from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0006_contentlibrary'),
    ]

    operations = [
        migrations.AlterField(
            model_name='contentlibrary',
            name='grade_band',
            field=models.CharField(choices=[('Khối 1', 'Khối 1'), ('Khối 2', 'Khối 2'), ('Khối 3', 'Khối 3'), ('Khối 4', 'Khối 4'), ('Khối 5', 'Khối 5')], default='Khối 1', max_length=32),
        ),
    ]
