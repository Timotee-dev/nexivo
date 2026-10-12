from django.db import migrations
import uuid


CATEGORIES = [
    # (name, slug, icon, description, display_order)
    ("Concerts & Music",    "concerts",     "🎵", "Live music performances, concerts, and gigs.",          1),
    ("Parties & Nightlife", "parties",      "🎉", "Club nights, celebrations, and social events.",         2),
    ("Festivals",           "festivals",    "🎪", "Cultural festivals, outdoor events, and carnivals.",    3),
    ("Comedy Shows",        "comedy",       "🎤", "Stand-up comedy, open mics, and comedy nights.",        4),
    ("Conferences",         "conferences",  "💼", "Business conferences, summits, and professional events.",5),
    ("Workshops",           "workshops",    "🎓", "Training, skill-building workshops, and seminars.",     6),
    ("Sports & Fitness",    "sports",       "⚽", "Sporting events, fitness challenges, and tournaments.", 7),
    ("Arts & Culture",      "arts",         "🎨", "Art exhibitions, theatre, and cultural experiences.",  8),
    ("Food & Drinks",       "food",         "🍽️", "Food festivals, tastings, and dining experiences.",    9),
    ("Tech & Innovation",   "tech",         "💻", "Tech meetups, hackathons, and product launches.",       10),
    ("Fashion & Beauty",    "fashion",      "👗", "Fashion shows, beauty events, and style exhibitions.", 11),
    ("Weddings & Socials",  "weddings",     "💍", "Wedding receptions, engagement parties, and socials.", 12),
    ("Church & Religious",  "church",       "⛪", "Church services, crusades, and religious gatherings.", 13),
    ("Health & Wellness",   "health",       "💪", "Health talks, wellness retreats, and fitness events.", 14),
    ("Education",           "education",    "📚", "Academic events, lectures, and educational programs.", 15),
    ("Networking",          "networking",   "🤝", "Networking mixers, meetups, and professional socials.",16),
    ("Kids & Family",       "family",       "👨‍👩‍👧", "Family-friendly events, children's activities, and shows.", 17),
    ("Other",               "other",        "✦",  "Events that don't fit into any other category.",       18),
]


def seed_categories(apps, schema_editor):
    Category = apps.get_model("events", "Category")
    for name, slug, icon, description, order in CATEGORIES:
        Category.objects.get_or_create(
            slug=slug,
            defaults={
                "id": uuid.uuid4(),
                "name": name,
                "icon": icon,
                "description": description,
                "display_order": order,
                "is_active": True,
            }
        )


def unseed_categories(apps, schema_editor):
    Category = apps.get_model("events", "Category")
    slugs = [row[1] for row in CATEGORIES]
    Category.objects.filter(slug__in=slugs).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0003_event_marketer_referral_code"),
    ]

    operations = [
        migrations.RunPython(seed_categories, reverse_code=unseed_categories),
    ]
