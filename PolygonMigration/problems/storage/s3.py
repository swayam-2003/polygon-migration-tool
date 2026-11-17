import boto3
from botocore.exceptions import ClientError
from django.conf import settings

from .base import ObjectStorage, StorageError


class S3CompatibleStorage(ObjectStorage):
    """S3 API storage for AWS S3, Cloudflare R2, and MinIO."""

    def __init__(self, provider_name, bucket, region=None, endpoint_url=None, access_key=None, secret_key=None, secure=True):
        self.provider_name = provider_name
        self.bucket = bucket
        if not self.bucket:
            raise StorageError(f"{provider_name} bucket name is not configured.")
        if not access_key or not secret_key:
            raise StorageError(f"{provider_name} access key and secret key are required.")
        client_kwargs = {
            "service_name": "s3",
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
        }
        if region:
            client_kwargs["region_name"] = region
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url
        self.client = boto3.client(**client_kwargs)

    @classmethod
    def from_settings(cls, provider):
        if provider == "s3":
            return cls(
                provider_name="s3",
                bucket=settings.AWS_S3_BUCKET_NAME,
                region=settings.AWS_REGION or "us-east-1",
                endpoint_url=settings.AWS_S3_ENDPOINT_URL or None,
                access_key=settings.AWS_ACCESS_KEY_ID,
                secret_key=settings.AWS_SECRET_ACCESS_KEY,
            )
        if provider == "r2":
            account_id = settings.R2_ACCOUNT_ID
            endpoint = f"https://{account_id}.r2.cloudflarestorage.com" if account_id else None
            return cls(
                provider_name="r2",
                bucket=settings.R2_BUCKET_NAME,
                region="auto",
                endpoint_url=endpoint,
                access_key=settings.R2_ACCESS_KEY_ID,
                secret_key=settings.R2_SECRET_ACCESS_KEY,
            )
        if provider == "minio":
            endpoint = settings.MINIO_ENDPOINT
            if endpoint and not endpoint.startswith("http"):
                scheme = "https" if settings.MINIO_SECURE else "http"
                endpoint = f"{scheme}://{endpoint}"
            return cls(
                provider_name="minio",
                bucket=settings.MINIO_BUCKET_NAME,
                region="us-east-1",
                endpoint_url=endpoint,
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE,
            )
        raise StorageError(f"Unsupported S3-compatible provider: {provider}")

    def ensure_ready(self):
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            try:
                self.client.create_bucket(Bucket=self.bucket)
            except ClientError as exc:
                raise StorageError(f"Could not access or create bucket {self.bucket}: {exc}") from exc

    def upload_bytes(self, key, data):
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        except ClientError as exc:
            raise StorageError(f"Upload failed for {key}: {exc}") from exc

    def download_bytes(self, key):
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except ClientError as exc:
            raise StorageError(f"Download failed for {key}: {exc}") from exc

    def list_keys(self, prefix):
        keys = []
        token = None
        while True:
            kwargs = {"Bucket": self.bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            try:
                response = self.client.list_objects_v2(**kwargs)
            except ClientError as exc:
                raise StorageError(f"Listing failed for {prefix}: {exc}") from exc
            keys.extend(item["Key"] for item in response.get("Contents", []))
            if not response.get("IsTruncated"):
                break
            token = response.get("NextContinuationToken")
        return keys

    def delete_prefix(self, prefix):
        keys = self.list_keys(prefix)
        for offset in range(0, len(keys), 1000):
            chunk = keys[offset:offset + 1000]
            try:
                self.client.delete_objects(
                    Bucket=self.bucket,
                    Delete={"Objects": [{"Key": key} for key in chunk], "Quiet": True},
                )
            except ClientError as exc:
                raise StorageError(f"Delete failed under {prefix}: {exc}") from exc
        return len(keys)
