import logging

from azure.core.exceptions import ClientAuthenticationError, ResourceNotFoundError
from azure.identity import UsernamePasswordCredential
from azure.storage.blob import BlobServiceClient
from django.conf import settings

from .base import ObjectStorage, StorageError

logger = logging.getLogger(__name__)


class AzureBlobManager:
    """Azure Blob Storage client authenticated with a username and password.

    Kept so existing imports of problems.AzureTestcase.AzureBlobManager continue
    to work. New migration code uses AzureStorage instead.
    """

    def __init__(self, account_url, tenant_id, client_id, username, password):
        self.account_url = account_url
        logger.info("Attempting to authenticate to Azure Blob Storage")
        try:
            credential = UsernamePasswordCredential(
                tenant_id=tenant_id,
                client_id=client_id,
                username=username,
                password=password,
            )
            self.blob_service_client = BlobServiceClient(
                account_url=self.account_url,
                credential=credential,
            )
        except ClientAuthenticationError as exc:
            logger.warning("Azure authentication failed: %s", exc)
            raise
        except Exception:
            logger.exception("Unexpected error creating the Azure blob client")
            raise

    def upload_test_case(self, container_name, db_problem_id, test_number, input_data, output_data):
        storage = AzureStorage(container_name=container_name, blob_service_client=self.blob_service_client)
        storage.upload_test_case(db_problem_id, test_number, input_data, output_data)

    def empty_blob(self, container_name, problem_id):
        storage = AzureStorage(container_name=container_name, blob_service_client=self.blob_service_client)
        storage.delete_problem(problem_id)


class AzureStorage(ObjectStorage):
    provider_name = "azure"

    def __init__(self, container_name=None, blob_service_client=None):
        self.container_name = container_name or settings.AZURE_CONTAINER_NAME
        if blob_service_client is not None:
            self.blob_service_client = blob_service_client
            return
        required = {
            "AZURE_STORAGE_ACCOUNT_URL": settings.AZURE_STORAGE_ACCOUNT_URL,
            "AZURE_TENANT_ID": settings.AZURE_TENANT_ID,
            "AZURE_CLIENT_ID": settings.AZURE_CLIENT_ID,
            "AZURE_USERNAME": settings.AZURE_USERNAME,
            "AZURE_PASSWORD": settings.AZURE_PASSWORD,
            "AZURE_CONTAINER_NAME": self.container_name,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise StorageError("Azure storage is missing: " + ", ".join(missing))
        manager = AzureBlobManager(
            account_url=settings.AZURE_STORAGE_ACCOUNT_URL,
            tenant_id=settings.AZURE_TENANT_ID,
            client_id=settings.AZURE_CLIENT_ID,
            username=settings.AZURE_USERNAME,
            password=settings.AZURE_PASSWORD,
        )
        self.blob_service_client = manager.blob_service_client

    def ensure_ready(self):
        client = self.blob_service_client.get_container_client(self.container_name)
        try:
            client.get_container_properties()
        except ResourceNotFoundError:
            client.create_container()

    def upload_bytes(self, key, data):
        try:
            blob = self.blob_service_client.get_blob_client(container=self.container_name, blob=key)
            blob.upload_blob(data, overwrite=True)
        except Exception as exc:
            raise StorageError(f"Azure upload failed for {key}: {exc}") from exc

    def download_bytes(self, key):
        try:
            blob = self.blob_service_client.get_blob_client(container=self.container_name, blob=key)
            return blob.download_blob().readall()
        except ResourceNotFoundError as exc:
            raise StorageError(f"Azure object not found: {key}") from exc
        except Exception as exc:
            raise StorageError(f"Azure download failed for {key}: {exc}") from exc

    def list_keys(self, prefix):
        try:
            container = self.blob_service_client.get_container_client(self.container_name)
            return [blob.name for blob in container.list_blobs(name_starts_with=prefix)]
        except Exception as exc:
            raise StorageError(f"Azure list failed for {prefix}: {exc}") from exc

    def delete_prefix(self, prefix):
        keys = self.list_keys(prefix)
        container = self.blob_service_client.get_container_client(self.container_name)
        for key in keys:
            container.delete_blob(key)
        return len(keys)
