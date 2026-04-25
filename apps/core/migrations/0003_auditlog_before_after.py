from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_add_allowed_domains'),
    ]

    operations = [
        migrations.AddField(
            model_name='auditlog',
            name='before',
            field=models.JSONField(blank=True, help_text='Resource state before the action', null=True),
        ),
        migrations.AddField(
            model_name='auditlog',
            name='after',
            field=models.JSONField(blank=True, help_text='Resource state after the action', null=True),
        ),
    ]
