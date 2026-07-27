from django.db import migrations


PAYMENT_TABLES = (
    'payments_usersubscription',
    'payments_payment',
    'payments_subscriptionplan',
)


def remove_course_purchase_data(apps, schema_editor):
    SystemConfiguration = apps.get_model('admin_api', 'SystemConfiguration')
    ContentType = apps.get_model('contenttypes', 'ContentType')
    for config in SystemConfiguration.objects.all().iterator():
        data = dict(config.data or {})
        integrations = dict(data.get('integrations') or {})
        if integrations.pop('payments', None) is not None:
            data['integrations'] = integrations
            config.data = data
            config.save(update_fields=['data'])

    existing_tables = set(schema_editor.connection.introspection.table_names())
    for table_name in PAYMENT_TABLES:
        if table_name in existing_tables:
            quoted_name = schema_editor.quote_name(table_name)
            schema_editor.execute(f'DROP TABLE {quoted_name}')

    ContentType.objects.filter(app_label='payments').delete()
    schema_editor.execute(
        'DELETE FROM django_migrations WHERE app = %s',
        params=['payments'],
    )


class Migration(migrations.Migration):
    dependencies = [
        ('content', '0011_course_archived'),
        ('admin_api', '0001_persist_admin_operations'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='course',
            name='price',
        ),
        migrations.RunPython(remove_course_purchase_data, migrations.RunPython.noop),
    ]
