# ⬡ Nexora — Nigeria's Premier Service Booking Platform

A full-stack Django booking platform. Zero config. Just run it.

---

## ⚡ Quick Start (2 steps)

```bash
# 1. Install & setup (run ONCE)
python setup.py

# 2. Start the server (every time)
python manage.py runserver
```

Open **http://localhost:8000** and you're live. 🚀

---

## 🔑 Default Login

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@nexora.ng | nexora123 |

Register as Customer or Provider at:
- `/accounts/register/` → Customer
- `/accounts/register/provider/` → Provider

---

## 📦 What's Included

| Feature | Details |
|---------|---------|
| **Auth** | Email login, customer + provider registration |
| **Services** | Full CRUD, images, categories, tags, search |
| **Bookings** | Full lifecycle (Pending → Confirmed → Completed) |
| **Payments** | Paystack integration (demo mode out of the box) |
| **Notifications** | In-app bell + dropdown |
| **Dashboards** | Customer, Provider, Admin — all separate |
| **Reviews** | Post-completion reviews with star ratings |
| **Withdrawals** | Provider payout requests + admin approval |
| **Database** | SQLite — no setup required |
| **UI** | Afro-Futurist dark theme, electric violet, fully responsive |

---

## 💳 Payments

**Demo Mode (default)** — payments auto-verify. No Paystack key needed to test the full flow.

**Go Live** — open `core/settings.py` and replace:
```python
PAYSTACK_PUBLIC_KEY = 'pk_test_demo'
```
with your real Paystack keys:
```python
PAYSTACK_PUBLIC_KEY = 'pk_live_xxxx'
PAYSTACK_SECRET_KEY = 'sk_live_xxxx'
```

Get keys at: https://dashboard.paystack.com

---

## 🏗️ Project Structure

```
nexora/
├── core/           → settings, urls, wsgi
├── accounts/       → users, profiles, notifications
├── services/       → listings, categories
├── bookings/       → booking lifecycle, reviews
├── payments/       → Paystack, receipts, withdrawals
├── dashboard/      → all three dashboards
├── templates/      → all HTML templates
├── static/         → css/nx.css, js/nx.js
├── media/          → uploaded images
├── manage.py
├── setup.py        → one-time setup script
└── requirements.txt → django + pillow only
```

---

## 🚀 Deployment (Render / Railway)

1. Push to GitHub
2. Connect repo in Render / Railway
3. Set build command: `python setup.py`
4. Set start command: `gunicorn core.wsgi:application`
5. Add env vars: `SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS`

For production, also switch to PostgreSQL by adding `psycopg2` to requirements and setting `DATABASE_URL`.

---

## ⚙️ Configuration (core/settings.py)

```python
PLATFORM_COMMISSION = 10        # % platform takes from each booking
PAYSTACK_PUBLIC_KEY = 'pk_...'  # Your Paystack key
TIME_ZONE = 'Africa/Lagos'      # Change if needed
```

---

Built with Django 4.2 + ❤️ — made for Nigeria.
