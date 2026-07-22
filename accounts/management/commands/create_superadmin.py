from django.core.management.base import BaseCommand
from decouple import config


class Command(BaseCommand):
    help = "Create the initial Nexivo super admin if none exists."

    def handle(self, *args, **options):
        from accounts.models import User
        email = config("SUPERADMIN_EMAIL", default="admin@nexivo.com")
        password = config("SUPERADMIN_PASSWORD", default="")

        if not password:
            self.stdout.write("SUPERADMIN_PASSWORD is not set. Skipping.")
            return

        if User.objects.filter(email=email).exists():
            self.stdout.write(self.style.WARNING(f"User {email} already exists. Skipping."))
            return

        user = User.objects.create_superuser(email=email, password=password, username="admin")
        self.stdout.write(self.style.SUCCESS(f"Super admin created: {user.email}"))