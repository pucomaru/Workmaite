import os
import logging
from jose import JWTError, jwt
try:
    from jose.exceptions import ExpiredSignatureError as _ExpiredSignatureError
except ImportError:
    _ExpiredSignatureError = None
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import models
from database import get_db

logger = logging.getLogger(__name__)

# SpringBoot와 동일한 시크릿 사용
SECRET_KEY = os.environ["JWT_SECRET"]
ALGORITHM = "HS256"

bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    """SpringBoot에서 발급된 JWT를 검증하고 사용자 정보를 반환."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            logger.warning("[Auth] JWT에 sub 없음")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        if payload.get("type") == "refresh":
            # refresh token을 API 인증에 사용하는 것 차단 (SEC-7)
            logger.warning("[Auth] refresh token으로 API 접근 시도")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError as e:
        if _ExpiredSignatureError and isinstance(e, _ExpiredSignatureError):
            logger.warning("[Auth] JWT 만료됨")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token_expired")
        if "Signature has expired" in str(e) or "expired" in str(e).lower():
            logger.warning("[Auth] JWT 만료됨")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="token_expired")
        logger.warning(f"[Auth] JWT 검증 실패: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = db.query(models.User).filter(models.User.id == int(sub)).first()
    if not user:
        logger.warning(f"[Auth] 사용자 없음: sub={sub}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
