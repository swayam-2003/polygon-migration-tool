import logging

logger = logging.getLogger(__name__)


class StorageError(Exception):
    """Raised when object storage cannot complete an operation."""


class ObjectStorage:
    """Shared test-case layout for every storage provider.

    Objects are stored as:
        test_cases/{problem_id}/{nn}      input
        test_cases/{problem_id}/{nn}.a    answer
    """

    provider_name = "storage"

    def ensure_ready(self):
        """Create the bucket, container, or directory if the provider can."""

    def upload_bytes(self, key, data):
        raise NotImplementedError

    def download_bytes(self, key):
        raise NotImplementedError

    def delete_prefix(self, prefix):
        raise NotImplementedError

    def list_keys(self, prefix):
        raise NotImplementedError

    @staticmethod
    def input_key(problem_id, test_number):
        return f"test_cases/{problem_id}/{test_number:02d}"

    @staticmethod
    def output_key(problem_id, test_number):
        return f"test_cases/{problem_id}/{test_number:02d}.a"

    def upload_test_case(self, problem_id, test_number, input_data, output_data):
        input_key = self.input_key(problem_id, test_number)
        output_key = self.output_key(problem_id, test_number)
        self.upload_bytes(input_key, input_data.encode("utf-8"))
        self.upload_bytes(output_key, output_data.encode("utf-8"))
        logger.info("Uploaded test case %s to %s and %s", test_number, input_key, output_key)
        return input_key, output_key

    def delete_problem(self, problem_id):
        prefix = f"test_cases/{problem_id}/"
        deleted = self.delete_prefix(prefix)
        logger.info("Deleted %s objects under %s", deleted, prefix)
        return deleted

    def verify_test_cases(self, problem_id, uploaded_cases):
        """Read every uploaded object back and compare it to the source bytes."""
        files = []
        failed = []
        for case in uploaded_cases:
            expected_pairs = (
                (self.input_key(problem_id, case["number"]), case["input"].encode("utf-8")),
                (self.output_key(problem_id, case["number"]), case["output"].encode("utf-8")),
            )
            for key, expected in expected_pairs:
                try:
                    actual = self.download_bytes(key)
                except Exception as exc:
                    failed.append({"key": key, "status": "missing", "detail": str(exc)})
                    files.append({"key": key, "bytes": 0, "status": "missing"})
                    continue
                status = "match" if actual == expected else "mismatch"
                if status != "match":
                    failed.append({
                        "key": key,
                        "status": status,
                        "detail": f"expected {len(expected)} bytes, read {len(actual)} bytes",
                    })
                files.append({"key": key, "bytes": len(actual), "status": status})
        matched = sum(1 for item in files if item["status"] == "match")
        return {
            "verified_count": matched,
            "failed": failed,
            "files": files,
            "object_keys": self.list_keys(f"test_cases/{problem_id}/"),
        }
