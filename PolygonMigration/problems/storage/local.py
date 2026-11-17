import os
import shutil

from django.conf import settings

from .base import ObjectStorage, StorageError


class LocalStorage(ObjectStorage):
    """Filesystem storage used for local setup and upload verification.

    Files live under LOCAL_STORAGE_ROOT, which defaults to
    PolygonMigration/local_storage. This provider does not need cloud credentials.
    """

    provider_name = "local"

    def __init__(self, root=None):
        self.root = os.path.abspath(root or settings.LOCAL_STORAGE_ROOT)

    def ensure_ready(self):
        os.makedirs(self.root, exist_ok=True)

    def _path(self, key):
        relative = key.replace("\\", "/").lstrip("/")
        path = os.path.abspath(os.path.join(self.root, *relative.split("/")))
        if os.path.commonpath([self.root, path]) != self.root:
            raise StorageError(f"Refusing to access a path outside storage root: {key}")
        return path

    def upload_bytes(self, key, data):
        self.ensure_ready()
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as handle:
            handle.write(data)

    def download_bytes(self, key):
        path = self._path(key)
        if not os.path.isfile(path):
            raise StorageError(f"Object not found: {key}")
        with open(path, "rb") as handle:
            return handle.read()

    def delete_prefix(self, prefix):
        path = self._path(prefix.rstrip("/"))
        if not os.path.isdir(path):
            return 0
        count = sum(len(files) for _, _, files in os.walk(path))
        shutil.rmtree(path)
        return count

    def list_keys(self, prefix):
        path = self._path(prefix.rstrip("/"))
        if not os.path.isdir(path):
            return []
        keys = []
        for dirpath, _, filenames in os.walk(path):
            for filename in filenames:
                full = os.path.join(dirpath, filename)
                keys.append(os.path.relpath(full, self.root).replace("\\", "/"))
        return sorted(keys)
