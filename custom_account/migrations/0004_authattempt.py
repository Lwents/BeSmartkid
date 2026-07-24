import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('custom_account', '0003_rename_custom_acc_user_id_6af29d_idx_custom_acco_user_id_62d7f2_idx'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuthAttempt',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('username_or_email', models.CharField(blank=True, max_length=255)),
                ('success', models.BooleanField(default=False)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True)),
                ('error', models.CharField(blank=True, max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name='auth_attempts', to='custom_account.usermodel')),
            ],
            options={
                'verbose_name': 'Auth Attempt',
                'verbose_name_plural': 'Auth Attempts',
                'ordering': ['-created_at'],
                'indexes': [models.Index(fields=['created_at', 'success'], name='custom_acc_creat_973f90_idx')],
            },
        ),
    ]
