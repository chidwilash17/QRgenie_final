from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('forms_builder', '0001_initial'),
    ]

    operations = [
        # Form — respondent identity settings
        migrations.AddField(
            model_name='form',
            name='requires_respondent_info',
            field=models.BooleanField(
                default=False,
                help_text='Collect respondent name + email before showing the form',
            ),
        ),
        migrations.AddField(
            model_name='form',
            name='limit_one_response_per_respondent',
            field=models.BooleanField(
                default=False,
                help_text='Only allow one submission per email address',
            ),
        ),
        # FormSubmission — store collected identity
        migrations.AddField(
            model_name='formsubmission',
            name='respondent_name',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name='formsubmission',
            name='respondent_email',
            field=models.EmailField(blank=True),
        ),
    ]
