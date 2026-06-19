"""r2_storage.py — Cloudflare R2 파일 저장소 유틸리티 (S3 호환 API / boto3)"""

import mimetypes
import os

import boto3
from botocore.config import Config

R2_ACCESS_KEY_ID = os.environ["R2_ACCESS_KEY_ID"]
R2_SECRET_ACCESS_KEY = os.environ["R2_SECRET_ACCESS_KEY"]
R2_ENDPOINT = os.environ["R2_ENDPOINT"]
R2_BUCKET = "workmaite-bucket"


def _client():
    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def upload_bytes(
    data: bytes, key: str, content_type: str = "application/octet-stream"
) -> str:
    """바이트 데이터를 R2에 업로드하고 공개 URL을 반환합니다."""
    _client().put_object(
        Bucket=R2_BUCKET,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    return f"{R2_ENDPOINT.rstrip('/')}/{R2_BUCKET}/{key}"


def download_bytes(key: str) -> bytes:
    """R2에서 파일을 다운로드합니다."""
    resp = _client().get_object(Bucket=R2_BUCKET, Key=key)
    return resp["Body"].read()


def delete_object(key: str) -> None:
    """R2에서 파일을 삭제합니다."""
    _client().delete_object(Bucket=R2_BUCKET, Key=key)


def url_to_key(url: str) -> str:
    """R2 URL에서 object key를 추출합니다 (UX-6: presigned·다른 엔드포인트 URL도 처리).

    저장된 file_path가 공개 URL / presigned URL(쿼리 포함) / 다른 엔드포인트 도메인 /
    이미 key 형태 등 무엇이든 버킷 이후 경로를 key로 안전하게 추출한다.
    """
    if not url:
        return url
    if not url.startswith("http"):
        return url  # 이미 key
    from urllib.parse import urlparse, unquote

    path = unquote(urlparse(url).path).lstrip("/")  # 쿼리스트링(presigned 서명) 제거
    # path가 "<bucket>/<key>" 또는 "<key>" — 버킷 세그먼트가 있으면 제거
    if path.startswith(f"{R2_BUCKET}/"):
        return path[len(R2_BUCKET) + 1 :]
    return path


def is_r2_url(path: str) -> bool:
    """경로가 R2 URL인지 확인합니다."""
    return bool(path) and path.startswith("http") and R2_BUCKET in path


def get_content_type(filename: str) -> str:
    """파일 확장자로 MIME 타입을 추론합니다."""
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


def generate_presigned_url(key: str, expires_in: int = 3600) -> str:
    """R2 오브젝트에 대한 시간 제한 presigned URL을 생성합니다."""
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": R2_BUCKET, "Key": key},
        ExpiresIn=expires_in,
    )
