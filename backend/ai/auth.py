import os
import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import models
from database import get_db

logger = logging.getLogger(__name__)

# SpringBoot와 동일한 시크릿 사용
SECRET_KEY = os.getenv("JWT_SECRET")
ALGORITHM = "HS256"

bearer_scheme = HTTPBearer()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000)
    return f"pbkdf2:{salt}:{hashed.hex()}"


def verify_password(plain: str, stored: str) -> bool:
    try:
        _, salt, hashed = stored.split(":")
        test = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), 100000)
        return test.hex() == hashed
    except Exception:
        return False


def create_access_token(data: dict, expires_minutes: int = 60 * 24 * 7) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.utcnow() + timedelta(minutes=expires_minutes)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


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
    except JWTError as e:
        logger.warning(f"[Auth] JWT 검증 실패: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = db.query(models.User).filter(models.User.id == int(sub)).first()
    if not user:
        logger.warning(f"[Auth] 사용자 없음: sub={sub}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
