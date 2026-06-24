import boto3
from core.config import settings


def _get_client():
    if not settings.s3_access_key:
        raise RuntimeError("S3_ACCESS_KEY not configured in .env")

    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint or None,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region or "us-east-1",
    )


def upload_file(file_bytes: bytes, key: str, content_type: str = "text/csv") -> str:
    client = _get_client()
    client.put_object(
        Bucket=settings.s3_bucket,
        Key=key,
        Body=file_bytes,
        ContentType=content_type,
    )
    if settings.s3_public_url:
        return f"{settings.s3_public_url}/{key}"
    return f"https://{settings.s3_bucket}.s3.{settings.s3_region}.amazonaws.com/{key}"


def generate_presigned_url(key: str, expiry: int = 3600) -> str:
    client = _get_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.s3_bucket, "Key": key},
        ExpiresIn=expiry,
    )
