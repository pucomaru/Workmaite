import os
from fastapi import APIRouter, Depends, HTTPException
from livekit.api import AccessToken, VideoGrants

import models
from auth import get_current_user

router = APIRouter(prefix="/api/livekit", tags=["livekit"])


@router.get("/token/{meeting_id}/{session_id}")
def get_livekit_token(
    meeting_id: int,
    session_id: int,
    current_user: models.User = Depends(get_current_user),
):
    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")

    if not api_key or not api_secret:
        raise HTTPException(
            status_code=503,
            detail="LiveKit 설정이 없습니다. LIVEKIT_API_KEY / LIVEKIT_API_SECRET을 .env에 추가하세요.",
        )

    # room name: meeting_{meeting_id}_session_{session_id}
    room_name = f"meeting_{meeting_id}_session_{session_id}"
    identity = f"user_{current_user.id}"
    display_name = current_user.name

    token = (
        AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_name(display_name)
        .with_grants(
            VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .to_jwt()
    )

    # 프론트엔드에서 직접 연결할 LiveKit URL
    # 개발환경: ws://localhost:7880 (--dev 모드는 WebSocket CORS 제한 없음)
    public_url = os.getenv("LIVEKIT_PUBLIC_URL", os.getenv("LIVEKIT_URL", "ws://localhost:7880"))

    return {
        "token": token,
        "url": public_url,
        "room": room_name,
        "identity": identity,
    }
