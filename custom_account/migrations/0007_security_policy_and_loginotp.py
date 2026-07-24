from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('custom_account', '0006_enable_email_notifications'),
    ]

    operations = [
        migrations.AddField(
            model_name='usermodel',
            name='failed_login_count',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='usermodel',
            name='last_failed_login_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='usermodel',
            name='lockout_until',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='usermodel',
            name='lockout_strikes',
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.CreateModel(
            name='SecurityPolicy',
            fields=[
                ('id', models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ('twofa_enforce_admin', models.BooleanField(default=False)),
                ('twofa_enforce_teacher', models.BooleanField(default=False)),
                ('rate_limit_login_failures', models.PositiveSmallIntegerField(default=5)),
                ('rate_limit_window_min', models.PositiveSmallIntegerField(default=10)),
                ('lockout_attempts', models.PositiveSmallIntegerField(default=5)),
                ('lockout_minutes', models.PositiveSmallIntegerField(default=30)),
                ('lockout_ban_strikes', models.PositiveSmallIntegerField(default=5)),
                ('rbac_note', models.TextField(blank=True, default='')),
            ],
            options={
                'verbose_name': 'Security Policy',
                'verbose_name_plural': 'Security Policies',
            },
        ),
        migrations.CreateModel(
            name='LoginOTP',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code_hash', models.CharField(max_length=128)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('expires_at', models.DateTimeField()),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('is_used', models.BooleanField(default=False)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='login_otps', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['user', '-created_at'], name='custom_acc_user_id_ba0b61_idx')],
            },
        ),
    ]
