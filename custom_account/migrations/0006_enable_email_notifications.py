from django.db import migrations


def enable_email_notifications(apps, schema_editor):
    Profile = apps.get_model('custom_account', 'Profile')
    for profile in Profile.objects.all().iterator():
        metadata = profile.metadata or {}
        metadata['email_updates'] = True
        metadata['email_notifications_enabled'] = True
        profile.metadata = metadata
        profile.save(update_fields=['metadata'])


class Migration(migrations.Migration):
    dependencies = [
        ('custom_account', '0005_profile_class_name'),
    ]

    operations = [
        migrations.RunPython(enable_email_notifications, migrations.RunPython.noop),
    ]
