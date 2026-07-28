from django.core.management.base import BaseCommand
from decouple import config


class Command(BaseCommand):
    help = "Create or update the Nexivo super admin account."

    def handle(self, *args, **options):
        from accounts.models import User
        email = config("SUPERADMIN_EMAIL", default="")
        password = config("SUPERADMIN_PASSWORD", default="")

        if not email or not password:
            self.stdout.write("SUPERADMIN_EMAIL or SUPERADMIN_PASSWORD not set. Skipping.")
            return

        user, created = User.objects.get_or_create(
            email=email,
            defaults={"username": "superadmin", "role": "super_admin"}
        )
        user.set_password(password)
        user.is_staff = True
        user.is_superuser = True
        user.role = "super_admin"
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(f"Super admin created: {email}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Super admin updated: {email}"))