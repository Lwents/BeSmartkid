# Generated manually for new lesson content type fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0007_alter_contentlibrary_grade_band'),
    ]

    operations = [
        migrations.AddField(
            model_name='lesson',
            name='document_file',
            field=models.FileField(blank=True, help_text='File tài liệu (PDF, DOCX)', null=True, upload_to='lesson_documents/'),
        ),
        migrations.AddField(
            model_name='lesson',
            name='text_content',
            field=models.TextField(blank=True, help_text='Nội dung văn bản', null=True),
        ),
        migrations.AlterField(
            model_name='lesson',
            name='content_type',
            field=models.CharField(choices=[('lesson', 'Lesson'), ('exploration', 'Exploration'), ('exercise', 'Exercise'), ('video', 'Video'), ('pdf', 'PDF'), ('text', 'Text'), ('document', 'Document')], default='lesson', max_length=32),
        ),
    ]
