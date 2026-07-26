"""
AI Learning Path APIs
- AI Đánh giá đầu vào
- AI Gợi ý bài học thông minh
- AI Phân tích điểm yếu
- AI Reward System
- FE mapping: aiLearningService (gọi /student/ai/learning-analyzer|assessment|assessment/result)

Tích hợp DeepSeek API (chính) và Gemini API (dự phòng)
"""
import os
import json
import logging
import requests as http_requests
from datetime import datetime, timedelta

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Avg, Count, Q, Max
from django.db.models.functions import TruncDate
from django.utils import timezone

from student_api.permissions import IsStudent
from content.models import Lesson, Module, Course, Enrollment, LessonProgress
from activities.models import ExerciseAttempt, Exercise
from gamification.models import GameSession
from ai_personalization.models import StreakRestoration

logger = logging.getLogger(__name__)


def _get_activity_qs_and_dates(user, tz, before_date=None):
    """Collect lesson/exercise/game activity dates in the correct timezone.

    Returns annotated querysets (for counting today) and a set of all activity dates
    to use when calculating streaks. Optionally exclude dates on/after ``before_date``
    (useful when checking the streak prior to a specific day).
    """
    lesson_qs = LessonProgress.objects.filter(
        student=user
    ).filter(
        Q(completed=True) | Q(video_watched=True)
    ).annotate(
        completed_date=TruncDate('completed_at', tzinfo=tz),
        accessed_date=TruncDate('last_accessed_at', tzinfo=tz)
    )
    if before_date:
        lesson_qs = lesson_qs.filter(
            Q(completed_date__lt=before_date) | Q(accessed_date__lt=before_date)
        )
    lesson_dates = set(
        dt
        for completed_dt, accessed_dt in lesson_qs.values_list('completed_date', 'accessed_date')
        for dt in (completed_dt, accessed_dt)
        if dt
    )

    exercise_qs = ExerciseAttempt.objects.filter(
        student=user,
        finished_at__isnull=False
    ).annotate(
        finished_date=TruncDate('finished_at', tzinfo=tz)
    )
    if before_date:
        exercise_qs = exercise_qs.filter(finished_date__lt=before_date)
    exercise_dates = set(
        dt for dt in exercise_qs.values_list('finished_date', flat=True) if dt
    )

    game_qs = GameSession.objects.filter(
        player=user,
        completed=True
    ).annotate(
        completed_date=TruncDate('completed_at', tzinfo=tz)
    )
    if before_date:
        game_qs = game_qs.filter(completed_date__lt=before_date)
    game_dates = set(
        dt for dt in game_qs.values_list('completed_date', flat=True) if dt
    )

    activity_dates = lesson_dates | exercise_dates | game_dates
    return lesson_qs, exercise_qs, game_qs, activity_dates


def _compute_streak(activity_dates, upto_date, require_activity_on_upto_date=True):
    """
    Compute consecutive-day streak ending at ``upto_date`` (inclusive).

    If ``require_activity_on_upto_date`` is False, the streak ends at the most
    recent activity on/before ``upto_date``.
    """
    if not activity_dates:
        return 0

    if require_activity_on_upto_date:
        if upto_date not in activity_dates:
            return 0
        start_date = upto_date
    else:
        start_date = max((d for d in activity_dates if d <= upto_date), default=None)
        if not start_date:
            return 0

    streak = 0
    check_date = start_date
    while streak < 365 and check_date in activity_dates:
        streak += 1
        check_date -= timedelta(days=1)
    return streak


class AIAPIClient:
    """Client để gọi OpenRouter API"""
    
    @staticmethod
    def call_deepseek(prompt, max_tokens=1024):
        """Gọi OpenRouter API"""
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            return {"error": "OpenRouter API chưa được cấu hình"}
        
        model = os.getenv("OPENROUTER_MODEL") or os.getenv("DEEPSEEK_MODEL") or "openai/gpt-4o"
        url = "https://openrouter.ai/api/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://smartkid.local",
            "X-Title": "SmartKid AI Learning",
        }
        
        try:
            resp = http_requests.post(
                url,
                headers=headers,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                },
                timeout=60,
            )
            
            if resp.status_code == 200:
                data = resp.json()
                text = data.get("choices", [])[0].get("message", {}).get("content", "")
                if text and text.strip():
                    return {"text": text.strip(), "model": model}
                return {"error": "OpenRouter trả về nội dung rỗng"}
            
            return {"error": f"OpenRouter lỗi {resp.status_code}"}
        except Exception as e:
            logger.error(f"OpenRouter API error: {e}")
            return {"error": str(e)}
    
    @staticmethod
    def call_ai(prompt, max_tokens=1024):
        """Gọi AI qua OpenRouter"""
        result = AIAPIClient.call_deepseek(prompt, max_tokens)
        if not result.get("error"):
            return result

        return {"error": result.get("error") or "OpenRouter không khả dụng"}


class AILearningAnalyzerView(APIView):
    """
    GET /api/student/ai/learning-analyzer/
    Phân tích tiến độ học tập và đề xuất bài học thông minh
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request):
        try:
            user = request.user
            
            # Lấy các khóa học đã đăng ký
            # Note: content.Enrollment model không có field 'status', chỉ có student và course
            enrollments = Enrollment.objects.filter(
                student=user
            ).select_related('course')
            
            if not enrollments.exists():
                # Vẫn tính daily_goal/streak dựa trên mọi hoạt động (kể cả AI practice) để không hiển thị 0 streak
                daily_goal = self._get_daily_goal(user)
                return Response({
                    "has_courses": False,
                    "message": "Chưa có khóa học nào. Hãy đăng ký khóa học để bắt đầu!",
                    "suggestions": [],
                    "weaknesses": [],
                    "achievements": [],
                    "daily_goal": daily_goal,
                })
            
            # Phân tích tiến độ
            analysis = self._analyze_progress(user, enrollments)
            
            # Tạo gợi ý AI
            suggestions = self._generate_suggestions(user, enrollments, analysis)
            
            # Phát hiện điểm yếu
            weaknesses = self._detect_weaknesses(user, enrollments)
            
            # Tính achievements
            achievements = self._calculate_achievements(user, analysis)
            
            # Daily goal
            daily_goal = self._get_daily_goal(user)
            
            # Tạo tin nhắn AI (tắt API call để tránh lỗi)
            use_ai_api = False  # Tạm tắt để tránh lỗi API
            ai_message = self._generate_ai_message(analysis, daily_goal, weaknesses, use_ai=use_ai_api)
            
            return Response({
                "has_courses": True,
                "analysis": analysis,
                "suggestions": suggestions,
                "weaknesses": weaknesses,
                "achievements": achievements,
                "daily_goal": daily_goal,
                "ai_message": ai_message,
            })
        except Exception as e:
            logger.error(f"AI Learning Analyzer error: {e}")
            # Không giả lập số liệu 0 khi truy vấn thật bị lỗi.
            return Response(
                {"detail": "Không thể phân tích dữ liệu học tập lúc này."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
    
    def _analyze_progress(self, user, enrollments):
        """Phân tích tiến độ học tập tổng thể"""
        total_lessons = 0
        completed_lessons = 0
        total_exercises = 0
        completed_exercises = 0
        avg_score = 0
        scores = []
        
        course_progress = []
        
        for enrollment in enrollments:
            course = enrollment.course
            modules = Module.objects.filter(course=course).prefetch_related('lessons')
            
            course_total = 0
            course_completed = 0
            
            for module in modules:
                lessons = module.lessons.all()
                course_total += lessons.count()
                
                for lesson in lessons:
                    total_lessons += 1
                    progress = LessonProgress.objects.filter(
                        student=user,
                        lesson=lesson,
                        completed=True
                    ).first()
                    if progress:
                        completed_lessons += 1
                        course_completed += 1
            
            # Lấy điểm bài tập
            exercises = Exercise.objects.filter(lesson__module__course=course)
            for exercise in exercises:
                total_exercises += 1
                attempt = ExerciseAttempt.objects.filter(
                    student=user,
                    exercise=exercise,
                    finished_at__isnull=False
                ).order_by('-finished_at').first()
                if attempt:
                    completed_exercises += 1
                    if attempt.score is not None:
                        scores.append(float(attempt.score))
            
            progress_pct = round((course_completed / course_total * 100) if course_total > 0 else 0)
            course_progress.append({
                "course_id": str(course.id),
                "course_title": course.title,
                "total": course_total,
                "completed": course_completed,
                "progress": progress_pct,
            })
        
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0
        overall_progress = round((completed_lessons / total_lessons * 100) if total_lessons > 0 else 0)
        
        return {
            "total_lessons": total_lessons,
            "completed_lessons": completed_lessons,
            "total_exercises": total_exercises,
            "completed_exercises": completed_exercises,
            "overall_progress": overall_progress,
            "avg_score": avg_score,
            "course_progress": course_progress,
        }
    
    def _generate_suggestions(self, user, enrollments, analysis):
        """Tạo gợi ý bài học thông minh"""
        suggestions = []
        
        # 1. Bài chưa hoàn thành (ưu tiên cao)
        for enrollment in enrollments[:3]:  # Giới hạn 3 khóa
            course = enrollment.course
            modules = Module.objects.filter(course=course).prefetch_related('lessons').order_by('position')
            
            for module in modules:
                for lesson in module.lessons.all().order_by('position'):
                    progress = LessonProgress.objects.filter(
                        student=user,
                        lesson=lesson,
                        completed=True
                    ).exists()
                    
                    if not progress:
                        suggestions.append({
                            "type": "continue",
                            "priority": "high",
                            "icon": "🎯",
                            "title": lesson.title,
                            "subtitle": f"{course.title} - {module.title}",
                            "reason": "Bài tiếp theo trong lộ trình",
                            "lesson_id": str(lesson.id),
                            "course_id": str(course.id),
                            "estimated_time": 15,
                        })
                        break
                if suggestions:
                    break
        
        # 2. Bài cần ôn lại (đã lâu không học)
        old_progress = LessonProgress.objects.filter(
            student=user,
            completed=True,
            completed_at__lt=timezone.now() - timedelta(days=7)
        ).select_related('lesson', 'lesson__module', 'lesson__module__course').order_by('completed_at')[:2]
        
        for progress in old_progress:
            lesson = progress.lesson
            suggestions.append({
                "type": "review",
                "priority": "medium",
                "icon": "🔄",
                "title": f"Ôn lại: {lesson.title}",
                "subtitle": lesson.module.course.title if lesson.module else "",
                "reason": f"Đã học cách đây {(timezone.now() - progress.completed_at).days} ngày",
                "lesson_id": str(lesson.id),
                "course_id": str(lesson.module.course.id) if lesson.module else "",
                "estimated_time": 10,
            })
        
        # 3. Bài tập chưa làm
        # Note: content.Enrollment không có field status
        pending_exercises = Exercise.objects.filter(
            lesson__module__course__enrollments__student=user
        ).exclude(
            attempts__student=user,
            attempts__finished_at__isnull=False
        ).select_related('lesson', 'lesson__module', 'lesson__module__course')[:2]
        
        for exercise in pending_exercises:
            suggestions.append({
                "type": "exercise",
                "priority": "medium",
                "icon": "📝",
                "title": exercise.title,
                "subtitle": exercise.lesson.module.course.title if exercise.lesson and exercise.lesson.module else "",
                "reason": "Bài tập chưa làm",
                "exercise_id": str(exercise.id),
                "lesson_id": str(exercise.lesson.id) if exercise.lesson else "",
                "course_id": str(exercise.lesson.module.course.id) if exercise.lesson and exercise.lesson.module else "",
                "estimated_time": 10,
            })
        
        return suggestions[:5]  # Giới hạn 5 gợi ý
    
    def _detect_weaknesses(self, user, enrollments):
        """Phát hiện điểm yếu dựa trên điểm bài tập và phân tích câu hỏi sai cụ thể"""
        weaknesses = []
        wrong_questions_by_topic = {}  # Nhóm câu sai theo topic để tạo bài tập
        
        # Lấy các bài tập có điểm thấp (LOẠI BỎ bài AI Practice - không tính vào phân tích điểm yếu)
        # Bỏ qua hoàn toàn các bài đã có attempt điểm >= 60 (đã làm lại và đạt)
        passed_exercise_ids = ExerciseAttempt.objects.filter(
            student=user,
            finished_at__isnull=False,
            score__gte=60
        ).values_list('exercise_id', flat=True)
        
        low_score_attempts = ExerciseAttempt.objects.filter(
            student=user,
            finished_at__isnull=False,
            score__lt=60  # Dưới 60%
        ).exclude(
            exercise_id__in=passed_exercise_ids
        ).exclude(
            # Loại bỏ các bài AI Practice (có title bắt đầu bằng "AI Practice" hoặc metadata type = 'ai_practice')
            exercise__title__startswith='AI Practice'
        ).exclude(
            # Loại bỏ các bài không có lesson (bài độc lập như AI Practice)
            exercise__lesson__isnull=True
        ).select_related(
            'exercise', 
            'exercise__lesson', 
            'exercise__lesson__module',
            'exercise__lesson__module__course'
        ).prefetch_related(
            'exercise__settings',
            'answers__question',
            'answers__question__choices'
        ).order_by('score')[:10]  # Lấy nhiều hơn để filter
        
        for attempt in low_score_attempts:
            exercise = attempt.exercise
            # Bỏ qua bài AI Practice (kiểm tra lại để chắc chắn)
            if not exercise:
                continue
            # Kiểm tra metadata type = 'ai_practice'
            if attempt.metadata and attempt.metadata.get('type') == 'ai_practice':
                continue
            # Kiểm tra title bắt đầu bằng "AI Practice"
            if exercise.title and exercise.title.startswith('AI Practice'):
                continue
            if not exercise.lesson or not exercise.lesson.module:
                continue

            # Kiểm tra xem bài tập có thể làm lại được không
            # Đếm số lần attempt của học sinh cho bài tập này
            student_attempt_count = ExerciseAttempt.objects.filter(
                student=user,
                exercise=exercise,
                finished_at__isnull=False
            ).count()

            # Xác định số lần làm tối đa (mặc định 1 nếu chưa cấu hình để tránh cho ôn lại vô hạn)
            settings_obj = getattr(exercise, "settings", None)
            max_attempts = getattr(settings_obj, "max_attempts", None) if settings_obj else None
            effective_max_attempts = int(max_attempts) if max_attempts is not None else 1
            can_retry = student_attempt_count < effective_max_attempts
            
            # Phân tích câu hỏi sai từ attempt này (dù không cho retry vẫn cần tạo bài cải thiện)
            from activities.models import ExerciseAnswer
            answers = ExerciseAnswer.objects.filter(
                attempt=attempt,
                correct=False  # Chỉ lấy câu sai
            ).select_related('question')
            
            wrong_questions = []
            for answer in answers:
                question = answer.question
                if question:
                    # Lấy đáp án đúng
                    correct_choice = question.choices.filter(is_correct=True).first()
                    correct_answer_text = correct_choice.text if correct_choice else "N/A"
                    # Lấy đáp án học sinh chọn từ JSON field `answer`
                    student_answer_text = "Không trả lời"
                    payload = answer.answer
                    try:
                        if isinstance(payload, dict):
                            student_answer_text = payload.get('text') or payload.get('selected_choice') or payload.get('selected_choice_id') or payload.get('value') or "Không trả lời"
                        elif isinstance(payload, list):
                            student_answer_text = ", ".join(str(x) for x in payload) or "Không trả lời"
                        elif payload:
                            student_answer_text = str(payload)
                    except Exception:
                        student_answer_text = "Không trả lời"
                    
                    question_text = getattr(question, 'text', None) or getattr(question, 'prompt', '') or str(question)
                    
                    wrong_questions.append({
                        "question_text": question_text[:200],  # Giới hạn độ dài
                        "question_id": str(question.id),
                        "student_answer": student_answer_text[:100],
                        "correct_answer": correct_answer_text[:100],
                        "topic": exercise.lesson.title,
                    })

            topic_key = exercise.lesson.title
            
            # LOẠI BỎ các topic là "AI Practice" hoặc liên quan đến AI Practice
            if "AI Practice" in topic_key:
                continue
            
            # Nhóm câu sai theo topic
            if topic_key not in wrong_questions_by_topic:
                wrong_questions_by_topic[topic_key] = {
                    "topic": exercise.lesson.title,
                    "course": exercise.lesson.module.course.title,
                    "lesson_id": str(exercise.lesson.id),
                    "course_id": str(exercise.lesson.module.course.id),
                    "wrong_questions": [],
                    "min_score": float(attempt.score) if attempt.score else 0,
                    "can_retry": can_retry,
                }
            
            topic_data = wrong_questions_by_topic[topic_key]
            topic_data["wrong_questions"].extend(wrong_questions)
            topic_data["min_score"] = min(topic_data["min_score"], float(attempt.score) if attempt.score else 0)
            # Nếu bất kỳ attempt nào hết lượt, đánh dấu không cho ôn lại
            topic_data["can_retry"] = topic_data.get("can_retry", False) and can_retry
            
            # Giới hạn số lượng weaknesses
            if len(wrong_questions_by_topic) >= 5:
                break
        
        # Chuyển đổi sang format weaknesses
        for topic_data in wrong_questions_by_topic.values():
            # LOẠI BỎ các weakness có topic là "AI Practice" hoặc liên quan đến AI Practice
            topic = topic_data.get("topic", "")
            course = topic_data.get("course", "")
            
            # Bỏ qua nếu topic hoặc course chứa "AI Practice"
            if "AI Practice" in topic or "AI Practice" in course:
                continue
            
            # Lấy top 5 câu sai để tạo bài tập
            wrong_questions = topic_data["wrong_questions"][:5]
            
            can_retry = topic_data.get("can_retry", False)
            suggestion_text = f"Cần ôn lại bài {topic_data['topic']}" if can_retry else f"Cần làm bài cải thiện cho {topic_data['topic']}"
            weaknesses.append({
                "topic": topic_data["topic"],
                "course": topic_data["course"],
                "score": topic_data["min_score"],
                "suggestion": suggestion_text,
                "lesson_id": topic_data["lesson_id"],
                "course_id": topic_data["course_id"],
                "can_retry": can_retry,
                "wrong_questions_count": len(wrong_questions),
                "wrong_questions": wrong_questions,  # Gửi câu sai để AI tạo bài tập
                })
        
        return weaknesses
    
    def _calculate_achievements(self, user, analysis):
        """Tính toán huy hiệu và thành tích"""
        achievements = []
        
        completed = analysis['completed_lessons']
        progress = analysis['overall_progress']
        avg_score = analysis['avg_score']
        
        # Huy hiệu dựa trên số bài hoàn thành
        if completed >= 1:
            achievements.append({"id": "first_lesson", "name": "Bước đầu tiên", "icon": "🌱", "unlocked": True})
        if completed >= 5:
            achievements.append({"id": "five_lessons", "name": "Chăm chỉ", "icon": "📚", "unlocked": True})
        if completed >= 10:
            achievements.append({"id": "ten_lessons", "name": "Học giỏi", "icon": "⭐", "unlocked": True})
        if completed >= 25:
            achievements.append({"id": "master", "name": "Siêu sao", "icon": "🌟", "unlocked": True})
        
        # Huy hiệu dựa trên điểm
        if avg_score >= 80:
            achievements.append({"id": "high_score", "name": "Điểm cao", "icon": "🏆", "unlocked": True})
        if avg_score >= 95:
            achievements.append({"id": "perfect", "name": "Hoàn hảo", "icon": "💎", "unlocked": True})
        
        # Huy hiệu tiến độ
        if progress >= 50:
            achievements.append({"id": "halfway", "name": "Nửa đường", "icon": "🔥", "unlocked": True})
        if progress >= 100:
            achievements.append({"id": "complete", "name": "Hoàn thành", "icon": "🎉", "unlocked": True})
        
        return achievements
    
    def _get_daily_goal(self, user):
        """Lấy mục tiêu học tập hàng ngày"""
        # SỬ DỤNG localdate() để lấy ngày theo timezone local (Asia/Ho_Chi_Minh)
        # thay vì timezone.now().date() trả về ngày UTC
        today = timezone.localdate()
        
        tz = timezone.get_current_timezone()
        lesson_qs, exercise_qs, game_qs, activity_dates = _get_activity_qs_and_dates(user, tz)

        completed_today = (
            lesson_qs.filter(
                Q(completed_date=today) | Q(accessed_date=today)
            ).distinct().count()
            + exercise_qs.filter(finished_date=today).distinct().count()
            + game_qs.filter(completed_date=today).distinct().count()
        )

        streak = _compute_streak(activity_dates, today)

        restoration_count = StreakRestoration.get_restoration_count_this_month(user)
        can_restore_monthly = StreakRestoration.can_restore(user)

        # Chỉ cho phép khôi phục khi:
        # - Đã từng có hoạt động trước đây (mất streak), và
        # - Streak hiện tại = 0, và
        # - Không phải người mới chưa có dữ liệu
        has_history = bool(activity_dates)
        last_activity = max(activity_dates) if activity_dates else None
        gap_days = (today - last_activity).days if last_activity else None
        # Mất streak khi đã bỏ lỡ ÍT NHẤT 1 ngày (không hoạt động hôm qua và hôm nay)
        lost_streak = has_history and streak == 0 and gap_days is not None and gap_days >= 2
        can_restore_flag = can_restore_monthly and lost_streak

        return {
            "target": 2,  # Mục tiêu 2 bài/ngày
            "completed": completed_today,
            "streak": streak,
            "streak_restoration": {
                "count_this_month": restoration_count,
                "max_per_month": 2,
                "can_restore": can_restore_flag,
                "remaining": max(0, 2 - restoration_count)
            }
        }
    
    def _generate_ai_message(self, analysis, daily_goal, weaknesses=None, use_ai=True):
        """Tạo tin nhắn AI động viên - có thể gọi AI API để tạo tin nhắn cá nhân hóa"""
        progress = analysis['overall_progress']
        streak = daily_goal['streak']
        completed_today = daily_goal['completed']
        target = daily_goal['target']
        completed_lessons = analysis['completed_lessons']
        avg_score = analysis['avg_score']
        
        # Nếu bật AI và có đủ dữ liệu, gọi AI để tạo tin nhắn cá nhân hóa
        if use_ai and completed_lessons > 0:
            try:
                prompt = f"""Bạn là AI trợ lý học tập cho học sinh tiểu học Việt Nam.
Hãy tạo 1 tin nhắn động viên ngắn gọn (tối đa 50 từ) dựa trên thông tin sau:

- Tiến độ học tập: {progress}%
- Số bài đã hoàn thành: {completed_lessons}
- Điểm trung bình: {avg_score}%
- Streak (ngày học liên tiếp): {streak} ngày
- Mục tiêu hôm nay: {completed_today}/{target} bài
- Điểm yếu cần cải thiện: {len(weaknesses) if weaknesses else 0} chủ đề

Yêu cầu:
- Dùng ngôn ngữ thân thiện, gọi học sinh là "con"
- Thêm emoji phù hợp
- Động viên tích cực
- Nếu có điểm yếu, nhắc nhẹ nhàng cần ôn lại

Chỉ trả về tin nhắn, không giải thích."""
                
                result = AIAPIClient.call_ai(prompt, max_tokens=150)
                if not result.get("error") and result.get("text"):
                    return result["text"]
            except Exception as e:
                logger.error(f"AI message generation failed: {e}")
        
        # Fallback: tin nhắn mặc định
        if completed_today >= target:
            return f"🎉 Tuyệt vời! Con đã hoàn thành mục tiêu hôm nay! Streak: {streak} ngày liên tiếp!"
        
        remaining = target - completed_today
        if progress == 0:
            return "🌟 Chào con! Hãy bắt đầu bài học đầu tiên nhé! AI sẽ đồng hành cùng con!"
        
        if streak >= 7:
            return f"🔥 Wow! {streak} ngày học liên tiếp! Con thật kiên trì! Còn {remaining} bài nữa thôi!"
        
        if streak >= 3:
            return f"💪 Giỏi lắm! {streak} ngày streak! Cố thêm {remaining} bài nữa nhé!"
        
        if progress < 25:
            return f"🌱 Con đang làm tốt lắm! Còn {remaining} bài nữa để đạt mục tiêu hôm nay!"
        
        if progress < 50:
            return f"📚 Tiến bộ tốt! Đã hoàn thành {progress}% rồi. Cố lên nhé!"
        
        if progress < 75:
            return f"⭐ Xuất sắc! Đã đi được hơn nửa đường! Còn {remaining} bài nữa thôi!"
        
        return f"🏆 Sắp hoàn thành rồi! Chỉ còn {100 - progress}% nữa thôi. Con làm được mà!"


class AIAssessmentView(APIView):
    """
    POST /api/student/ai/assessment/
    AI Đánh giá đầu vào cho khóa học
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def post(self, request):
        course_id = request.data.get('course_id')
        if not course_id:
            return Response({"detail": "course_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response({"detail": "Course not found"}, status=status.HTTP_404_NOT_FOUND)
        if not Enrollment.objects.filter(student=request.user, course=course).exists():
            return Response(
                {"detail": "Bạn chưa đăng ký khóa học này."},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        # Tạo câu hỏi đánh giá bằng AI
        use_ai = request.data.get('use_ai', True)
        questions = self._generate_assessment_questions(course, use_ai=use_ai)

        if questions is None:
            return Response(
                {"detail": "Không thể tạo câu hỏi đánh giá vì AI chưa được cấu hình hoặc đang lỗi."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if not questions:
            return Response(
                {"detail": "Khóa học chưa có nội dung bài học để tạo bài đánh giá."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        return Response({
            "course_id": str(course.id),
            "course_title": course.title,
            "questions": questions,
            "total_questions": len(questions),
            "estimated_time": len(questions) * 1,  # 1 phút/câu
        })
    
    def _generate_assessment_questions(self, course, use_ai=True):
        """Tạo 10-15 câu hỏi đánh giá dựa trên NỘI DUNG THỰC TẾ của khóa học"""
        import random
        from content.models import LessonVersion, ContentBlock
        
        modules = Module.objects.filter(course=course).prefetch_related('lessons')
        
        # Thu thập thông tin và NỘI DUNG bài học
        lesson_data = []
        for module in modules:
            for lesson in module.lessons.all():
                # Lấy nội dung text từ lesson
                content_text = ""
                
                # 1. Lấy từ text_content và introduction
                if lesson.text_content:
                    content_text += lesson.text_content + "\n"
                if lesson.introduction:
                    content_text += lesson.introduction + "\n"
                
                # 2. Lấy từ ContentBlock (version mới nhất)
                try:
                    latest_version = lesson.versions.filter(status='published').first()
                    if not latest_version:
                        latest_version = lesson.versions.first()
                    
                    if latest_version:
                        # Lấy text từ content blocks
                        blocks = ContentBlock.objects.filter(lesson_version=latest_version)
                        for block in blocks:
                            if block.type == 'text' and block.payload.get('text'):
                                content_text += block.payload['text'] + "\n"
                            elif block.type == 'introduction' and block.payload.get('text'):
                                content_text += block.payload['text'] + "\n"
                except Exception:
                    pass
                
                lesson_data.append({
                    "title": lesson.title,
                    "module": module.title,
                    "lesson_id": str(lesson.id),
                    "content": content_text[:1500],  # Giới hạn để không quá dài
                })
        
        if not lesson_data:
            return []
        
        # Số câu hỏi: ngẫu nhiên 10-15
        num_questions = random.randint(10, 15)
        
        # Thử dùng AI để tạo câu hỏi thông minh dựa trên nội dung thực tế
        if use_ai:
            try:
                # Tạo tóm tắt nội dung cho AI
                content_summary = ""
                for i, lesson in enumerate(lesson_data[:8]):  # Lấy tối đa 8 bài
                    content_summary += f"\n--- Bài {i+1}: {lesson['title']} ---\n"
                    if lesson['content']:
                        content_summary += lesson['content'][:500] + "\n"
                    else:
                        content_summary += f"(Bài học về {lesson['title']})\n"
                
                prompt = f"""Bạn là AI tạo câu hỏi đánh giá đầu vào cho học sinh tiểu học Việt Nam.

KHÓA HỌC: {course.title}

NỘI DUNG CÁC BÀI HỌC:
{content_summary}

YÊU CẦU:
1. Tạo CHÍNH XÁC {num_questions} câu hỏi trắc nghiệm
2. Câu hỏi phải DỰA TRÊN NỘI DUNG THỰC TẾ của các bài học ở trên
3. Mỗi câu có 4 lựa chọn, 1 đáp án đúng
4. Độ khó từ dễ đến trung bình (phù hợp tiểu học)
5. Câu hỏi đa dạng: kiến thức, hiểu biết, áp dụng

Trả về JSON array với format:
[
  {{
    "text": "Câu hỏi liên quan đến nội dung bài học...",
    "choices": ["Đáp án A", "Đáp án B", "Đáp án C", "Đáp án D"],
    "correct_index": 0
  }}
]

CHỈ TRẢ VỀ JSON, KHÔNG GIẢI THÍCH."""
                
                result = AIAPIClient.call_ai(prompt, max_tokens=3000)
                if not result.get("error") and result.get("text"):
                    # Parse JSON từ response
                    text = result["text"].strip()
                    # Tìm JSON array trong response
                    start = text.find('[')
                    end = text.rfind(']') + 1
                    if start >= 0 and end > start:
                        json_str = text[start:end]
                        ai_questions = json.loads(json_str)
                        
                        # Map câu hỏi với lesson
                        questions = []
                        for i, q in enumerate(ai_questions[:num_questions]):
                            # Phân bổ câu hỏi cho các bài học
                            lesson_idx = i % len(lesson_data)
                            questions.append({
                                "id": i + 1,
                                "type": "single",
                                "text": q.get("text", ""),
                                "choices": q.get("choices", []),
                                "correct_index": q.get("correct_index", 0),
                                "module": lesson_data[lesson_idx]["module"],
                                "lesson_id": lesson_data[lesson_idx]["lesson_id"],
                                "ai_generated": True,
                            })
                        if len(questions) >= 10:
                            return questions
            except Exception as e:
                logger.error(f"AI assessment generation failed: {e}")
        
        # Không tạo bộ câu hỏi tự đánh giá giả khi provider lỗi/chưa cấu hình.
        return None


class AIAssessmentResultView(APIView):
    """
    POST /api/student/ai/assessment/result/
    Xử lý kết quả đánh giá và tạo lộ trình cá nhân hóa
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def post(self, request):
        course_id = request.data.get('course_id')
        answers = request.data.get('answers', [])
        
        if not course_id:
            return Response({"detail": "course_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response({"detail": "Course not found"}, status=status.HTTP_404_NOT_FOUND)
        if not Enrollment.objects.filter(student=request.user, course=course).exists():
            return Response(
                {"detail": "Bạn chưa đăng ký khóa học này."},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        # Phân tích kết quả với AI
        use_ai = request.data.get('use_ai', True)
        result = self._analyze_assessment(course, answers, use_ai=use_ai)
        
        return Response(result)
    
    def _analyze_assessment(self, course, answers, use_ai=True):
        """Phân tích kết quả đánh giá và đề xuất lộ trình - có thể dùng AI"""
        # Tính điểm theo thang 10
        # Mỗi câu trả lời đúng (correct_index match) = 1 điểm
        # Điểm = (số câu đúng / tổng số câu) * 10
        correct_count = 0
        total_questions = len(answers) if answers else 0
        
        for answer in answers:
            # Nếu có correct_index trong câu hỏi, so sánh với choice
            correct_index = answer.get('correct_index')
            choice = answer.get('choice', 0)
            
            if correct_index is not None:
                # Câu hỏi có đáp án đúng - kiểm tra đúng/sai
                if choice == correct_index:
                    correct_count += 1
            else:
                # Câu hỏi self-assessment (không có đáp án đúng)
                # Dùng choice làm điểm tự đánh giá (0-3 -> quy đổi)
                correct_count += choice / 3  # Normalize về 0-1
        
        # Tính điểm trên thang 10
        score_10 = round((correct_count / total_questions) * 10, 1) if total_questions > 0 else 0
        
        # Xác định level dựa trên thang điểm 10
        if score_10 < 4:
            level = "beginner"
            level_text = "Người mới bắt đầu"
            start_from = 1
        elif score_10 < 6:
            level = "elementary"
            level_text = "Cơ bản"
            start_from = 2
        elif score_10 < 8:
            level = "intermediate"
            level_text = "Trung bình"
            start_from = 3
        else:
            level = "advanced"
            level_text = "Nâng cao"
            start_from = 4
        
        # Lấy bài học đề xuất bắt đầu
        modules = Module.objects.filter(course=course).prefetch_related('lessons').order_by('position')
        suggested_lessons = []
        all_lessons = []
        
        lesson_count = 0
        for module in modules:
            for lesson in module.lessons.all().order_by('position'):
                lesson_count += 1
                all_lessons.append({"title": lesson.title, "module": module.title})
                if lesson_count >= start_from:
                    suggested_lessons.append({
                        "id": str(lesson.id),
                        "title": lesson.title,
                        "module": module.title,
                    })
                if len(suggested_lessons) >= 3:
                    break
            if len(suggested_lessons) >= 3:
                break
        
        # Tạo recommendation bằng AI
        recommendation = ""
        ai_recommendation = False
        if use_ai:
            try:
                prompt = f"""Bạn là AI tư vấn học tập cho học sinh tiểu học Việt Nam.
Dựa trên kết quả đánh giá đầu vào, hãy đưa ra lời khuyên ngắn gọn (tối đa 30 từ).

Khóa học: {course.title}
Trình độ: {level_text}
Điểm đánh giá: {score_10}/10
Các bài học: {', '.join([l['title'] for l in all_lessons[:5]])}

Yêu cầu:
- Ngôn ngữ thân thiện, gọi học sinh là "con"
- Động viên tích cực
- Đề xuất cụ thể nên bắt đầu từ đâu

Chỉ trả về lời khuyên, không giải thích."""
                
                result = AIAPIClient.call_ai(prompt, max_tokens=100)
                if not result.get("error") and result.get("text"):
                    recommendation = result["text"]
                    ai_recommendation = True
            except Exception as e:
                logger.error(f"AI recommendation failed: {e}")
        
        # Fallback recommendation
        if not recommendation:
            if level == "beginner":
                recommendation = "Bắt đầu từ bài đầu tiên để xây dựng nền tảng vững chắc."
            elif level == "elementary":
                recommendation = "Có thể bỏ qua phần giới thiệu và bắt đầu từ bài thực hành."
            elif level == "intermediate":
                recommendation = "Tập trung vào các bài nâng cao và bài tập thực hành."
            else:
                recommendation = "Có thể đi thẳng vào các bài kiểm tra và thử thách."
        
        return {
            "level": level,
            "level_text": level_text,
            "score": score_10,
            "max_score": 10,
            "recommendation": recommendation,
            "start_from_lesson": start_from,
            "suggested_lessons": suggested_lessons,
            "personalized_path": {
                "skip_intro": score_10 >= 5,
                "focus_practice": score_10 >= 7,
                "challenge_mode": score_10 >= 8.5,
            },
            "ai_powered": ai_recommendation,
        }


class StreakRestoreView(APIView):
    """
    POST /api/student/ai/learning/restore-streak/
    Khôi phục streak bị mất - tối đa 2 lần/tháng
    """
    permission_classes = [IsAuthenticated, IsStudent]
    
    def _get_previous_streak(self, user, before_date):
        """Tính streak trước ngày bị mất"""
        tz = timezone.get_current_timezone()
        _, _, _, activity_dates = _get_activity_qs_and_dates(user, tz, before_date=before_date)
        # Use the latest activity strictly before the given date
        return _compute_streak(
            activity_dates,
            before_date - timedelta(days=1),
            require_activity_on_upto_date=False
        )
    
    def post(self, request):
        user = request.user
        today = timezone.localdate()
        
        # Kiểm tra streak hiện tại
        current_streak = self._get_daily_goal(user)['streak']
        
        if current_streak > 0:
            return Response(
                {'error': 'Streak hiện tại vẫn còn, không cần khôi phục'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Kiểm tra số lần đã khôi phục trong tháng
        if not StreakRestoration.can_restore(user):
            restoration_count = StreakRestoration.get_restoration_count_this_month(user)
            return Response(
                {
                    'error': f'Đã hết lượt khôi phục trong tháng này ({restoration_count}/2)',
                    'restoration_count': restoration_count,
                    'max_per_month': 2
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Tính streak trước khi mất (ngày hôm qua)
        yesterday = today - timedelta(days=1)
        previous_streak = self._get_previous_streak(user, today)
        
        if previous_streak == 0:
            return Response(
                {'error': 'Không có streak để khôi phục'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Tạo record khôi phục
        month_year = today.strftime('%Y-%m')
        restoration = StreakRestoration.objects.create(
            user=user,
            month_year=month_year,
            restored_streak_value=previous_streak,
            restored_at=timezone.now()
        )
        
        # Tạo hoặc cập nhật LessonProgress record cho ngày hôm qua để "khôi phục" streak
        # Tìm lesson progress gần nhất (có completed hoặc video_watched)
        last_progress = LessonProgress.objects.filter(
            student=user
        ).filter(
            Q(completed=True) | Q(video_watched=True)
        ).order_by('-last_accessed_at').first()
        
        if last_progress:
            # Cập nhật last_accessed_at và completed_at của progress gần nhất thành hôm qua
            # để streak được tính lại đúng
            yesterday_datetime = timezone.make_aware(
                datetime.combine(yesterday, datetime.min.time().replace(hour=12))  # 12:00 PM
            )
            last_progress.last_accessed_at = yesterday_datetime
            # Đảm bảo có completed_at hoặc completed/video_watched để streak được tính
            if not last_progress.completed_at:
                last_progress.completed_at = yesterday_datetime
            last_progress.save(update_fields=['last_accessed_at', 'completed_at'])
        
        restoration_count = StreakRestoration.get_restoration_count_this_month(user)
        
        return Response({
            'success': True,
            'message': f'Đã khôi phục streak {previous_streak} ngày!',
            'restored_streak': previous_streak,
            'restoration_count': restoration_count,
            'remaining_restorations': 2 - restoration_count
        })
    
    def _get_daily_goal(self, user):
        """Helper method để tính daily goal (copy từ AILearningAnalyzerView)"""
        today = timezone.localdate()
        tz = timezone.get_current_timezone()
        lesson_qs, exercise_qs, game_qs, activity_dates = _get_activity_qs_and_dates(user, tz)

        completed_today = (
            lesson_qs.filter(
                Q(completed_date=today) | Q(accessed_date=today)
            ).distinct().count()
            + exercise_qs.filter(finished_date=today).distinct().count()
            + game_qs.filter(completed_date=today).distinct().count()
        )

        return {
            "target": 2,
            "completed": completed_today,
            "streak": _compute_streak(activity_dates, today),
        }
