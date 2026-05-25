from sqlalchemy.orm import Session
import models


def create_notification(
    db: Session,
    user_id: int,
    type: str,
    message: str,
    ref_id: int = None,
    ref_type: str = None,
):
    notif = models.Notification(
        user_id=user_id,
        type=type,
        message=message,
        ref_id=ref_id,
        ref_type=ref_type,
    )
    db.add(notif)
    return notif
