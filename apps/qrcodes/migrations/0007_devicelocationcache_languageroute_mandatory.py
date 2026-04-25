from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("qrcodes", "0006_languageroute_geo_direct"),
    ]

    operations = [
        migrations.AddField(
            model_name='languageroute',
            name='mandatory_location',
            field=models.BooleanField(
                default=False,
                help_text='Require GPS on first scan; cache device IP→coords for repeat scans',
            ),
        ),
        migrations.CreateModel(
            name='DeviceLocationCache',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip_address', models.GenericIPAddressField(db_index=True, unique=True)),
                ('latitude', models.FloatField()),
                ('longitude', models.FloatField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'verbose_name': 'Device Location Cache'},
        ),
    ]
