from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sessions_app", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="supportsession",
            index=models.Index(
                fields=["created_by", "-created_at"],
                name="sc_session_creator_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="supportsession",
            index=models.Index(
                fields=["status", "expires_at"],
                name="sc_session_status_exp_idx",
            ),
        ),
    ]
