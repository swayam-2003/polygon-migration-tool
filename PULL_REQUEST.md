# Pull request

**Title:** Store migrated test cases through a configurable provider and verify the upload

## Summary

- Test-case uploads go through `STORAGE_PROVIDER` instead of a hard-coded Azure client. `local`, `azure`, `s3`, `r2`, and `minio` are implemented. `local` is the default and writes `PolygonMigration/local_storage`.
- A migration is successful only after every uploaded test object is read back and compared with the source bytes. The home page lists each key, size, and match result. `python manage.py verify_storage` does the same check with two sample cases and then deletes them.
- `Problem.notes` and `Problem.genie_chat` are added in migration `0002`, because the model already expected those columns and saving a problem failed without them.

Google Cloud Storage and Google Drive are not implemented. Choosing them raises an error that names the supported providers.

## What changed

- `PolygonMigration/problems/storage/` holds the shared layout (`test_cases/{problem id}/{nn}` and `{nn}.a`), the local filesystem, Azure, and the S3-compatible client used for S3, R2, and MinIO.
- `PolygonAPI.migrate_test_cases_to_storage` deletes the old prefix, uploads, optionally uploads a custom checker, verifies, and deletes the prefix again if verification fails.
- `problems/AzureTestcase.py` remains as an import path to `AzureBlobManager`.
- The storage button label uses the active provider. The posted field is still `migrate_to_azure`.
- `.env.example` and `README.md` document the provider switch. `.gitignore` excludes `.env`, `local_storage/`, SQLite files, logs, and virtualenvs.
- `boto3` is in `requirement.txt`.

## Configure

Copy `PolygonMigration/.env.example` to `PolygonMigration/.env`.

```text
STORAGE_PROVIDER=local
DB_ENGINE=sqlite
POLYGON_API_KEY=your-key
POLYGON_API_SECRET=your-secret
```

Use `DB_ENGINE=postgresql` with `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` when PostgreSQL is available.

For S3 set `STORAGE_PROVIDER=s3` plus `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, and `AWS_S3_BUCKET_NAME`. Set `AWS_S3_ENDPOINT_URL` for a non-AWS endpoint.

For R2 set `STORAGE_PROVIDER=r2` plus `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, and `R2_BUCKET_NAME`.

For MinIO set `STORAGE_PROVIDER=minio` plus `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MINIO_BUCKET_NAME`, and `MINIO_SECURE`.

For Azure set `STORAGE_PROVIDER=azure` plus `AZURE_STORAGE_ACCOUNT_URL`, `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_USERNAME`, `AZURE_PASSWORD`, and `AZURE_CONTAINER_NAME`.

Leave `REDIS_HOST` empty to run without Redis.

## Verify

From `PolygonMigration/`:

```text
pip install -r ../requirement.txt
python manage.py migrate
python manage.py verify_storage
python manage.py test problems.tests
python manage.py createsuperuser
python manage.py runserver
```

`verify_storage` should print `match` for four objects and then delete them.

As a staff user, open `/users/login/`, fetch a Polygon problem, choose a difficulty, save the problem, then use the storage button. The success panel should list every object as `match`. For `local`, the same files are under `local_storage/test_cases/{database problem id}/`. `01` is the input and `01.a` is the output.

The test suite covers the local read-back, a gap when a test has an empty side, replacement of a previous upload, the S3 client's put/get calls, truncation to 260 characters, leftover database rows, and the duplicate-title failure. Those view tests mock Polygon.

## Out of scope

The product and code issues in `ISSUES.md` are documented there. This change does not change the 260-character database copy, the leftover rows on re-migration, the slug uniqueness rule, the Redis prefix mismatch, or the host-local checker binary.
