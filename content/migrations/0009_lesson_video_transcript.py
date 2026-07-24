# Generated manually for video_transcript field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0008_lesson_document_file_lesson_text_content_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='lesson',
            name='video_transcript',
            field=models.TextField(blank=True, help_text='Nội dung lời thoại/phụ đề video để AI hiểu ngữ cảnh', null=True),
        ),
    ]
