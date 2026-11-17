import uuid

from django.core.management.base import BaseCommand, CommandError

from problems.storage.base import StorageError
from problems.storage.factory import get_storage, get_storage_label


class Command(BaseCommand):
    help = "Upload two sample test cases to the configured storage provider, read them back, then delete them."

    def handle(self, *args, **options):
        problem_id = f"verify-{uuid.uuid4().hex[:8]}"
        cases = [
            {"number": 1, "input": "2\n1 2\n", "output": "3\n"},
            {"number": 2, "input": "1\n5\n", "output": "5\n"},
        ]
        storage = get_storage()
        self.stdout.write(f"Provider: {get_storage_label()} ({storage.provider_name})")
        try:
            storage.ensure_ready()
            storage.delete_problem(problem_id)
            for case in cases:
                storage.upload_test_case(problem_id, case["number"], case["input"], case["output"])
            report = storage.verify_test_cases(problem_id, cases)
        except StorageError as exc:
            raise CommandError(str(exc)) from exc
        finally:
            try:
                storage.delete_problem(problem_id)
            except Exception as exc:
                self.stderr.write(f"Cleanup failed for {problem_id}: {exc}")

        for item in report["files"]:
            self.stdout.write(f"{item['status']}: {item['key']} ({item['bytes']} bytes)")
        if report["failed"]:
            raise CommandError(f"Verification failed for {len(report['failed'])} object(s).")
        self.stdout.write(self.style.SUCCESS(
            f"Verified {report['verified_count']} objects, then deleted the temporary prefix."
        ))
