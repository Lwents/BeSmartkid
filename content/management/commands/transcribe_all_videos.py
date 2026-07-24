"""
Django management command để transcribe tất cả video chưa có transcript.
Usage: python manage.py transcribe_all_videos
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from content.models import Lesson
from content.services.video_transcriber import video_transcriber
from content.utils.storage_utils import local_path_from_storage
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Transcribe tất cả video chưa có transcript cho các lesson đã tạo trước đó'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help='Giới hạn số lượng lesson cần transcribe (mặc định: tất cả)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Chỉ hiển thị danh sách, không thực sự transcribe'
        )
    
    def handle(self, *args, **options):
        limit = options.get('limit')
        dry_run = options.get('dry_run', False)
        
        # Tìm tất cả lesson có video nhưng chưa có transcript
        lessons_with_video_url = Lesson.objects.filter(
            video_url__isnull=False
        ).exclude(
            video_url=''
        ).filter(
            video_transcript__isnull=True
        ) | Lesson.objects.filter(
            video_url__isnull=False
        ).exclude(
            video_url=''
        ).filter(
            video_transcript=''
        )
        
        lessons_with_video_file = Lesson.objects.filter(
            video_file__isnull=False
        ).exclude(
            video_file=''
        ).filter(
            video_transcript__isnull=True
        ) | Lesson.objects.filter(
            video_file__isnull=False
        ).exclude(
            video_file=''
        ).filter(
            video_transcript=''
        )
        
        # Combine và loại bỏ duplicate
        all_lessons = (lessons_with_video_url | lessons_with_video_file).distinct()
        
        if limit:
            all_lessons = all_lessons[:limit]
        
        total = all_lessons.count()
        
        if total == 0:
            self.stdout.write(self.style.SUCCESS('Không có lesson nào cần transcribe!'))
            return
        
        self.stdout.write(f'Tìm thấy {total} lesson cần transcribe:')
        for lesson in all_lessons:
            video_source = lesson.video_url if lesson.video_url else f'File: {lesson.video_file}'
            self.stdout.write(f'  - {lesson.title} (ID: {lesson.id}) - {video_source}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY RUN: Không thực sự transcribe. Bỏ --dry-run để thực hiện.'))
            return
        
        self.stdout.write(f'\nBắt đầu transcribe {total} lesson...')
        
        success_count = 0
        failed_count = 0
        
        for idx, lesson in enumerate(all_lessons, 1):
            self.stdout.write(f'\n[{idx}/{total}] Đang transcribe: {lesson.title}...')
            
            try:
                transcript = None
                
                if lesson.video_file:
                    with local_path_from_storage(str(lesson.video_file)) as video_path:
                        transcript = video_transcriber.transcribe_video(video_path=video_path) if video_path else None
                elif lesson.video_url:
                    transcript = video_transcriber.transcribe_video(video_url=lesson.video_url)
                
                if transcript:
                    lesson.video_transcript = transcript
                    lesson.save(update_fields=['video_transcript'])
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'  ✓ Đã transcribe thành công! ({len(transcript)} ký tự)'
                        )
                    )
                    success_count += 1
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f'  ✗ Không thể tạo transcript (có thể do lỗi API hoặc video không có phụ đề)'
                        )
                    )
                    failed_count += 1
                    
            except Exception as e:
                logger.error(f"Error transcribing lesson {lesson.id}: {e}")
                self.stdout.write(
                    self.style.ERROR(f'  ✗ Lỗi: {str(e)}')
                )
                failed_count += 1
        
        self.stdout.write(
            self.style.SUCCESS(
                f'\n✓ Hoàn thành! Thành công: {success_count}, Thất bại: {failed_count}, Tổng: {total}'
            )
        )










