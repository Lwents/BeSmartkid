from django.apps import AppConfig
import threading
import logging

logger = logging.getLogger(__name__)


class ContentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'content'
    _auto_transcribe_started = False

    def ready(self):
        import content.signals  # noqa
        
        # Tự động quét và transcribe video còn thiếu khi server khởi động
        # Chỉ chạy một lần để tránh chạy nhiều lần khi reload
        if not ContentConfig._auto_transcribe_started:
            ContentConfig._auto_transcribe_started = True
            self._start_auto_transcribe_background()

    def _start_auto_transcribe_background(self):
        """Chạy auto-transcribe trong background thread để không block server startup"""
        def auto_transcribe_all_videos():
            try:
                # Đợi một chút để đảm bảo database đã sẵn sàng
                import time
                time.sleep(5)
                
                from content.models import Lesson
                from content.services.video_transcriber import video_transcriber
                
                # Tìm tất cả lesson có video nhưng chưa có transcript
                from django.db.models import Q
                
                lessons_with_video_url = Lesson.objects.filter(
                    video_url__isnull=False
                ).exclude(video_url='').filter(
                    Q(video_transcript__isnull=True) | Q(video_transcript='')
                )
                
                lessons_with_video_file = Lesson.objects.filter(
                    video_file__isnull=False
                ).exclude(video_file='').filter(
                    Q(video_transcript__isnull=True) | Q(video_transcript='')
                )
                
                all_lessons = (lessons_with_video_url | lessons_with_video_file).distinct()
                total = all_lessons.count()
                
                if total > 0:
                    logger.info(f"Auto-transcribe: Tìm thấy {total} video chưa có transcript, bắt đầu transcribe...")
                    
                    for idx, lesson in enumerate(all_lessons, 1):
                        try:
                            # Refresh từ DB để đảm bảo có dữ liệu mới nhất
                            lesson.refresh_from_db()
                            
                            # Kiểm tra lại xem đã có transcript chưa (có thể đã được transcribe bởi process khác)
                            if lesson.video_transcript and lesson.video_transcript.strip():
                                logger.info(f"Auto-transcribe: Lesson {lesson.id} đã có transcript, bỏ qua")
                                continue
                            
                            logger.info(f"Auto-transcribe: Đang transcribe lesson {lesson.id} ({idx}/{total})...")
                            
                            # Transcribe
                            transcript = None
                            if lesson.video_file:
                                from content.utils.storage_utils import local_path_from_storage
                                with local_path_from_storage(str(lesson.video_file)) as video_path:
                                    if not video_path:
                                        continue
                                    transcript = video_transcriber.transcribe_video(video_path=video_path)
                            elif lesson.video_url:
                                transcript = video_transcriber.transcribe_video(video_url=lesson.video_url)
                            
                            # Lưu transcript nếu có
                            if transcript:
                                lesson.video_transcript = transcript
                                lesson.save(update_fields=['video_transcript'])
                                logger.info(f"Auto-transcribe: Đã transcribe lesson {lesson.id} ({idx}/{total}) - {len(transcript)} ký tự")
                            else:
                                logger.warning(f"Auto-transcribe: Không thể transcribe lesson {lesson.id} ({idx}/{total})")
                                
                        except Exception as e:
                            logger.error(f"Auto-transcribe: Lỗi khi transcribe lesson {lesson.id}: {e}", exc_info=True)
                    
                    logger.info(f"Auto-transcribe: Hoàn tất! Đã xử lý {total} video")
                else:
                    logger.info("Auto-transcribe: Tất cả video đã có transcript")
                    
            except Exception as e:
                logger.error(f"Auto-transcribe: Lỗi khi quét video: {e}", exc_info=True)
        
        # Chạy trong daemon thread để không block server shutdown
        thread = threading.Thread(target=auto_transcribe_all_videos, daemon=True)
        thread.start()
        logger.info("Auto-transcribe: Đã khởi động background thread để quét và transcribe video")
