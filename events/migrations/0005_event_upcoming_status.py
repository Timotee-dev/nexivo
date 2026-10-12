from django.db import migrations
import django.db.models.fields


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0004_seed_categories"),
    ]

    operations = [
        migrations.AlterField(
            model_name="event",
            name="status",
            field=django.db.models.fields.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("pending_review", "Pending Review"),
                    ("upcoming", "Upcoming"),
                    ("published", "Published"),
                    ("suspended", "Suspended"),
                    ("cancelled", "Cancelled"),
                    ("completed", "Completed"),
                ],
                db_index=True,
                default="draft",
                max_length=20,
            ),
        ),
    ]
