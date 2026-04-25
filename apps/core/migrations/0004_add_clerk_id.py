# Generated manually for Clerk integration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_auditlog_before_after'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='clerk_id',
            field=models.CharField(blank=True, db_index=True, help_text='Clerk user ID for external authentication', max_length=255, null=True, unique=True),
        ),
    ]
