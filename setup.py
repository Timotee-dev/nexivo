#!/usr/bin/env python3
"""
Nexora Setup Script
Run this ONCE before your first `py manage.py runserver`
Usage: python setup.py
"""
import subprocess, sys, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

def run(cmd, msg):
    print(f"\n▶ {msg}...")
    result = subprocess.run(cmd, shell=True)
    if result.returncode != 0:
        print(f"  ✗ Failed: {cmd}")
        sys.exit(1)
    print(f"  ✓ Done")

print("=" * 52)
print("  ⬡  NEXORA — First-Time Setup")
print("=" * 52)

# Install dependencies
run(f"{sys.executable} -m pip install -r requirements.txt", "Installing dependencies")

# Run migrations
run(f"{sys.executable} manage.py migrate", "Setting up database")

# Seed categories
seed = """
from services.models import Category
cats = [
  ('Beauty & Hair','beauty-hair','✂️'),
  ('Home Cleaning','home-cleaning','🏠'),
  ('Health & Wellness','health-wellness','💊'),
  ('Repairs & Maintenance','repairs','🔧'),
  ('Photography','photography','📸'),
  ('Tutoring & Education','tutoring','📚'),
  ('Catering & Food','catering','🍽️'),
  ('Events & DJ','events','🎵'),
  ('Tech Support','tech','💻'),
  ('Laundry & Ironing','laundry','👕'),
  ('Transport','transport','🚗'),
  ('Security','security','🛡️'),
]
created = 0
for name, slug, emoji in cats:
    _, c = Category.objects.get_or_create(name=name, defaults={'slug': slug, 'emoji': emoji})
    if c: created += 1
print(f'  ✓ {created} categories seeded ({Category.objects.count()} total)')
"""
run(f'{sys.executable} manage.py shell -c "{seed}"', "Seeding categories")

# Create admin user
admin_script = """
from accounts.models import User
if not User.objects.filter(email='admin@nexora.ng').exists():
    u = User.objects.create_superuser(
        username='admin@nexora.ng',
        email='admin@nexora.ng',
        password='nexora123',
        first_name='Platform',
        last_name='Admin',
        role='admin',
    )
    print('  ✓ Admin created: admin@nexora.ng / nexora123')
else:
    print('  ✓ Admin already exists')
"""
run(f'{sys.executable} manage.py shell -c "{admin_script}"', "Creating admin account")

print("\n" + "=" * 52)
print("  🎉 Setup complete!")
print("=" * 52)
print("""
  Start the server:
    python manage.py runserver

  Then open: http://localhost:8000

  ─────────────────────────────────────────────
  Default accounts (change passwords in prod!):
  ─────────────────────────────────────────────
  Admin:    admin@nexora.ng      / nexora123
  ─────────────────────────────────────────────

  Register as Customer or Provider at:
    http://localhost:8000/accounts/register/
    http://localhost:8000/accounts/register/provider/

  Django admin panel:
    http://localhost:8000/admin/

  ─────────────────────────────────────────────
  Payment mode: DEMO (auto-verifies payments)
  To go live: set PAYSTACK_PUBLIC_KEY and
  PAYSTACK_SECRET_KEY in core/settings.py
  ─────────────────────────────────────────────
""")
