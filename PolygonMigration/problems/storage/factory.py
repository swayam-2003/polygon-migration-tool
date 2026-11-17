from django.conf import settings

from .base import StorageError
from .local import LocalStorage

PROVIDER_LABELS = {
    "local": "Local filesystem",
    "azure": "Azure Blob Storage",
    "s3": "Amazon S3",
    "r2": "Cloudflare R2",
    "minio": "MinIO",
}


def normalize_provider(provider=None):
    return (provider if provider is not None else settings.STORAGE_PROVIDER or "local").strip().lower()


def get_storage_label(provider=None):
    provider = normalize_provider(provider)
    return PROVIDER_LABELS.get(provider, provider)


def get_storage(provider=None):
    provider = normalize_provider(provider)
    if provider == "local":
        return LocalStorage()
    if provider == "azure":
        from .azure import AzureStorage
        return AzureStorage()
    if provider in {"s3", "r2", "minio"}:
        from .s3 import S3CompatibleStorage
        return S3CompatibleStorage.from_settings(provider)
    raise StorageError(
        f"STORAGE_PROVIDER '{provider}' is not implemented. "
        "Use local, azure, s3, r2, or minio."
    )
