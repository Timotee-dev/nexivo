#!/usr/bin/env bash
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate
python -c "
from accounts.models import User
if not User.objects.filter(email='admin@nexivo.ng').exists():
    User.objects.create_superuser(username='admin@nexivo.ng', email='admin@nexivo.ng', password='nexivo123', first_name='Platform', last_name='Admin', role='admin')
    print('Admin created')
from services.models import Category
cats = [('Beauty & Hair','beauty-hair','✂️'),('Home Cleaning','home-cleaning','🏠'),('Health & Wellness','health-wellness','💊'),('Repairs & Maintenance','repairs','🔧'),('Photography','photography','📸'),('Tutoring & Education','tutoring','📚'),('Catering & Food','catering','🍽️'),('Events & DJ','events','🎵'),('Tech Support','tech','💻'),('Laundry & Ironing','laundry','👕'),('Transport','transport','🚗'),('Security','security','🛡️')]
[Category.objects.get_or_create(name=n, defaults={'slug':s,'emoji':e}) for n,s,e in cats]
print('Categories seeded')
"