from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create or update a staff user who can log in to the migration screen."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="staff@example.com")
        parser.add_argument("--password", default="changeme-staff")
        parser.add_argument("--username", default="staff")

    def handle(self, *args, **options):
        user_model = get_user_model()
        email = options["email"]
        defaults = {
            "username": options["username"],
            "first_name": "Staff",
            "last_name": "User",
            "contact_number": "0000000000",
            "college": "Local",
            "graduation_year": 2024,
            "gender": "OTHER",
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
        }
        user, created = user_model.objects.get_or_create(email=email, defaults=defaults)
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(options["password"])
        user.save()
        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} staff user {email}"))
        self.stdout.write("Log in at /users/login/ with that email and password.")
