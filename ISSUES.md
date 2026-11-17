# Issues Analysis

The three product issues and three code issues below are ranked within each group. Edge-case answers say whether the behavior was executed in `problems/tests.py` or concluded by reading the code. The tests mock Polygon. They were not run against a live Polygon problem.

## Summary

| Type | Critical | High | Medium | Low | Total |
|------|----------|------|--------|-----|-------|
| Product Issues | 1 | 2 | 0 | 0 | 3 |
| Code Issues | 0 | 3 | 0 | 0 | 3 |

---

## Product Issues

### [P1] Database test migration keeps only the first 260 characters and drops empty sides

**Severity**: Critical

**Location**: `PolygonMigration/problems/views.py` (the `migrate_test_cases_to_db` loop, around the `input_data[:260]` assignment)

**Description**:
"Migrate Test Description to Database" is the action that fills `ProblemTestCase`. Before insert it runs `rstrip()` and then keeps `input[:260]` and `output[:260]`. The comment says bytes. The slice is on a Python string, so it keeps 260 characters. A test is inserted only when both sides are still non-empty. The page then says the migration succeeded.

**Impact**:
Any real Polygon test longer than 260 characters is stored incomplete. A judge or later export that trusts `ProblemTestCase` will grade against the wrong data. Tests with an empty input or an empty output, including a side that was only whitespace, disappear with no error. Sample rows created by the other button are not truncated. The two database copies of the same test can disagree.

**Evidence**:
Tested in `test_database_migration_drops_full_input_and_empty_cases`. A 300-character input and a 280-character output were stored as 260 characters each. The description was kept. A second test with an empty output was not stored.

**Suggested Fix**:
Store the full input and output, or stop writing them here and treat storage objects as the only full copy. Surface a count of skipped tests on the page. If a preview column is still useful, put the 260-character preview in a separate field.

---

### [P2] Re-migrating does not remove database tests that Polygon deleted

**Severity**: High

**Location**: `PolygonMigration/problems/views.py` (sample loop around `existing_sample_cases`, and the `ProblemTestCase` loop that updates `existing_test_cases[idx]`)

**Description**:
Both database writers update or insert by position. Neither deletes rows beyond the new list. Storage does the opposite: it deletes `test_cases/{problem_id}/` before uploading the new set.

**Impact**:
After a problem setter removes tests on Polygon, the database still returns the old tests. A problem that went from 20 tests to 12 still has 20 `ProblemTestCase` rows. The first 12 show the new data. The last 8 keep the removed data. The same shape applies to `SampleTestCase` when samples are removed. `Problem.test_case_count` changes only on "Create/Update problem in Database", so it can also stay at the old number. Storage and the database then disagree about which tests exist.

**Evidence**:
Tested in `test_remigration_leaves_removed_database_rows` for `ProblemTestCase` (20 rows, then a 12-test migration, 20 rows remain, rows 13–20 still contain the old input). Storage replacement was tested in `test_remigration_replaces_storage_objects`: four files were deleted and two new files remained. The sample-row path is the same loop shape and was read, not given its own shrinking-sample test.

**Suggested Fix**:
Replace the positional upsert with a delete-and-insert, or delete rows whose order is greater than the new list, inside the same transaction. Update `test_case_count` from the list that was actually saved. Use the Polygon test index as the identity so a gap does not overwrite the wrong row.

---

### [P3] A second problem with the same title cannot be saved

**Severity**: High

**Location**: `PolygonMigration/problems/models.py` (`Problem.slug` unique) and `PolygonMigration/problems/views.py` (`slug = slugify(title)` in the fetch path, then `Problem.objects.create`)

**Description**:
The slug is derived only from the title. The database also requires that slug to be unique. Lookup of an existing row uses `polygon_id`, not the slug. The create path has no alternate slug when the insert hits the unique constraint. The whole request is inside `transaction.atomic()`, and the page reports a generic rollback.

**Impact**:
Two different Polygon problems titled "Two Sum" cannot both be migrated. The second save fails. The first problem is left as it was. The user is not told that the title collided, so the next attempt looks like a random failure. Titles that differ only by punctuation or spacing can collide too, because `slugify` folds them to the same slug.

**Evidence**:
Tested in `test_same_title_blocks_the_second_problem`. Polygon ids `601` and `602` both parsed to the title "Two Sum". The first create succeeded. The second response contained "rolled back". Problem `602` was not inserted. Problem `601` stayed `easy`.

**Suggested Fix**:
Build the slug from the polygon id as well as the title, for example `two-sum-602`, and retry on conflict. Catch the integrity error and show "a problem with this title already exists" instead of the rollback sentence.

---

## Code Issues

### [C1] The cache clear before upload does not touch the cache that was written

**Severity**: High

**Location**: `PolygonMigration/problems/polygon_api.py` (`delete_problem_test_case_cache` uses `oj_dev_with_redis_storage_test_cases_{db_problem_id}`, while `store_test_cases_in_redis` uses `polygon_migration_test_cases_{polygon_id}`)

**Description**:
Before a storage upload, the view calls `delete_problem_test_case_cache(database_problem_id)`. That scan uses a different prefix, a different id (the database id, not the Polygon id), and a pattern copied from another project. The keys written by this app are never selected. `migrate_test_cases_to_storage` then prefers Redis over Polygon whenever the count key exists.

**Impact**:
A staff user can fetch a problem, change the tests on Polygon, and upload the cached copy for up to 30 minutes. The success message still says the upload was verified, because verification compares storage with the cached payload, not with Polygon. The delete call also cannot invalidate another service's cache, because it never wrote those keys.

**Evidence**:
Read from the two prefixes in `polygon_api.py`. Not executed against a live Redis server. The migration tests patch `get_test_cases_from_redis`, so they do not prove the key mismatch by running Redis.

**Suggested Fix**:
Delete `polygon_migration_test_cases_{polygon_id}*` before an upload, or skip the cache on the storage action and always refetch. Pass the Polygon id, not the database id, into that delete.

---

### [C2] A failed test-list call is saved as zero tests

**Severity**: High

**Location**: `PolygonMigration/problems/polygon_api.py` (`requests.post` in `_make_request` and `download_and_extract_package`; `get_test_cases` returns `[]` on any exception) and `PolygonMigration/problems/views.py` (`test_case_count = len(api.get_test_cases(polygon_id))`)

**Description**:
Polygon POSTs now wait at most 30 seconds and retry HTTP 429 and 503. `get_test_cases`, `get_problem_files`, and `get_file_content` still catch every exception and return an empty result. The view treats that empty list as the real test count and can save `test_case_count = 0` while still saving the statement. A failed call to `get_all_test_cases` now stops the migration instead of storing blank tests.

**Impact**:
A Polygon call now fails after the timeout and the retries, but it still holds the database transaction opened at the start of the POST while those retries run. A brief API error inside `get_test_cases` during "Create/Update problem in Database" can persist a problem that claims to have no tests. The user sees success if the rest of the save works.

**Evidence**:
Read from `_make_request`, `download_and_extract_package`, `get_test_cases`, and the `test_case_count` assignment. The automated tests stub `get_test_cases` with a real list, so they do not exercise the empty-on-error path.

**Suggested Fix**:
Do not save `test_case_count` from a swallowed failure. Use one fetch result for both the count and the bodies, and show the Polygon error on the page.

---

### [C3] A custom checker is compiled for the machine running the migrator

**Severity**: High

**Location**: `PolygonMigration/problems/polygon_api.py` (`_store_custom_checker`, the `sys.platform.startswith("win")` filename choice, and `compile_custom_checker`)

**Description**:
For a checker whose Polygon name does not start with `std::`, the app compiles `custom_checker.cpp` with the local `g++` and uploads the resulting binary. On Windows the object name is `custom_checker.exe`. On other systems it is `custom_checker`. The source file is uploaded only when compilation fails. The success text can still say the checker was uploaded.

**Impact**:
The binary matches the operator's OS and architecture, not the judge's. A checker built on a Windows laptop will not run on a Linux judge. A missing `testlib.h` or a failed compile silently substitutes source under a different name, so a downstream runner looking for `custom_checker` will not find it. The page does not say which of those two outcomes happened except by including the object key when the new storage path returns one.

**Evidence**:
Read from `_store_custom_checker` and `compile_custom_checker`. Not executed. The storage tests patch `get_custom_checker_info` to return `None`, so no compiler was invoked.

**Suggested Fix**:
Upload the checker source always, and compile only for a configured target triple, or skip compilation and record `checker_type=custom` for a person to build in the judge environment. Fail the migration when a custom checker was requested and the expected artifact was not produced.

---

## Edge Case Analysis

### Q1

A Polygon problem has 0 sample test cases but 15 regular test cases. What happens when you migrate this problem?

**Tested**, with Polygon mocked in `test_zero_samples_and_fifteen_regular_tests`. The 15 cases were marked `is_sample=False`, which is the flag `get_all_test_cases` sets when `useInStatements` is false. That flag mapping was read in `get_all_test_cases` and was not called against Polygon.

"Create/Update problem in Database" creates the `Problem` with `test_case_count` 15, because that number comes from `len(get_test_cases(...))`, not from the sample list. It creates zero `SampleTestCase` rows. It does not create `ProblemTestCase` rows.

"Migrate Test Description to Database" then creates 15 `ProblemTestCase` rows, all with `is_sample=False`, provided each test has non-empty input and output after `rstrip`.

A storage upload of that same list writes `test_cases/{database_id}/01` through `15` and the matching `.a` files, then reads them back. That 15-file upload was not the test that ran. It follows the loop in `migrate_test_cases_to_storage`, which uploads every non-empty case and numbers by position.

The on-screen test table still lists all 15 during fetch. The main solution is requested on the database-save path. In the test, Polygon solutions were stubbed as an empty list, so no solution was shown.

### Q2

A problem is migrated with 20 test cases. Later, the problem setter removes 8 test cases on Polygon (now 12 remain). The problem is re-migrated. What happens?

**Tested** for the database in `test_remigration_leaves_removed_database_rows`, and **tested** for storage in `test_remigration_replaces_storage_objects`. Both used mocked Polygon payloads rather than a live edit on Polygon.

Storage: the upload deletes every object under `test_cases/{database_id}/` and writes the current 12 cases as `01` through `12` plus `.a` files. The old `13` through `20` objects are gone. In the test, a 4-file set was replaced by a 2-file set and the old objects were not left behind.

Database, "Migrate Test Description to Database": 20 `ProblemTestCase` rows remain. Rows 1–12 are overwritten with the new input and output. Rows 13–20 still contain the removed tests. `order` on those leftover rows is unchanged.

Database, "Create/Update problem in Database": the problem statement and `test_case_count` update. `test_case_count` becomes 12 only if `get_test_cases` returns 12 items. Sample rows are updated by position and extras are not deleted. This sample path was read from the same style of loop and was not re-tested with a shrinking sample list.

If the user only clicks the storage button, `Problem.test_case_count` and the `ProblemTestCase` rows stay at the old values while storage has 12 files.

### Q3

Two different Polygon problems have the exact same title: "Two Sum". You migrate the first one successfully. Then you try to migrate the second one. What happens?

**Tested** in `test_same_title_blocks_the_second_problem` with two polygon ids and one parsed title. Not tested against two live Polygon problems.

The first save inserts a `Problem` whose slug is `two-sum`. The second save also computes `two-sum` and inserts a new row because the lookup is by `polygon_id`, which does not match the first row. The unique constraint on `slug` raises. The transaction rolls back. The page says the migration failed and all changes have been rolled back. The second problem is not in the database. The first problem is unchanged, including its difficulty and tags. No duplicate title is stored.

Fetching the second problem, without the database button, still shows the statement. The failure happens on save.

### Q4

When test cases are saved to the database via "Migrate Test Cases to DB", some data is intentionally discarded. What data is lost? Why might this cause problems?

**Tested** in `test_database_migration_drops_full_input_and_empty_cases`: characters after position 260 are discarded for both input and output, a test with an empty output is discarded, and the description is kept. The button in the template is labeled "Migrate Test Description to Database" and posts `migrate_test_cases_to_db`.

**Read from the view, not separately tested**:

- `rstrip()` removes trailing whitespace before the length check and the slice. A test whose output is only a newline is dropped.
- The slice is 260 characters, not 260 bytes, despite the comment.
- The Polygon index, the `manual` flag, groups, and points are not columns on `ProblemTestCase`. `order` is a new counter of saved rows, not the Polygon index. A skipped empty test makes `order` diverge from the list position used for updates.
- The full text is not recoverable from this table. The storage upload keeps the full bytes, but only if that other button was used, and its file numbers are positions in the Polygon list, not `ProblemTestCase.order`.

This causes wrong verdicts if anything grades from `ProblemTestCase`. It also makes the database copy and the storage copy different lengths and, after a skipped test, different indexes. A later re-migration updates by list position, so the truncated value is what gets compared and overwritten.

---

## Notes

`Problem.notes` and `Problem.genie_chat` were on the model and missing from `0001_initial`. Creating a problem raised `no such column: problems_problem.notes`. `0002_problem_notes_and_genie_chat` adds both columns. That is fixed in this tree, so it is not one of the open issues above.

`memory_limit` is labeled MB and is stored from Polygon `problem.info` `memoryLimit` with a default of 256. I did not call a live Polygon problem, so I am not treating a bytes-versus-megabytes mismatch as a confirmed issue.

The login view logs out an already authenticated user on GET. That is a smaller product bug than the three above. Unused imports in `problems/views.py` (`BeautifulSoup`, `cache`) are real and low severity. I left them in place.
