from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase


class CreateStaffUserTests(TestCase):
    def test_command_creates_a_staff_user_who_can_authenticate(self):
        call_command("create_staff_user", email="reviewer@example.com", password="reviewer-pass", username="reviewer")
        user = get_user_model().objects.get(email="reviewer@example.com")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.check_password("reviewer-pass"))

        call_command("create_staff_user", email="reviewer@example.com", password="second-pass", username="reviewer")
        user.refresh_from_db()
        self.assertTrue(user.check_password("second-pass"))
        self.assertEqual(get_user_model().objects.filter(email="reviewer@example.com").count(), 1)
