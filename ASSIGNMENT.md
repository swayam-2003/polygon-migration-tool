# Assignment status

This file is the map of the Polygon Migration Tool assessment: what was asked, what is in the tree, and what still has to be done by hand before emailing the submission.

## What the assessment asks for

- A working staff flow: log in, fetch a Polygon problem, save it, save test cases, upload test cases, and show that the uploaded files are the files that were sent.
- Storage that another engineer can configure from `.env.example`, with `.env` and secrets kept out of git.
- The storage change committed, plus a pull-request description of what changed and how to verify it.
- `DOCUMENTATION.md` at the repository root, explaining how the screens use the backend, database, and external services.
- `ISSUES.md` at the repository root, with three product issues, three code issues, and the four edge-case answers.
- A 5–10 minute video, the Polygon username, the actual time spent, and an email to nalin@algouniversity.com.

## What is done

Object storage is selected with `STORAGE_PROVIDER`.

| Value | Behavior |
| --- | --- |
| `local` | Writes `PolygonMigration/local_storage`. No cloud account. This is the default. |
| `azure` | Existing Azure username/password blob upload. |
| `s3` | Amazon S3, or another S3 endpoint via `AWS_S3_ENDPOINT_URL`. |
| `r2` | Cloudflare R2. |
| `minio` | MinIO. |

Google Cloud Storage and Google Drive are not implemented.

An upload is reported as success only after each test object is downloaded and compared. The home page lists the key, size, and `match` result. `python manage.py verify_storage` uploads two sample cases, checks them, and deletes them.

`python manage.py test problems.tests` was run with `DB_ENGINE=sqlite`. 12 tests passed. `verify_storage` then reported 4 matching objects and deleted them.

`problems/migrations/0002_problem_notes_and_genie_chat.py` adds columns the model already had. Without it, saving a problem fails.

`DOCUMENTATION.md` describes the request path. `ISSUES.md` has the ranked issues and the edge-case answers. `PULL_REQUEST.md` is the pull-request text. `.env.example` has no real secrets. `.gitignore` excludes `.env`, `local_storage/`, `db.sqlite3`, logs, and virtualenvs.

The folder was not a git repository. The commit created here is the first commit, so it contains the starter project and these changes together. `PULL_REQUEST.md` describes the delta from the starter.

## How to run

```text
cd Polygon-migration-assignment/PolygonMigration
python -m venv .venv
.venv\Scripts\activate
pip install -r ..\requirement.txt
copy .env.example .env
```

For a machine without PostgreSQL, set `DB_ENGINE=sqlite` in `.env`. Otherwise start PostgreSQL and set `DB_ENGINE=postgresql`.

Put real `POLYGON_API_KEY` and `POLYGON_API_SECRET` in `.env` before fetching a live problem. Leave `STORAGE_PROVIDER=local` to verify files on disk.

```text
python manage.py migrate
python manage.py createsuperuser
python manage.py verify_storage
python manage.py runserver
```

Log in at http://localhost:8000/users/login/ as a staff user. Fetch a Polygon id, choose a difficulty, save the problem, then use the storage button. The green panel should list `match` for each object. The same bytes are under `local_storage/test_cases/{database id}/`.

## What you still need to submit

These items are not in the repo because they are personal or cannot be produced from the code:

- Record a 5–10 minute video a reviewer can open. Show login, fetch, database save, storage upload, the on-screen verification list, and the files on disk or the `verify_storage` output. Put the URL in the email.
- Fill in your Polygon username, the actual hours you spent, your city, whether you can interview in Bangalore, and whether you can join immediately.
- Send the email yourself. A draft is below. Do not commit secrets while you do this.

```text
To: nalin@algouniversity.com
Subject: [Polygon Assessment] — Your Name

Repository URL:
Video URL:
Current city:
Can Interview inperson in Bangalore:
Can Join Immediately:

Notes (optional):
Polygon username:
Time spent:
```

There is no GitHub remote in this workspace, so there is no pull-request URL yet. Create the remote, push the branch, and open the pull request with the body in `PULL_REQUEST.md`. Put that repository URL in the email.

## Section 3.1

The assessment says the product and code issues must be chosen and explained by you, without AI, and that a shortlist interview will ask you to defend them. `ISSUES.md` in this tree is a written analysis of the code and of `problems/tests.py`. Read it, run the flows yourself, and replace any ranking or recommendation you cannot explain in your own words before you submit. The edge-case section marks what was executed in tests and what was only read.

## Assumptions and blockers

- No Polygon credentials were available here, so the live fetch, package download, and checker compile were not run against Polygon. The view tests stub those calls.
- No browser session was available. The pages were exercised with Django's test client. Login redirect, problem save, truncation, slug collision, leftover rows, and the storage read-back were covered there.
- SQLite is supported so the app can run without PostgreSQL. The default in `.env.example` is still PostgreSQL.
- Redis is optional. An empty `REDIS_HOST` skips it.
- Azure username/password auth is unchanged and still fails when that account requires MFA. Use `local`, `s3`, `r2`, or `minio` if Azure user auth is blocked.
- `g++` is optional. A custom checker is uploaded as source when compilation fails, which is called out in `ISSUES.md`.
