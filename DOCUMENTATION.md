# Polygon Migration Tool

This document explains how a staff user action moves through the browser, the Django backend, PostgreSQL or SQLite, Redis, the Polygon API, and object storage.

## What the application does

A staff user logs in, enters a Polygon problem id, and reviews the statement and test cases. From that screen the user can:

1. Save the problem, tags, difficulty, and sample tests in the database.
2. Save a shortened copy of every test case in the database.
3. Upload the full test-case files to object storage and read them back.

The storage button still submits the form field `migrate_to_azure`. The server uses `STORAGE_PROVIDER` to decide where the files go. The button label shows the active provider, for example "Migrate Test Cases to Local filesystem".

## Configure it

Copy `PolygonMigration/.env.example` to `PolygonMigration/.env`.

| Purpose | Variables |
| --- | --- |
| Django | `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` |
| Database | `DB_ENGINE` (`postgresql` or `sqlite`), plus `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` for PostgreSQL |
| Polygon | `POLYGON_API_KEY`, `POLYGON_API_SECRET` |
| Cache | `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_SSL`. Leave `REDIS_HOST` empty to skip Redis. |
| Storage | `STORAGE_PROVIDER` = `local`, `azure`, `s3`, `r2`, or `minio` |

`local` writes files under `LOCAL_STORAGE_ROOT`, which defaults to `PolygonMigration/local_storage`. It does not need a cloud account. Azure, S3, R2, and MinIO settings are in `.env.example`. Google Cloud Storage and Google Drive are not implemented; selecting them raises a clear error.

Create a staff user with `python manage.py createsuperuser`, then open `http://localhost:8000/users/login/`. Only `is_staff` users stay logged in. The home page is `/`.

## Login

`users/templates/users/login.html` posts the email and password to `/users/login/`.

`users/views.py` calls `authenticate`. `users/backends.py` loads `users.User` by email and checks the password. The user model is email-based (`USERNAME_FIELD = 'email'`). If the user is not staff, the view shows an error and does not start a session. A staff user is sent to `problems:index`.

Opening the login page while already authenticated logs the current user out before the form is shown.

## Fetch a problem

The home form in `problems/templates/problems/index.html` posts `problem_id` to `/`. `problems/views.py` `index` allows only an authenticated staff user.

For a fetch with no migration flag, the view:

1. Calls Polygon `problem.info`.
2. Downloads the latest `standard` package with `problem.package`, unzips it, and reads `problem.html`.
3. Parses the title, statement, input format, output format, and notes in `parse_problem_html`.
4. Calls `problem.checker` and maps `std::ncmp.cpp` style names onto the checker choices. Anything else is stored as `custom`.
5. Calls `problem.tests` through `get_test_cases` and uses the list length as `test_case_count`.
6. Loads every test body with `problem.testInput` and `problem.testAnswer` through `get_all_test_cases`, unless that payload is already in Redis.
7. Renders previews. Input, output, and description longer than 50 characters get a "View Full" modal.

`get_all_test_cases` marks a test as a sample when Polygon's `useInStatements` flag is true. Redis keys, when Redis is configured, are `polygon_migration_test_cases_{polygon_id}_count` and `_test_{n}`, with a 30 minute TTL. If Redis is down or unset, the view calls Polygon again.

The main solution is loaded only when the problem already exists in the database, or during "Create/Update problem in Database". The view prefers the Polygon solution tagged `MA`.

## Save the problem

"Create/Update problem in Database" posts `migrate_to_db=1`, `difficulty`, and `tags`. The browser copies the difficulty select and the selected tag chips into that form before submit. Difficulty is required.

Inside one database transaction the view:

1. Looks up `Problem` by `polygon_id`.
2. Creates or updates the title, slug, statement, limits, checker, notes, and `test_case_count`.
3. Clears `extra_tags` and recreates the selected tags, plus `new_tag` when that field is present.
4. Rebuilds sample rows in `SampleTestCase` from tests whose `is_sample` flag is true. Both input and output must be non-empty after `rstrip`. These sample rows keep the full text.

`Problem.slug` is `slugify(title)` and is unique. `Problem.polygon_id` is also unique. Tags are `ProblemTag` rows shared across problems.

This action does not write `ProblemTestCase` rows and does not upload files.

## Save test cases in the database

"Migrate Test Description to Database" posts `migrate_test_cases_to_db=1`. The problem must already exist.

The view reads the Redis cache or calls `get_all_test_cases` again. For each test with both input and output after `rstrip`, it keeps the first 260 characters of input and of output, plus the description and `is_sample`, in `ProblemTestCase`. Existing rows are updated by position. Rows past the end of the new list are not deleted. Tests with an empty side are skipped, but they still occupy a position when later rows are matched, because the loop index is not compacted.

The button does not change `Problem.test_case_count`.

## Upload test cases to storage

The storage button posts `migrate_to_azure=1`. The problem must already exist. The view then calls `PolygonAPI.migrate_test_cases_to_storage(polygon_id, database_problem_id)`.

That method:

1. Builds the client from `STORAGE_PROVIDER` in `problems/storage/factory.py`.
2. Reads cached tests or fetches them from Polygon.
3. Deletes `test_cases/{database_problem_id}/`.
4. Uploads input to `test_cases/{id}/{nn}` and output to `test_cases/{id}/{nn}.a`. `nn` is the 1-based position in the Polygon list. An empty input or output leaves a gap at that number.
5. If Polygon reports a checker that does not start with `std::`, compiles it with `g++` when available and uploads `custom_checker` or `custom_checker.exe`. If compilation fails, it uploads `custom_checker.cpp`.
6. Downloads every uploaded test object and compares the bytes with the source text encoded as UTF-8.
7. If any upload or comparison fails, deletes the problem prefix and raises. The page shows the exception. The success panel lists each key, its size, and `match`.

`python manage.py verify_storage` does the same read-back with two tiny test cases and then deletes them. Use it before pointing the app at a real bucket.

### Provider behavior

| `STORAGE_PROVIDER` | Where files go |
| --- | --- |
| `local` | Files under `LOCAL_STORAGE_ROOT` |
| `azure` | Blob container from the Azure settings, using `UsernamePasswordCredential` |
| `s3` | AWS S3, or any S3 API endpoint in `AWS_S3_ENDPOINT_URL` |
| `r2` | `https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com` |
| `minio` | The MinIO endpoint. The bucket is created if it is missing. |

Azure credentials are required only when `STORAGE_PROVIDER=azure`. The old `AzureBlobManager` import path still works through `problems/AzureTestcase.py`.

## Failure behavior

The fetch, database writes, and storage upload for one POST run in a single `transaction.atomic()` block. A database exception rolls back the database work from that request. Object storage is not inside the database transaction. If the upload itself fails, `migrate_test_cases_to_storage` deletes the partial prefix. If the upload already verified and a later step in the same request raises, the view calls `delete_azure_blob`, which deletes that prefix too.

Redis cache deletion before an upload uses the prefix `oj_dev_with_redis_storage_test_cases_{database_id}`. The cache writes use `polygon_migration_test_cases_{polygon_id}`. Those prefixes do not match, so the pre-upload delete does not remove the cached tests.

## Models

| Model | Role |
| --- | --- |
| `users.User` | Staff login and profile fields |
| `problems.Problem` | One migrated problem, keyed by `polygon_id` |
| `problems.ProblemTag` | Tag names |
| `problems.SampleTestCase` | Full sample input and output shown with the statement |
| `problems.ProblemTestCase` | Truncated input, output, description, and sample flag |
| `contents.Topic` | Topic rows used by the user profile. The migration screen does not edit topics. |

Admin screens are under `/admin/`.

## What changed for storage

The assignment started with Azure-only uploads in `problems/AzureTestcase.py`. Uploads now go through `problems/storage/`. The migration reports success only after a read-back comparison. `problems/migrations/0002_problem_notes_and_genie_chat.py` adds `notes` and `genie_chat`, which were on the model but missing from the initial migration, so creating a problem failed. `.env.example` documents every implemented provider and keeps secrets out of git.
