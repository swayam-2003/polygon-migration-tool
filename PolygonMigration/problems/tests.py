import shutil
import tempfile
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from problems.models import Problem, ProblemTestCase, SampleTestCase
from problems.polygon_api import PolygonAPI
from problems.storage.base import StorageError
from problems.storage.factory import get_storage
from problems.storage.local import LocalStorage

PROBLEM_HTML = """
<html><body>
<div class="title">Two Sum</div>
<div class="legend"><p>Add two numbers.</p></div>
<div class="input-specification"><div class="section-title">Input</div><p>Two integers.</p></div>
<div class="output-specification"><div class="section-title">Output</div><p>One integer.</p></div>
<div class="note"><div class="section-title">Note</div><p>Sample note.</p></div>
</body></html>
"""


def polygon_cases(count, prefix="case", sample_count=0):
    cases = []
    for index in range(1, count + 1):
        cases.append({
            "index": index,
            "manual": True,
            "is_sample": index <= sample_count,
            "description": f"desc-{prefix}-{index}",
            "input": f"{prefix}-input-{index}\n",
            "output": f"{prefix}-output-{index}\n",
        })
    return cases


class LocalStorageTests(TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.storage = LocalStorage(root=self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_upload_read_back_and_delete(self):
        self.storage.upload_test_case(4, 1, "in", "out")
        report = self.storage.verify_test_cases(4, [{"number": 1, "input": "in", "output": "out"}])
        self.assertEqual(report["failed"], [])
        self.assertEqual(report["verified_count"], 2)
        self.assertEqual(self.storage.list_keys("test_cases/4/"), ["test_cases/4/01", "test_cases/4/01.a"])
        self.assertEqual(self.storage.delete_problem(4), 2)
        self.assertEqual(self.storage.list_keys("test_cases/4/"), [])

    def test_mismatch_is_reported(self):
        self.storage.upload_test_case(4, 1, "in", "out")
        report = self.storage.verify_test_cases(4, [{"number": 1, "input": "OTHER", "output": "out"}])
        self.assertEqual(report["failed"][0]["status"], "mismatch")

    def test_path_escape_is_rejected(self):
        with self.assertRaises(StorageError):
            self.storage.upload_bytes("../outside.txt", b"nope")


class StorageMigrationTests(TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_provider_switch_rejects_unimplemented_backend(self):
        with override_settings(STORAGE_PROVIDER="gdrive"):
            with self.assertRaises(StorageError):
                get_storage()

    @override_settings(POLYGON_API_KEY="test-key", POLYGON_API_SECRET="test-secret", REDIS_HOST="")
    def test_storage_upload_is_verified_and_renumbered(self):
        cases = polygon_cases(3)
        cases[1]["output"] = ""
        with override_settings(STORAGE_PROVIDER="local", LOCAL_STORAGE_ROOT=self.root):
            api = PolygonAPI()
            with patch.object(api, "get_test_cases_from_redis", return_value=cases), \
                    patch.object(api, "get_custom_checker_info", return_value=None):
                result = api.migrate_test_cases_to_storage("100", db_problem_id=9)
            storage = LocalStorage(root=self.root)
            self.assertEqual(result["uploaded_count"], 2)
            self.assertEqual(result["skipped"], [2])
            self.assertEqual(result["verified_count"], 4)
            self.assertEqual(storage.download_bytes("test_cases/9/01"), b"case-input-1\n")
            self.assertEqual(storage.download_bytes("test_cases/9/03"), b"case-input-3\n")
            self.assertNotIn("test_cases/9/02", storage.list_keys("test_cases/9/"))

    @override_settings(POLYGON_API_KEY="test-key", POLYGON_API_SECRET="test-secret", REDIS_HOST="")
    def test_remigration_replaces_storage_objects(self):
        with override_settings(STORAGE_PROVIDER="local", LOCAL_STORAGE_ROOT=self.root):
            api = PolygonAPI()
            with patch.object(api, "get_custom_checker_info", return_value=None):
                with patch.object(api, "get_test_cases_from_redis", return_value=polygon_cases(4, prefix="old")):
                    api.migrate_test_cases_to_storage("100", db_problem_id=9)
                with patch.object(api, "get_test_cases_from_redis", return_value=polygon_cases(2, prefix="new")):
                    api.migrate_test_cases_to_storage("100", db_problem_id=9)
            storage = LocalStorage(root=self.root)
            keys = storage.list_keys("test_cases/9/")
            self.assertEqual(keys, ["test_cases/9/01", "test_cases/9/01.a", "test_cases/9/02", "test_cases/9/02.a"])
            self.assertEqual(storage.download_bytes("test_cases/9/01"), b"new-input-1\n")

    def test_s3_put_and_read_back_use_the_bucket(self):
        body = MagicMock()
        body.read.return_value = b"in"
        client = MagicMock()
        client.get_object.return_value = {"Body": body}
        client.list_objects_v2.return_value = {"Contents": [{"Key": "test_cases/1/01"}], "IsTruncated": False}
        with patch("problems.storage.s3.boto3.client", return_value=client):
            from problems.storage.s3 import S3CompatibleStorage
            storage = S3CompatibleStorage(
                provider_name="s3",
                bucket="testcases",
                region="us-east-1",
                access_key="key",
                secret_key="secret",
            )
            storage.upload_bytes("test_cases/1/01", b"in")
            self.assertEqual(storage.download_bytes("test_cases/1/01"), b"in")
        client.put_object.assert_called_once_with(Bucket="testcases", Key="test_cases/1/01", Body=b"in")

    @override_settings(POLYGON_API_KEY="test-key", POLYGON_API_SECRET="test-secret")
    def test_polygon_request_retries_rate_limit(self):
        limited = MagicMock(status_code=429, headers={"Retry-After": "0"})
        ok = MagicMock(status_code=200, headers={})
        ok.json.return_value = {"status": "OK", "result": {"name": "A+B"}}
        ok.raise_for_status.return_value = None
        with patch("problems.polygon_api.requests.post", side_effect=[limited, ok]) as post, \
                patch("problems.polygon_api.time.sleep"):
            result = PolygonAPI()._make_request("problem.info", {"problemId": "69927"})
        self.assertEqual(result, {"name": "A+B"})
        self.assertEqual(post.call_count, 2)


class MigrationFlowTests(TestCase):
    def setUp(self):
        self.client = Client()
        user = get_user_model().objects.create_user(
            email="staff@example.com",
            password="password123",
            username="staff",
            first_name="Staff",
            last_name="User",
            contact_number="9999999999",
            college="Test College",
            graduation_year=2024,
            gender="OTHER",
            is_staff=True,
        )
        self.client.force_login(user)

    def _api(self, cases):
        api = MagicMock()
        api.get_problem_info.return_value = {"name": "Two Sum", "timeLimit": 2000, "memoryLimit": 256}
        api.download_and_extract_package.return_value = PROBLEM_HTML
        api.get_test_cases_from_redis.return_value = None
        api.get_all_test_cases.return_value = cases
        api.get_test_cases.return_value = [{"index": case["index"]} for case in cases]
        api.get_custom_checker_info.return_value = None
        api._make_request.side_effect = lambda method, params=None: "std::ncmp.cpp" if method == "problem.checker" else []
        return api

    def _post(self, api, polygon_id, **extra):
        with patch("problems.views.PolygonAPI", return_value=api):
            return self.client.post(reverse("problems:index"), {"problem_id": polygon_id, **extra})

    def test_login_required(self):
        self.client.logout()
        response = self.client.get(reverse("problems:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/users/login/", response.url)

    def test_zero_samples_and_fifteen_regular_tests(self):
        cases = polygon_cases(15, sample_count=0)
        api = self._api(cases)
        created = self._post(api, "501", migrate_to_db="1", difficulty="easy")
        self.assertEqual(created.status_code, 200)
        problem = Problem.objects.get(polygon_id="501")
        self.assertEqual(problem.test_case_count, 15)
        self.assertEqual(SampleTestCase.objects.filter(problem=problem).count(), 0)

        migrated = self._post(api, "501", migrate_test_cases_to_db="1")
        self.assertEqual(migrated.status_code, 200)
        rows = ProblemTestCase.objects.filter(problem=problem)
        self.assertEqual(rows.count(), 15)
        self.assertFalse(rows.filter(is_sample=True).exists())

    def test_remigration_leaves_removed_database_rows(self):
        api = self._api(polygon_cases(20, prefix="old"))
        self._post(api, "502", migrate_to_db="1", difficulty="medium")
        self._post(api, "502", migrate_test_cases_to_db="1")
        problem = Problem.objects.get(polygon_id="502")
        self.assertEqual(ProblemTestCase.objects.filter(problem=problem).count(), 20)

        api.get_all_test_cases.return_value = polygon_cases(12, prefix="new")
        api.get_test_cases.return_value = [{"index": index} for index in range(1, 13)]
        self._post(api, "502", migrate_test_cases_to_db="1")
        rows = list(ProblemTestCase.objects.filter(problem=problem).order_by("order"))
        self.assertEqual(len(rows), 20)
        self.assertTrue(rows[0].input.startswith("new-input-1"))
        self.assertTrue(rows[11].input.startswith("new-input-12"))
        self.assertTrue(rows[12].input.startswith("old-input-13"))
        self.assertTrue(rows[19].input.startswith("old-input-20"))

    def test_same_title_blocks_the_second_problem(self):
        api = self._api(polygon_cases(1))
        first = self._post(api, "601", migrate_to_db="1", difficulty="easy")
        self.assertContains(first, "created in database successfully")
        second = self._post(api, "602", migrate_to_db="1", difficulty="hard")
        self.assertContains(second, "rolled back")
        self.assertFalse(Problem.objects.filter(polygon_id="602").exists())
        self.assertEqual(Problem.objects.get(polygon_id="601").difficulty, "easy")

    def test_database_migration_drops_full_input_and_empty_cases(self):
        cases = [
            {
                "index": 1,
                "manual": False,
                "is_sample": False,
                "description": "keep this description",
                "input": "A" * 300,
                "output": "B" * 280,
            },
            {
                "index": 2,
                "manual": True,
                "is_sample": False,
                "description": "dropped",
                "input": "present",
                "output": "",
            },
        ]
        api = self._api(cases)
        self._post(api, "701", migrate_to_db="1", difficulty="hard")
        response = self._post(api, "701", migrate_test_cases_to_db="1")
        self.assertEqual(response.status_code, 200)
        problem = Problem.objects.get(polygon_id="701")
        rows = list(ProblemTestCase.objects.filter(problem=problem))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].input, "A" * 260)
        self.assertEqual(rows[0].output, "B" * 260)
        self.assertEqual(rows[0].description, "keep this description")
        self.assertEqual(rows[0].order, 1)
        self.assertFalse(hasattr(rows[0], "manual"))
