from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('custom_account', '0004_authattempt'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='class_name',
            field=models.CharField(max_length=128, blank=True, null=True, help_text='Lớp (ví dụ: 1, 2, 3, 4, 5)'),
        ),
    ]
