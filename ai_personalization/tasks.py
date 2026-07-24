# ai_personalization/tasks.py
"""
Celery tasks for async processing of heavy AI computations.
"""
from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone
from typing import List
import logging
import numpy as np

logger = logging.getLogger(__name__)
User = get_user_model()

# ... existing code ...

@shared_task
def auto_restore_streak_and_award_badges():
    """
    Tự động khôi phục streak khi mất và còn lượt khôi phục
    Tạo badges khi streak mất và bắt đầu lại
    Chạy mỗi ngày lúc 0:00 (sau khi streak được tính lại)
    """
    from custom_account.models import UserModel as User
    from content.models import LessonProgress
    from activities.models import ExerciseAttempt
    from gamification.models import GameSession, Badge, UserBadge
    from ai_personalization.models import StreakRestoration
    from django.db.models import Q
    from datetime import timedelta, datetime
    
    today = timezone.localdate()
    yesterday = today - timedelta(days=1)
    
    # Lấy tất cả học sinh
    students = User.objects.filter(role='student', is_active=True).select_related('profile')
    
    restored_count = 0
    badge_count = 0
    
    for student in students:
        try:
            # Tính streak hiện tại
            from activities.models import ExerciseAttempt
            from gamification.models import GameSession
            
            streak = 0
            check_date = today
            while streak < 365:
                has_lesson = LessonProgress.objects.filter(
                    student=student
                ).filter(
                    Q(completed=True) | Q(video_watched=True)
                ).filter(
                    Q(completed_at__date=check_date) | Q(last_accessed_at__date=check_date)
                ).exists()
                
                has_exercise = ExerciseAttempt.objects.filter(
                    student=student,
                    finished_at__date=check_date
                ).exists()
                
                has_game = GameSession.objects.filter(
                    player=student,
                    completed=True,
                    completed_at__date=check_date
                ).exists()
                
                if has_lesson or has_exercise or has_game:
                    streak += 1
                    check_date -= timedelta(days=1)
                else:
                    break
            
            # Kiểm tra hôm qua có hoạt động không
            yesterday_has_activity = (
                LessonProgress.objects.filter(
                    student=student
                ).filter(
                    Q(completed=True) | Q(video_watched=True)
                ).filter(
                    Q(completed_at__date=yesterday) | Q(last_accessed_at__date=yesterday)
                ).exists() or
                ExerciseAttempt.objects.filter(
                    student=student,
                    finished_at__date=yesterday
                ).exists() or
                GameSession.objects.filter(
                    player=student,
                    completed=True,
                    completed_at__date=yesterday
                ).exists()
            )
            
            # Nếu streak = 0 và có thể khôi phục
            was_restored = False
            if streak == 0 and StreakRestoration.can_restore(student) and yesterday_has_activity:
                # Tính streak trước khi mất (hôm qua)
                previous_streak = 0
                check_date = yesterday
                while previous_streak < 365:
                    has_lesson = LessonProgress.objects.filter(
                        student=student
                    ).filter(
                        Q(completed=True) | Q(video_watched=True)
                    ).filter(
                        Q(completed_at__date=check_date) | Q(last_accessed_at__date=check_date)
                    ).exists()
                    
                    has_exercise = ExerciseAttempt.objects.filter(
                        student=student,
                        finished_at__date=check_date
                    ).exists()
                    
                    has_game = GameSession.objects.filter(
                        player=student,
                        completed=True,
                        completed_at__date=check_date
                    ).exists()
                    
                    if has_lesson or has_exercise or has_game:
                        previous_streak += 1
                        check_date -= timedelta(days=1)
                    else:
                        break
                
                # Nếu có streak để khôi phục (>= 1)
                if previous_streak >= 1:
                    # Tự động khôi phục
                    month_year = today.strftime('%Y-%m')
                    restoration = StreakRestoration.objects.create(
                        user=student,
                        month_year=month_year,
                        restored_streak_value=previous_streak,
                        restored_at=timezone.now()
                    )
                    
                    # Tạo hoặc cập nhật LessonProgress để khôi phục streak
                    last_progress = LessonProgress.objects.filter(
                        student=student
                    ).filter(
                        Q(completed=True) | Q(video_watched=True)
                    ).order_by('-last_accessed_at').first()
                    
                    if last_progress:
                        yesterday_datetime = timezone.make_aware(
                            datetime.combine(yesterday, datetime.min.time().replace(hour=12))
                        )
                        last_progress.last_accessed_at = yesterday_datetime
                        if not last_progress.completed_at:
                            last_progress.completed_at = yesterday_datetime
                        last_progress.save(update_fields=['last_accessed_at', 'completed_at'])
                    
                    was_restored = True
                    restored_count += 1
                    logger.info(f"Auto-restored streak {previous_streak} for {student.username}")
            
            # Tạo badge khi streak mất (chỉ khi không được auto-restore)
            if streak == 0 and yesterday_has_activity and not was_restored:
                # Tạo badge "Streak mất" nếu chưa có
                badge, created = Badge.objects.get_or_create(
                    name='streak_lost',
                    defaults={
                        'description': 'Đã mất streak nhưng không sao, hãy bắt đầu lại!',
                        'icon_url': '🔥',
                        'criteria': {'type': 'streak_lost'}
                    }
                )
                
                if not UserBadge.objects.filter(user=student, badge=badge).exists():
                    UserBadge.objects.create(
                        user=student,
                        badge=badge,
                        metadata={'streak_lost_date': str(yesterday), 'auto_awarded': True}
                    )
                    badge_count += 1
                    logger.info(f"Awarded 'streak_lost' badge to {student.username}")
            
            # Tạo badge khi bắt đầu streak mới (streak = 1 và hôm qua không có hoạt động)
            if streak == 1 and not yesterday_has_activity:
                badge, created = Badge.objects.get_or_create(
                    name='streak_reborn',
                    defaults={
                        'description': 'Bắt đầu streak mới! Hãy giữ lửa!',
                        'icon_url': '🌱',
                        'criteria': {'type': 'streak_reborn'}
                    }
                )
                
                if not UserBadge.objects.filter(user=student, badge=badge).exists():
                    UserBadge.objects.create(
                        user=student,
                        badge=badge,
                        metadata={'streak_started_date': str(today), 'auto_awarded': True}
                    )
                    badge_count += 1
                    logger.info(f"Awarded 'streak_reborn' badge to {student.username}")
        except Exception as e:
            logger.error(f"Error processing auto-restore/badge for {student.id}: {e}", exc_info=True)
    
    logger.info(f"Auto-restored {restored_count} streaks and awarded {badge_count} badges")
    return {'restored': restored_count, 'badges': badge_count}


@shared_task
def send_streak_warning_notifications():
    """
    Gửi cảnh báo streak sắp mất (2-3 tiếng trước 23:59)
    Chạy mỗi giờ để kiểm tra và gửi cho các user cần cảnh báo
    """
    from activities.models import Notification, NotificationLog
    from content.models import LessonProgress
    from django.db.models import Q
    from datetime import timedelta
    
    # Lấy thời gian hiện tại theo timezone local
    now = timezone.now()
    local_now = timezone.localtime(now)
    current_hour = local_now.hour
    
    # Chỉ chạy vào khoảng 21:00-22:00 (2-3 tiếng trước 23:59)
    # Tạm thời comment để test (có thể bỏ comment khi deploy production)
    # if current_hour < 21 or current_hour >= 23:
    #     return
    
    today = timezone.localdate()
    
    # Lấy tất cả học sinh có enrollment
    students = User.objects.filter(
        role='student',
        is_active=True
    ).select_related('profile')
    
    sent_count = 0
    
    for student in students:
        try:
            # Kiểm tra notifications_enabled
            profile = getattr(student, 'profile', None)
            if not profile:
                continue
            
            # Lấy setting từ metadata, mặc định True
            notifications_enabled = profile.metadata.get('notifications_enabled', True)
            if not notifications_enabled:
                continue
            
            # Tính streak hiện tại (bao gồm bài học, bài tập, bài kiểm tra, trò chơi)
            from activities.models import ExerciseAttempt
            from gamification.models import GameSession
            
            streak = 0
            check_date = today
            while streak < 365:
                has_lesson = LessonProgress.objects.filter(
                    student=student
                ).filter(
                    Q(completed=True) | Q(video_watched=True)
                ).filter(
                    Q(completed_at__date=check_date) | Q(last_accessed_at__date=check_date)
                ).exists()
                
                has_exercise = ExerciseAttempt.objects.filter(
                    student=student,
                    finished_at__date=check_date
                ).exists()
                
                has_game = GameSession.objects.filter(
                    player=student,
                    completed=True,
                    completed_at__date=check_date
                ).exists()
                
                if has_lesson or has_exercise or has_game:
                    streak += 1
                    check_date -= timedelta(days=1)
                else:
                    break
            
            # Điều kiện: streak >= 2 và chưa đạt daily goal hôm nay
            if streak < 2:
                logger.debug(f"User {student.username}: streak {streak} < 2, skip")
                continue
            
            # Kiểm tra xem đã đạt daily goal hôm nay chưa (bao gồm bài học, bài tập, bài kiểm tra, trò chơi)
            lessons_completed = LessonProgress.objects.filter(
                student=student
            ).filter(
                Q(completed=True) | Q(video_watched=True)
            ).filter(
                Q(completed_at__date=today) | Q(last_accessed_at__date=today)
            ).distinct().count()
            
            exercises_completed = ExerciseAttempt.objects.filter(
                student=student,
                finished_at__date=today
            ).distinct().count()
            
            games_completed = GameSession.objects.filter(
                player=student,
                completed=True,
                completed_at__date=today
            ).distinct().count()
            
            completed_today = lessons_completed + exercises_completed + games_completed
            
            target = 2  # Daily goal
            if completed_today >= target:
                logger.debug(f"User {student.username}: completed_today {completed_today} >= {target}, skip")
                continue  # Đã đạt goal, không cần cảnh báo
            
            # Kiểm tra xem đã gửi STREAK_WARNING trong ngày chưa
            already_sent = NotificationLog.objects.filter(
                user=student,
                notification_type='streak_warning',
                sent_date=today
            ).exists()
            
            if already_sent:
                logger.debug(f"User {student.username}: already sent today, skip")
                continue
            
            logger.info(f"User {student.username}: Eligible - streak={streak}, completed_today={completed_today}/{target}")
            
            # Tạo nội dung notification bằng AI
            try:
                from .ai_tutor import AITutorEngine
                ai_tutor = AITutorEngine()
                
                # Lấy thông tin học sinh để cá nhân hóa
                student_name = profile.display_name if profile else student.username
                student_grade = profile.metadata.get('grade', 1) if profile else 1
                
                # Tạo prompt cho AI
                ai_prompt = f"""Tạo một câu cảnh báo ngắn gọn (1-2 câu, tối đa 50 từ) để nhắc học sinh sắp mất streak.

Thông tin:
- Tên học sinh: {student_name}
- Lớp: {student_grade}
- Streak hiện tại: {streak} ngày
- Đã hoàn thành hôm nay: {completed_today}/{target} bài

Yêu cầu:
- Ngôn ngữ đơn giản, phù hợp học sinh lớp {student_grade}
- Khẩn trương nhưng vui vẻ, khích lệ
- Thêm 1-2 emoji phù hợp (🔥, ⚡, 💪)
- Không quá dài, đi thẳng vào vấn đề
- Xưng "mình", gọi học sinh là "bạn" hoặc "em"

Trả lời theo format:
TITLE: [tiêu đề ngắn, có emoji]
MESSAGE: [nội dung cảnh báo]"""
                
                ai_result = ai_tutor.chat(
                    user_message=ai_prompt,
                    context={},
                    conversation_history=[],
                    student_grade=student_grade
                )
                
                if ai_result.get('success') and ai_result.get('message'):
                    ai_response = ai_result['message']
                    # Parse response để lấy title và message
                    lines = ai_response.split('\n')
                    title = None
                    message = None
                    
                    for line in lines:
                        if line.strip().startswith('TITLE:'):
                            title = line.replace('TITLE:', '').strip()
                        elif line.strip().startswith('MESSAGE:'):
                            message = line.replace('MESSAGE:', '').strip()
                    
                    # Fallback nếu không parse được
                    if not title or not message:
                        message = ai_response.strip()
                        title = f'🔥 Cảnh báo: Sắp mất streak {streak} ngày!'
                else:
                    raise Exception("AI response failed")
            except Exception as e:
                logger.warning(f"AI generation failed for {student.id}, using fallback: {e}")
                # Fallback messages
                title = f'🔥 Cảnh báo: Sắp mất streak {streak} ngày!'
                message = f'Bạn sắp mất chuỗi học {streak} ngày rồi! Vào học 1 bài nhanh để giữ streak nào 🔥'
            
            # Gửi notification
            Notification.objects.create(
                user=student,
                title=title,
                message=message,
                type='warning',
                category='streak_warning',
                metadata={
                    'streak': streak,
                    'completed_today': completed_today,
                    'target': target,
                }
            )
            
            # Log notification
            NotificationLog.objects.create(
                user=student,
                notification_type='streak_warning',
                sent_date=today,
                metadata={'streak': streak}
            )
            
            sent_count += 1
        except Exception as e:
            logger.error(f"Error sending streak warning to {student.id}: {e}")

    logger.info(f"Sent {sent_count} streak warning notifications")
    return sent_count


@shared_task
def send_comeback_reminders():
    """
    Gửi nhắc nhở quay lại sau khi bỏ dở (1, 3, 7 ngày)
    Chạy mỗi ngày một lần
    """
    from activities.models import Notification, NotificationLog
    from content.models import LessonProgress
    from django.db.models import Q
    from datetime import timedelta
    
    today = timezone.localdate()
    reminder_days = [1, 3, 4, 5, 7, 14, 21, 30]  # Các mốc ngày cần nhắc (1, 3, 4, 5, 7, 14, 21, 30 ngày)
    
    # Lấy tất cả học sinh có enrollment
    students = User.objects.filter(
        role='student',
        is_active=True
    ).select_related('profile')
    
    sent_count = 0
    
    for student in students:
        try:
            # Kiểm tra notifications_enabled
            profile = getattr(student, 'profile', None)
            if not profile:
                logger.debug(f"Student {student.id} has no profile, skipping")
                continue
            
            notifications_enabled = profile.metadata.get('notifications_enabled', True)
            if not notifications_enabled:
                logger.debug(f"Student {student.id} has notifications disabled, skipping")
                continue
            
            # Tìm ngày học gần nhất - lấy theo last_accessed_at mới nhất
            # Vì last_accessed_at phản ánh hoạt động gần nhất của học sinh
            last_progress = LessonProgress.objects.filter(
                student=student
            ).filter(
                Q(completed=True) | Q(video_watched=True)
            ).order_by('-last_accessed_at', '-completed_at').first()
            
            if not last_progress:
                # Chưa học bao giờ - không gửi comeback reminder
                continue
            
            # Lấy ngày học gần nhất từ last_accessed_at (phản ánh hoạt động gần nhất)
            last_date = None
            if last_progress.last_accessed_at:
                last_date = last_progress.last_accessed_at.date()
            elif last_progress.completed_at:
                last_date = last_progress.completed_at.date()
            
            if not last_date:
                continue
            
            # Tính số ngày đã bỏ dở
            days_missed = (today - last_date).days
            
            if days_missed <= 0:
                continue  # Đã học hôm nay hoặc tương lai
            
            # Kiểm tra xem có phải mốc cần nhắc không
            if days_missed not in reminder_days:
                logger.debug(f"Student {student.id}: days_missed={days_missed} not in reminder_days, skipping")
                continue
            
            logger.info(f"Student {student.id}: Processing comeback reminder for {days_missed} days missed")
            
            # Xác định notification type
            notification_type = f'comeback_{days_missed}day'
            
            # Kiểm tra xem đã gửi notification này chưa (mỗi mốc chỉ gửi 1 lần)
            already_sent = NotificationLog.objects.filter(
                user=student,
                notification_type=notification_type
            ).exists()
            
            if already_sent:
                continue
            
            # Tạo nội dung notification bằng AI
            try:
                from .ai_tutor import AITutorEngine
                ai_tutor = AITutorEngine()
        
                # Lấy thông tin học sinh để cá nhân hóa
                student_name = profile.display_name or student.username
                student_grade = profile.metadata.get('grade', 1) or 1
                
                # Tạo prompt cho AI
                ai_prompt = f"""Tạo một câu động viên ngắn gọn (1-2 câu, tối đa 50 từ) để khuyến khích học sinh quay lại học tập.

Thông tin:
- Tên học sinh: {student_name}
- Lớp: {student_grade}
- Đã bỏ dở: {days_missed} ngày
- Lần cuối học: {last_date}

Yêu cầu:
- Ngôn ngữ đơn giản, phù hợp học sinh lớp {student_grade}
- Vui vẻ, ấm áp, khích lệ
- Thêm 1-2 emoji phù hợp
- Không quá dài, đi thẳng vào vấn đề
- Xưng "mình", gọi học sinh là "bạn" hoặc "em"

Trả lời theo format:
TITLE: [tiêu đề ngắn, có emoji]
MESSAGE: [nội dung động viên]"""
                
                ai_result = ai_tutor.chat(
                    user_message=ai_prompt,
                    context={},
                    conversation_history=[],
                    student_grade=student_grade
                )
                
                if ai_result.get('success') and ai_result.get('message'):
                    ai_response = ai_result['message']
                    # Parse response để lấy title và message
                    lines = ai_response.split('\n')
                    title = None
                    message = None
                    
                    for line in lines:
                        if line.strip().startswith('TITLE:'):
                            title = line.replace('TITLE:', '').strip()
                        elif line.strip().startswith('MESSAGE:'):
                            message = line.replace('MESSAGE:', '').strip()
                
                    # Fallback nếu không parse được
                    if not title or not message:
                        # Dùng AI response làm message, tạo title mặc định
                        message = ai_response.strip()
                        if days_missed == 1:
                            title = '📚 Hôm qua bạn bỏ lỡ bài học rồi!'
                        elif days_missed == 3:
                            title = '💪 Đã 3 ngày rồi từ lần cuối bạn học'
                        elif days_missed == 4:
                            title = '📖 Đã 4 ngày rồi, đừng bỏ cuộc nhé!'
                        elif days_missed == 5:
                            title = '🎯 Đã 5 ngày rồi, quay lại thôi!'
                        elif days_missed == 7:
                            title = '🌟 Đã 1 tuần rồi, quay lại thôi!'
                        elif days_missed == 14:
                            title = '📅 Đã 2 tuần rồi, đừng quên học tập nhé!'
                        elif days_missed == 21:
                            title = '⏳ Đã 3 tuần rồi, quay lại học thôi!'
                        elif days_missed == 30:
                            title = '🗓️ Đã 1 tháng rồi, quay lại học tập nhé!'
                        else:
                            title = f'📚 Đã {days_missed} ngày rồi từ lần cuối bạn học'
                else:
                    # Fallback nếu AI không hoạt động
                    raise Exception("AI response failed")
            except Exception as e:
                logger.warning(f"AI generation failed for {student.id}, using fallback: {e}")
                # Fallback messages cho tất cả các mốc
                if days_missed == 1:
                    title = '📚 Hôm qua bạn bỏ lỡ bài học rồi!'
                    message = 'Hôm qua bạn bỏ lỡ bài học rồi, hôm nay quay lại nhé!'
                elif days_missed == 3:
                    title = '💪 Đã 3 ngày rồi từ lần cuối bạn học'
                    message = 'Đã 3 ngày rồi từ lần cuối bạn học. Thói quen nhỏ mỗi ngày sẽ tạo ra khác biệt lớn!'
                elif days_missed == 4:
                    title = '📖 Đã 4 ngày rồi, đừng bỏ cuộc nhé!'
                    message = 'Đã 4 ngày rồi từ lần cuối bạn học. Hãy quay lại và tiếp tục hành trình học tập của mình!'
                elif days_missed == 5:
                    title = '🎯 Đã 5 ngày rồi, quay lại thôi!'
                    message = 'Đã 5 ngày rồi từ lần cuối bạn học. Mỗi ngày học một chút sẽ giúp bạn tiến bộ đáng kể!'
                elif days_missed == 7:
                    title = '🌟 Đã 1 tuần rồi, quay lại thôi!'
                    message = 'Đã 1 tuần rồi, quay lại làm một bài nhẹ nhàng để bắt đầu lại thôi 💪'
                elif days_missed == 14:
                    title = '📅 Đã 2 tuần rồi, đừng quên học tập nhé!'
                    message = 'Đã 2 tuần rồi từ lần cuối bạn học. Hãy quay lại và tiếp tục hành trình học tập của mình!'
                elif days_missed == 21:
                    title = '⏳ Đã 3 tuần rồi, quay lại học thôi!'
                    message = 'Đã 3 tuần rồi từ lần cuối bạn học. Hãy quay lại và bắt đầu lại hành trình học tập!'
                elif days_missed == 30:
                    title = '🗓️ Đã 1 tháng rồi, quay lại học tập nhé!'
                    message = 'Đã 1 tháng rồi từ lần cuối bạn học. Hãy quay lại và tiếp tục hành trình học tập của mình!'
                else:
                    # Fallback cho các mốc khác
                    title = f'📚 Đã {days_missed} ngày rồi từ lần cuối bạn học'
                    message = f'Đã {days_missed} ngày rồi từ lần cuối bạn học. Hãy quay lại và tiếp tục hành trình học tập của mình!'
            
            # Gửi notification
            Notification.objects.create(
                user=student,
                title=title,
                message=message,
                type='info',
                category='comeback_reminder',
                metadata={
                    'days_missed': days_missed,
                    'last_learning_date': str(last_date),
                }
            )
            
            # Log notification
            NotificationLog.objects.create(
                user=student,
                notification_type=notification_type,
                sent_date=today,
                metadata={'days_missed': days_missed, 'last_learning_date': str(last_date)}
            )
            
            sent_count += 1
            
        except Exception as e:
            logger.error(f"Error sending comeback reminder to {student.id}: {e}")
    
    logger.info(f"Sent {sent_count} comeback reminder notifications")
    return sent_count


@shared_task
def send_comeback_emails():
    """
    Gửi email nhắc nhở quay lại (tương tự Come Back Reminder nhưng qua email)
    Chỉ gửi khi user bật email_notifications_enabled
    """
    from activities.models import NotificationLog
    from content.models import LessonProgress
    from infrastructure.email_service import get_email_service
    from django.db.models import Q
    from datetime import timedelta
    from django.conf import settings
    
    today = timezone.localdate()
    reminder_days = [1, 3, 4, 5, 7, 14, 21, 30]  # Các mốc ngày cần nhắc (giống comeback reminders)
    
    # Lấy tất cả học sinh
    students = User.objects.filter(
        role='student',
        is_active=True
    ).select_related('profile')
    
    logger.info(f"Processing comeback emails for {students.count()} students")
    email_service = get_email_service()
    sent_count = 0
    
    for student in students:
        try:
            profile = getattr(student, 'profile', None)
            if not profile:
                logger.debug(f"Student {student.id} has no profile, skipping")
                continue
            
            # Kiểm tra email_notifications_enabled (ưu tiên), fallback về email_updates (được FE lưu)
            metadata = profile.metadata or {}
            email_pref = metadata.get('email_notifications_enabled')
            if email_pref is None:
                email_pref = metadata.get('email_updates', False)
            if not email_pref:
                logger.debug(f"Student {student.id} has email notifications disabled, skipping")
                continue
            
            # Tìm ngày học gần nhất - lấy theo last_accessed_at mới nhất (giống comeback reminders)
            last_progress = LessonProgress.objects.filter(
                student=student
            ).filter(
                Q(completed=True) | Q(video_watched=True)
            ).order_by('-last_accessed_at', '-completed_at').first()
            
            if not last_progress:
                continue
            
            # Lấy ngày học gần nhất từ last_accessed_at (phản ánh hoạt động gần nhất)
            last_date = None
            if last_progress.last_accessed_at:
                last_date = last_progress.last_accessed_at.date()
            elif last_progress.completed_at:
                last_date = last_progress.completed_at.date()
            
            if not last_date:
                continue
            
            days_missed = (today - last_date).days
            
            if days_missed <= 0:
                continue  # Đã học hôm nay hoặc tương lai
            
            # Kiểm tra xem có phải mốc cần nhắc không
            if days_missed not in reminder_days:
                logger.debug(f"Student {student.id}: days_missed={days_missed} not in reminder_days, skipping")
                continue
            
            logger.info(f"Student {student.id}: Processing comeback email for {days_missed} days missed")
            
            # Kiểm tra xem đã gửi email này chưa
            notification_type = f'comeback_email_{days_missed}day'
            already_sent = NotificationLog.objects.filter(
                user=student,
                notification_type=notification_type
            ).exists()
            
            if already_sent:
                continue
            
            # Tạo nội dung email bằng AI
            try:
                from .ai_tutor import AITutorEngine
                ai_tutor = AITutorEngine()
                
                # Lấy thông tin học sinh để cá nhân hóa
                student_name = profile.display_name or student.username
                student_grade = profile.metadata.get('grade', 1) or 1
                
                # Tạo prompt cho AI
                ai_prompt = f"""Tạo một email động viên ngắn gọn (2-3 câu, tối đa 80 từ) để khuyến khích học sinh quay lại học tập qua email.

Thông tin:
- Tên học sinh: {student_name}
- Lớp: {student_grade}
- Đã bỏ dở: {days_missed} ngày
- Lần cuối học: {last_date}

Yêu cầu:
- Ngôn ngữ đơn giản, phù hợp học sinh lớp {student_grade}
- Vui vẻ, ấm áp, khích lệ
- Thêm 1-2 emoji phù hợp
- Phù hợp với email (có thể dài hơn notification một chút)
- Xưng "mình", gọi học sinh là "bạn" hoặc "em"

Trả lời theo format:
SUBJECT: [tiêu đề email ngắn, có emoji]
BODY: [nội dung email động viên]"""
                
                ai_result = ai_tutor.chat(
                    user_message=ai_prompt,
                    context={},
                    conversation_history=[],
                    student_grade=student_grade
                )
                
                if ai_result.get('success') and ai_result.get('message'):
                    ai_response = ai_result['message']
                    # Parse response để lấy subject và body
                    lines = ai_response.split('\n')
                    subject = None
                    body_text = None
                    
                    for line in lines:
                        if line.strip().startswith('SUBJECT:'):
                            subject = line.replace('SUBJECT:', '').strip()
                        elif line.strip().startswith('BODY:'):
                            body_text = line.replace('BODY:', '').strip()
                    
                    # Fallback nếu không parse được
                    if not subject or not body_text:
                        body_text = ai_response.strip()
                        if days_missed == 1:
                            subject = '📚 Hôm qua bạn bỏ lỡ bài học rồi!'
                        elif days_missed == 3:
                            subject = '💪 Đã 3 ngày rồi từ lần cuối bạn học'
                        elif days_missed == 4:
                            subject = '📖 Đã 4 ngày rồi, đừng bỏ cuộc nhé!'
                        elif days_missed == 5:
                            subject = '🎯 Đã 5 ngày rồi, quay lại thôi!'
                        elif days_missed == 7:
                            subject = '🌟 Đã 1 tuần rồi, quay lại thôi!'
                        elif days_missed == 14:
                            subject = '📅 Đã 2 tuần rồi, đừng quên học tập nhé!'
                        elif days_missed == 21:
                            subject = '⏳ Đã 3 tuần rồi, quay lại học thôi!'
                        elif days_missed == 30:
                            subject = '🗓️ Đã 1 tháng rồi, quay lại học tập nhé!'
                        else:
                            subject = f'📚 Đã {days_missed} ngày rồi từ lần cuối bạn học'
                else:
                    raise Exception("AI response failed")
                    
            except Exception as e:
                logger.warning(f"AI generation failed for {student.id}, using fallback: {e}")
                # Fallback messages cho tất cả các mốc
                if days_missed == 1:
                    subject = '📚 Hôm qua bạn bỏ lỡ bài học rồi!'
                    body_text = 'Hôm qua bạn bỏ lỡ bài học rồi, hôm nay quay lại nhé!'
                elif days_missed == 3:
                    subject = '💪 Đã 3 ngày rồi từ lần cuối bạn học'
                    body_text = 'Đã 3 ngày rồi từ lần cuối bạn học. Thói quen nhỏ mỗi ngày sẽ tạo ra khác biệt lớn!'
                elif days_missed == 4:
                    subject = '📖 Đã 4 ngày rồi, đừng bỏ cuộc nhé!'
                    body_text = 'Đã 4 ngày rồi từ lần cuối bạn học. Hãy quay lại và tiếp tục hành trình học tập của mình!'
                elif days_missed == 5:
                    subject = '🎯 Đã 5 ngày rồi, quay lại thôi!'
                    body_text = 'Đã 5 ngày rồi từ lần cuối bạn học. Mỗi ngày học một chút sẽ giúp bạn tiến bộ đáng kể!'
                elif days_missed == 7:
                    subject = '🌟 Đã 1 tuần rồi, quay lại thôi!'
                    body_text = 'Đã 1 tuần rồi, quay lại làm một bài nhẹ nhàng để bắt đầu lại thôi 💪'
                elif days_missed == 14:
                    subject = '📅 Đã 2 tuần rồi, đừng quên học tập nhé!'
                    body_text = 'Đã 2 tuần rồi từ lần cuối bạn học. Hãy quay lại và tiếp tục hành trình học tập của mình!'
                elif days_missed == 21:
                    subject = '⏳ Đã 3 tuần rồi, quay lại học thôi!'
                    body_text = 'Đã 3 tuần rồi từ lần cuối bạn học. Hãy quay lại và bắt đầu lại hành trình học tập!'
                elif days_missed == 30:
                    subject = '🗓️ Đã 1 tháng rồi, quay lại học tập nhé!'
                    body_text = 'Đã 1 tháng rồi từ lần cuối bạn học. Hãy quay lại và tiếp tục hành trình học tập của mình!'
                else:
                    subject = f'📚 Đã {days_missed} ngày rồi từ lần cuối bạn học'
                    body_text = f'Đã {days_missed} ngày rồi từ lần cuối bạn học. Hãy quay lại và tiếp tục hành trình học tập của mình!'
            
            # Tạo HTML email với nút "Học ngay"
            frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
            learn_url = f"{frontend_url}/student/learning-path"
            
            html_body = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .button {{ display: inline-block; padding: 12px 24px; background-color: #4F46E5; color: white; text-decoration: none; border-radius: 6px; margin-top: 20px; }}
                    .button:hover {{ background-color: #4338CA; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>{subject}</h2>
                    <p>{body_text}</p>
                    <a href="{learn_url}" class="button">Học ngay</a>
                </div>
            </body>
            </html>
            """
            
            # Gửi email
            email_service.send(
                to=student.email,
                subject=subject,
                body=body_text,
                html_body=html_body
            )
            
            # Log notification
            NotificationLog.objects.create(
                user=student,
                notification_type=notification_type,
                sent_date=today,
                metadata={'days_missed': days_missed, 'last_learning_date': str(last_date)}
            )
            
            sent_count += 1
        except Exception as e:
            logger.error(f"Error sending comeback email to {student.id}: {e}", exc_info=True)

    logger.info(f"Sent {sent_count} comeback reminder emails")
    return sent_count
