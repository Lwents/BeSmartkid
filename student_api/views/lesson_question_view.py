import os
import time
import requests as http_requests

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from student_api.permissions import IsStudent
from django.conf import settings
from content.models import Lesson
from activities.models import Notification, LessonQuestion, LessonQuestionReply, LessonQuestionReport
from django.contrib.auth import get_user_model
from django.http import StreamingHttpResponse
import json


def avatar_for(user, request):
    """Get avatar URL for user, with fallback to profile avatar_url and default avatar"""
    if not user:
        return None
    
    # Try to get from profile first
    try:
        profile = getattr(user, "profile", None)
        if profile:
            avatar_path = getattr(profile, "avatar_url", None)
            if avatar_path and avatar_path.strip():
                # Handle different avatar URL formats
                if avatar_path.startswith(("http://", "https://", "data:")):
                    return avatar_path
                if avatar_path.startswith("/"):
                    return request.build_absolute_uri(avatar_path) if request else avatar_path
                # Relative path - build full URL
                media_url = getattr(settings, "MEDIA_URL", "/media/").rstrip("/")
                base = request.build_absolute_uri(media_url + "/") if request else media_url + "/"
                return f"{base}{avatar_path.lstrip('/')}"
    except Exception:
        pass
    
    # Fallback: check if user has avatar attribute directly (for backward compatibility)
    try:
        if hasattr(user, "avatar") and user.avatar:
            avatar_path = str(user.avatar)
            if avatar_path.startswith(("http://", "https://", "data:")):
                return avatar_path
            if request:
                return request.build_absolute_uri(avatar_path)
            return avatar_path
    except Exception:
        pass
    
    # Return None to let frontend handle default avatar based on gender
    # Frontend will use getAvatarSrc() which handles boy/girl avatars based on gender
    return None


def serialize_reply(rep: LessonQuestionReply, user=None, request=None):
    profile = getattr(rep.user, "profile", None)
    gender = getattr(profile, "gender", None) if profile else None
    
    # Safely get reactions_count and reacted
    # If model hasn't been migrated yet, these will default to 0 and False
    reactions_count = 0
    reacted = False
    try:
        reactions_count = rep.reactions.count()
        if user:
            reacted = rep.reactions.filter(user=user).exists()
    except (AttributeError, Exception):
        # Reactions relation doesn't exist (migration not run) - silently use defaults
        pass
    
    return {
        "id": str(rep.id),
        "user": rep.user.username,
        "avatar": avatar_for(rep.user, request),
        "gender": gender,
        "user_id": rep.user.id,
        "is_owner": bool(user and user.id == rep.user.id),
        "is_teacher": rep.is_teacher,
        "content": rep.content,
        "created_at": rep.created_at.isoformat(),
        "reactions_count": reactions_count,
        "reacted": reacted,
    }


def serialize_question(q: LessonQuestion, user=None, request=None):
    try:
        profile = getattr(q.student, "profile", None)
        gender = getattr(profile, "gender", None) if profile else None
        
        # Safely get reactions_count and reacted
        # If model hasn't been migrated yet, these will default to 0 and False
        reactions_count = 0
        reacted = False
        try:
            reactions_count = q.reactions.count()
            if user:
                reacted = q.reactions.filter(user=user).exists()
        except (AttributeError, Exception):
            # Reactions relation doesn't exist (migration not run) - silently use defaults
            pass
        
        # Safely serialize replies
        replies = []
        try:
            replies = [serialize_reply(r, user=user, request=request) for r in q.replies.all()]
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error serializing replies for question {q.id}: {e}")
            replies = []
        
        return {
            "id": str(q.id),
            "lesson_id": str(q.lesson_id),
            "student_id": q.student_id,
            "student": q.student.username,
            "avatar": avatar_for(q.student, request),
            "gender": gender,
            "is_owner": bool(user and user.id == q.student_id),
            "content": q.content,
            "created_at": q.created_at.isoformat(),
            "reactions_count": reactions_count,
            "reacted": reacted,
            "replies": replies,
        }
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error serializing question {q.id if q else 'unknown'}: {e}", exc_info=True)
        # Return minimal data to prevent complete failure
        return {
            "id": str(q.id) if q else "",
            "lesson_id": str(q.lesson_id) if q else "",
            "student_id": q.student_id if q else None,
            "student": q.student.username if q and q.student else "",
            "avatar": None,
            "gender": None,
            "is_owner": False,
            "content": q.content if q else "",
            "created_at": q.created_at.isoformat() if q and hasattr(q, 'created_at') else "",
            "reactions_count": 0,
            "reacted": False,
            "replies": [],
        }


class StudentLessonQuestionView(APIView):
    """
    GET /api/student/lesson-questions/?lesson_id=...
    POST /api/student/lesson-questions/ { lesson_id, content }
    PATCH /api/student/lesson-questions/<id>/ { content }
    DELETE /api/student/lesson-questions/<id>/
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request):
        lesson_id = request.query_params.get("lesson_id")
        if not lesson_id:
            return Response({"detail": "lesson_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        qs = LessonQuestion.objects.filter(lesson_id=lesson_id).select_related(
            "student", 
            "student__profile"
        ).prefetch_related(
            "replies__user",
            "replies__user__profile",
            "replies__reactions",
        )
        # Note: reactions for question will be handled safely in serialize_question
        data = [serialize_question(q, user=request.user, request=request) for q in qs.order_by("-created_at")]
        return Response({"items": data}, status=status.HTTP_200_OK)

    def post(self, request):
        content = (request.data.get("content") or "").strip()
        lesson_id = request.data.get("lesson_id")
        # Kiểm tra xem có phải là tương tác với AI không (không gửi thông báo cho giáo viên)
        is_ai_interaction = request.data.get("is_ai_interaction", False)

        if not lesson_id:
            return Response({"detail": "lesson_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        if not content:
            return Response({"detail": "Nội dung không được để trống"}, status=status.HTTP_400_BAD_REQUEST)

        lesson = get_object_or_404(Lesson, id=lesson_id)
        course = lesson.module.course if lesson.module else None
        teacher = getattr(course, "owner", None)
        if teacher is None:
            return Response({"detail": "Không tìm thấy giáo viên phụ trách"}, status=status.HTTP_400_BAD_REQUEST)

        student = request.user
        q = LessonQuestion.objects.create(lesson=lesson, student=student, content=content)

        # Chỉ gửi thông báo cho giáo viên nếu KHÔNG phải là tương tác với AI
        if not is_ai_interaction:
            course = lesson.module.course if lesson.module else None
            teacher = getattr(course, "owner", None)
            if teacher:
                course_title = course.title if course else "Khóa học"
                lesson_title = lesson.title
                Notification.objects.create(
                    user=teacher,
                    title=f"Học sinh hỏi về bài: {lesson.title}",
                    message=f"[{course_title}] {content}",
                    type="info",
                    category="lesson_question",
                    metadata={
                        "lesson_question_id": str(q.id),
                        "lesson_id": str(lesson.id),
                        "course_id": str(course.id) if course else None,
                        "student_id": str(student.id),
                        "student": student.username,
                        "lesson_title": lesson.title,
                        "course_title": course_title,
                    },
                )

        # Trả về câu hỏi vừa tạo
        data = serialize_question(q, user=request.user, request=request)
        return Response(data, status=status.HTTP_201_CREATED)

    def patch(self, request, pk=None):
        if not pk:
            return Response({"detail": "question id required"}, status=status.HTTP_400_BAD_REQUEST)
        q = get_object_or_404(LessonQuestion, id=pk)
        if q.student_id != request.user.id:
            return Response({"detail": "Không được phép sửa"}, status=status.HTTP_403_FORBIDDEN)
        content = (request.data.get("content") or "").strip()
        if not content:
            return Response({"detail": "Nội dung không được để trống"}, status=status.HTTP_400_BAD_REQUEST)
        q.content = content
        q.save(update_fields=["content"])
        return Response({"item": serialize_question(q, user=request.user, request=request)}, status=status.HTTP_200_OK)

    def delete(self, request, pk=None):
        if not pk:
            return Response({"detail": "question id required"}, status=status.HTTP_400_BAD_REQUEST)
        q = get_object_or_404(LessonQuestion, id=pk)
        if q.student_id != request.user.id:
            return Response({"detail": "Không được phép xóa"}, status=status.HTTP_403_FORBIDDEN)
        # Xóa notification liên quan đến câu hỏi và các reply con
        reply_ids = list(q.replies.values_list("id", flat=True))
        Notification.objects.filter(metadata__lesson_question_id=str(q.id)).delete()
        if reply_ids:
          Notification.objects.filter(metadata__reply_id__in=[str(rid) for rid in reply_ids]).delete()
        q.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class StudentLessonQuestionReplyView(APIView):
    """
    POST /api/student/lesson-questions/<id>/reply/
    PATCH /api/student/lesson-questions/replies/<reply_id>/
    DELETE /api/student/lesson-questions/replies/<reply_id>/
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def post(self, request, pk):
        question = get_object_or_404(LessonQuestion, id=pk)
        content = (request.data.get("content") or "").strip()
        # Kiểm tra xem có phải là tương tác với AI không (không gửi thông báo cho giáo viên)
        is_ai_interaction = request.data.get("is_ai_interaction", False)
        
        if not content:
            return Response({"detail": "Nội dung không được để trống"}, status=status.HTTP_400_BAD_REQUEST)

        rep = LessonQuestionReply.objects.create(
            question=question,
            user=request.user,
            content=content,
            is_teacher=False,
        )

        # Chỉ gửi thông báo cho giáo viên nếu KHÔNG phải là tương tác với AI
        if not is_ai_interaction:
            course = question.lesson.module.course if question.lesson.module else None
            teacher = getattr(course, "owner", None)
            if teacher:
                course_title = course.title if course else "Khóa học"
                lesson_title = question.lesson.title
                Notification.objects.create(
                    user=teacher,
                    title=f"Học sinh trả lời thảo luận: {lesson_title}",
                    message=f"[{course_title}] {content}",
                    type="info",
                    category="lesson_question_reply",
                    metadata={
                        "lesson_question_id": str(question.id),
                        "lesson_id": str(question.lesson_id),
                        "course_id": str(course.id) if course else None,
                        "course_title": course_title,
                        "lesson_title": lesson_title,
                    "student_id": str(request.user.id),
                    "student": request.user.username,
                },
            )

        question.refresh_from_db()
        return Response({"item": serialize_question(question, user=request.user, request=request)}, status=status.HTTP_201_CREATED)

    def patch(self, request, reply_id=None):
        if not reply_id:
            return Response({"detail": "reply id required"}, status=status.HTTP_400_BAD_REQUEST)
        rep = get_object_or_404(LessonQuestionReply, id=reply_id)
        if rep.user_id != request.user.id:
            return Response({"detail": "Không được phép sửa"}, status=status.HTTP_403_FORBIDDEN)
        content = (request.data.get("content") or "").strip()
        if not content:
            return Response({"detail": "Nội dung không được để trống"}, status=status.HTTP_400_BAD_REQUEST)
        rep.content = content
        rep.save(update_fields=["content"])
        question = rep.question
        question.refresh_from_db()
        return Response({"item": serialize_question(question, user=request.user, request=request)}, status=status.HTTP_200_OK)

    def delete(self, request, reply_id=None):
        if not reply_id:
            return Response({"detail": "reply id required"}, status=status.HTTP_400_BAD_REQUEST)
        rep = get_object_or_404(LessonQuestionReply, id=reply_id)
        if rep.user_id != request.user.id:
            return Response({"detail": "Không được phép xóa"}, status=status.HTTP_403_FORBIDDEN)
        question = rep.question
        Notification.objects.filter(metadata__reply_id=str(rep.id)).delete()
        rep.delete()
        return Response({"item": serialize_question(question, user=request.user, request=request)}, status=status.HTTP_200_OK)


class StudentLessonQuestionReactionView(APIView):
    """
    POST /api/student/lesson-question-replies/<reply_id>/react/
    Toggle like (emoji default 'like')
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def post(self, request, reply_id):
        emoji = (request.data.get("emoji") or "like")[:16]
        reply = get_object_or_404(LessonQuestionReply, id=reply_id)
        reaction, created = reply.reactions.get_or_create(user=request.user, defaults={"emoji": emoji})
        if not created:
            # toggle off
            reaction.delete()
            reacted = False
        else:
            reacted = True
        return Response(
            {
                "reacted": reacted,
                "reactions_count": reply.reactions.count(),
            },
            status=status.HTTP_200_OK,
        )


class StudentLessonQuestionQuestionReactionView(APIView):
    """
    POST /api/student/lesson-questions/<question_id>/react/
    Toggle like (emoji default 'like') for a question
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def post(self, request, question_id=None, pk=None):
        # Accept both path converters: question_id or pk (DRF may pass pk)
        question_id = question_id or pk
        emoji = (request.data.get("emoji") or "like")[:16]
        question = get_object_or_404(LessonQuestion, id=question_id)
        from activities.models import LessonQuestionReaction
        
        try:
            reaction, created = LessonQuestionReaction.objects.get_or_create(
                question=question,
                user=request.user,
                defaults={"emoji": emoji}
            )
            if not created:
                # toggle off
                reaction.delete()
                reacted = False
            else:
                reacted = True
            
            # Safely get reactions_count
            try:
                reactions_manager = getattr(question, 'reactions', None)
                if reactions_manager is not None:
                    reactions_count = reactions_manager.count()
                else:
                    reactions_count = 0
            except Exception:
                reactions_count = 0
        except Exception as e:
            # If model doesn't support question reactions yet (migration not run)
            return Response(
                {"detail": "Reaction feature not available. Please run migrations."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        
        return Response(
            {
                "reacted": reacted,
                "reactions_count": reactions_count,
            },
            status=status.HTTP_200_OK,
        )


class StudentLessonQuestionReportView(APIView):
    """
    POST /api/student/lesson-question-report/ {question_id|reply_id, reason, detail}
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def post(self, request):
        question_id = request.data.get("question_id")
        reply_id = request.data.get("reply_id")
        reason = (request.data.get("reason") or "Vi phạm nội dung")[:255]
        detail = (request.data.get("detail") or "").strip()
        if not question_id and not reply_id:
            return Response({"detail": "question_id hoặc reply_id là bắt buộc"}, status=status.HTTP_400_BAD_REQUEST)

        question = None
        reply = None
        if question_id:
            question = get_object_or_404(LessonQuestion, id=question_id)
        if reply_id:
            reply = get_object_or_404(LessonQuestionReply, id=reply_id)

        report = LessonQuestionReport.objects.create(
            reporter=request.user,
            question=question,
            reply=reply,
            reason=reason,
            detail=detail,
        )

        # Gửi thông báo cho admin/staff
        User = get_user_model()
        admins = User.objects.filter(is_staff=True, is_active=True)
        
        # Tạo message chi tiết hơn
        question_text = question.content[:100] if question else None
        reply_text = reply.content[:100] if reply else None
        
        # Lấy thông tin user bị báo cáo
        reported_user = None
        reported_username = "N/A"
        if question:
            reported_user = question.student
            reported_username = reported_user.username if reported_user else "N/A"
        elif reply:
            reported_user = reply.user
            reported_username = reported_user.username if reported_user else "N/A"
        
        report_message = f"Báo cáo vi phạm từ {request.user.username}\n"
        report_message += f"Người bị báo cáo: {reported_username}\n"
        report_message += f"Lý do: {reason}"
        if detail:
            report_message += f"\nChi tiết: {detail}"
        if question_text:
            report_message += f"\nNội dung câu hỏi: {question_text}"
        if reply_text:
            report_message += f"\nNội dung phản hồi: {reply_text}"
        
        for admin in admins:
            Notification.objects.create(
                user=admin,
                title="🚨 Báo cáo vi phạm hỏi đáp bài học",
                message=report_message,
                type="warning",
                category="lesson_question_report",
                metadata={
                    "report_id": str(report.id),
                    "question_id": str(question.id) if question else None,
                    "reply_id": str(reply.id) if reply else None,
                    "reporter_id": str(request.user.id),
                    "reporter": request.user.username,
                    "reporter_email": request.user.email,
                    "reported_user_id": str(reported_user.id) if reported_user else None,
                    "reported_username": reported_username,
                    "reported_email": reported_user.email if reported_user else None,
                    "reason": reason,
                    "detail": detail,
                    "lesson_id": str(question.lesson_id) if question else (str(reply.question.lesson_id) if reply else None),
                },
            )

        return Response({"detail": "Đã gửi báo cáo"}, status=status.HTTP_201_CREATED)


class StudentLessonQuestionAIAnswerView(APIView):
    """
    POST /api/student/lesson-questions/<question_id>/ai-answer/
    Gọi AI để trả lời câu hỏi của học sinh dựa trên nội dung bài học.
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def post(self, request, question_id):
        try:
            question = get_object_or_404(LessonQuestion, id=question_id)
            lesson = question.lesson
        except Exception as e:
            return Response({"detail": f"Không tìm thấy câu hỏi: {str(e)}"}, status=status.HTTP_404_NOT_FOUND)
        
        # Lấy API key
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            return Response({"detail": "OpenRouter API chưa được cấu hình"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        
        # Lấy context từ bài học
        lesson_context = self._get_lesson_context(lesson)
        
        # Lấy lịch sử hội thoại (câu hỏi gốc + các replies)
        conversation_history = self._get_conversation_history(question)
        
        # Tạo prompt với lịch sử hội thoại
        prompt = self._build_prompt(question.content, lesson_context, lesson, conversation_history)
        
        # Gọi trực tiếp OpenRouter với stream=True
        
        # Generator function để stream response
        def stream_response_generator():
            full_content = []
            
            # 1. Yield start signal (optional, for frontend readiness)
            # yield json.dumps({"status": "start"}) + "\n"

            try:
                # Call OpenRouter with stream
                for chunk in self._call_openrouter_stream(prompt):
                    if chunk:
                        full_content.append(chunk)
                        # Yield chunk data to client
                        yield json.dumps({"chunk": chunk}) + "\n"
                
                # Stream finished
                ai_text = "".join(full_content)
                ai_text = self._clean_markdown(ai_text)
                
                # 2. Save to DB
                User = get_user_model()
                ai_user = User.objects.filter(username="AI_Assistant").first()
                if not ai_user:
                    try:
                        ai_user = User.objects.create_user(
                            username="AI_Assistant",
                            email="ai@smartkid.local",
                            password=None,
                            is_active=False,
                            role="admin",
                        )
                    except:
                        course = question.lesson.module.course if question.lesson.module else None
                        ai_user = getattr(course, "owner", None)
                
                if ai_user and ai_text:
                    reply = LessonQuestionReply.objects.create(
                        question=question,
                        user=ai_user,
                        content=ai_text,
                        is_teacher=False,
                    )
                    # Yield final success message with ID
                    yield json.dumps({"done": True, "reply_id": str(reply.id)}) + "\n"
                    
            except Exception as e:
                print(f"Streaming error: {e}")
                yield json.dumps({"error": str(e)}) + "\n"

        return StreamingHttpResponse(stream_response_generator(), content_type="application/x-ndjson")
    
    def _get_lesson_context(self, lesson):
        """Lấy nội dung bài học để làm context cho AI"""
        context_parts = []
        song_info = ""  # Thông tin về bài hát nếu có
        
        # Lấy thông tin khóa học
        try:
            if lesson.module and lesson.module.course:
                course = lesson.module.course
                context_parts.append(f"Khóa học: {course.title}")
                if course.description:
                    context_parts.append(f"Mô tả khóa học: {course.description[:300]}")
        except Exception:
            pass
        
        # Tiêu đề và giới thiệu
        context_parts.append(f"Tiêu đề bài học: {lesson.title}")
        if lesson.introduction:
            context_parts.append(f"Giới thiệu bài học: {lesson.introduction[:500]}")
            # Kiểm tra xem introduction có chứa thông tin về bài hát không
            intro_lower = lesson.introduction.lower()
            if any(keyword in intro_lower for keyword in ['bài hát', 'ca sĩ', 'nhạc sĩ', 'sáng tác', 'remix', 'cover']):
                song_info += f"Thông tin bài hát từ giới thiệu: {lesson.introduction[:500]}\n"
        
        # Nội dung text trực tiếp từ lesson
        if lesson.text_content:
            context_parts.append(f"Nội dung chính:\n{lesson.text_content[:2000]}")
            # Kiểm tra xem text_content có chứa thông tin về bài hát không
            text_lower = lesson.text_content.lower()
            if any(keyword in text_lower for keyword in ['bài hát', 'ca sĩ', 'nhạc sĩ', 'sáng tác', 'remix', 'cover']):
                song_info += f"Thông tin bài hát từ nội dung: {lesson.text_content[:500]}\n"
        
        # Ưu tiên lấy video_transcript từ field nếu có
        if lesson.video_transcript:
            # Tăng độ dài transcript để có nhiều context hơn
            context_parts.append(f"[Nội dung video/Lời bài hát] {lesson.video_transcript[:4000]}")
        
        # Thêm thông tin về bài hát nếu có
        if song_info:
            context_parts.insert(1, f"THÔNG TIN VỀ BÀI HÁT:\n{song_info}")
        
        # Kiểm tra title có chứa thông tin về bài hát không
        title_lower = lesson.title.lower()
        if any(keyword in title_lower for keyword in ['remix', 'cover', 'bài hát', 'nhạc']):
            if not song_info:
                song_info = f"Tiêu đề bài học có thể liên quan đến bài hát: {lesson.title}\n"
                context_parts.insert(1, f"THÔNG TIN VỀ BÀI HÁT:\n{song_info}")
        
        # Lấy nội dung từ ContentBlock (chi tiết hơn)
        try:
            latest_version = lesson.versions.filter(status='published').order_by('-version').first()
            if not latest_version:
                latest_version = lesson.versions.order_by('-version').first()
            
            if latest_version:
                # Lấy content blocks từ database
                content_blocks = latest_version.content_blocks.order_by('position')
                
                lesson_content = []
                for block in content_blocks[:15]:  # Giới hạn 15 blocks
                    payload = block.payload or {}
                    
                    if block.type == 'text':
                        # Block text - nội dung chính
                        text = payload.get('text', '') or payload.get('content', '')
                        if text:
                            lesson_content.append(text[:800])
                    
                    elif block.type == 'introduction':
                        # Block giới thiệu
                        intro_text = payload.get('text', '') or payload.get('content', '')
                        if intro_text:
                            lesson_content.append(f"[Giới thiệu] {intro_text[:500]}")
                    
                    elif block.type == 'quiz':
                        # Block quiz - câu hỏi trong bài
                        quiz_text = payload.get('question', '') or payload.get('text', '')
                        if quiz_text:
                            lesson_content.append(f"[Câu hỏi trong bài] {quiz_text[:300]}")
                    
                    elif block.type == 'video':
                        # Video - lấy transcript nếu có (tăng độ dài để có nhiều context hơn)
                        transcript = payload.get('transcript', '') or payload.get('captions', '') or payload.get('tts_text', '')
                        if transcript:
                            lesson_content.append(f"[Nội dung video/Lời bài hát] {transcript[:2000]}")
                
                if lesson_content:
                    context_parts.append("NỘI DUNG BÀI HỌC CHI TIẾT:\n" + "\n\n".join(lesson_content))
                
                # Cũng kiểm tra content JSON nếu có
                if latest_version.content and isinstance(latest_version.content, dict):
                    json_content = latest_version.content
                    
                    # Lấy text từ các key phổ biến
                    for key in ['content', 'text', 'body', 'description', 'summary']:
                        if key in json_content and json_content[key]:
                            val = json_content[key]
                            if isinstance(val, str) and len(val) > 20:
                                context_parts.append(f"[{key}] {val[:500]}")
                    
                    # Lấy từ content_blocks trong JSON
                    json_blocks = json_content.get('content_blocks', []) or json_content.get('blocks', [])
                    for jblock in json_blocks[:10]:
                        if isinstance(jblock, dict):
                            jtext = jblock.get('text', '') or jblock.get('content', '') or jblock.get('body', '')
                            if jtext and len(jtext) > 20:
                                context_parts.append(jtext[:400])
        except Exception as e:
            # Log lỗi nhưng không fail
            pass
        
        # Giới hạn tổng độ dài context (tăng lên để có nhiều context hơn)
        full_context = "\n\n".join(context_parts)
        return full_context[:10000]  # Tăng từ 8000 lên 10000 ký tự để có nhiều context hơn
    
    def _get_conversation_history(self, question):
        """Lấy lịch sử hội thoại từ câu hỏi và các replies"""
        history = []
        
        # Câu hỏi gốc
        history.append(f"Học sinh: {question.content}")
        
        # Các replies theo thứ tự thời gian
        replies = question.replies.order_by('created_at')
        for reply in replies:
            if reply.user and reply.user.username == "AI_Assistant":
                history.append(f"AI: {reply.content[:500]}")  # Giới hạn độ dài
            else:
                history.append(f"Học sinh: {reply.content[:300]}")
        
        return "\n".join(history[-10:])  # Chỉ lấy 10 tin nhắn gần nhất
    
    def _build_prompt(self, question_content, lesson_context, lesson, conversation_history=""):
        """Tạo prompt cho AI"""
        # Nếu có lịch sử hội thoại, sử dụng prompt khác
        if conversation_history and len(conversation_history) > 50:
            return f"""Bạn là trợ lý học tập AI của SmartKid, đang hỗ trợ học sinh học bài "{lesson.title}".

THÔNG TIN BÀI HỌC:
{lesson_context}

LỊCH SỬ HỘI THOẠI:
{conversation_history}

YÊU CẦU TRẢ LỜI (QUAN TRỌNG - PHẢI TUÂN THỦ):
1. TRẢ LỜI TRỰC TIẾP, KHÔNG HỎI LẠI HỌC SINH
   - KHÔNG được hỏi "em đang tò mò đúng không?", "em muốn biết gì?"
   - TRẢ LỜI NGAY câu hỏi/tin nhắn MỚI NHẤT của học sinh
   - BẮT ĐẦU trả lời NGAY, không có câu mở đầu dài dòng

2. Nếu học sinh hỏi về nội dung bài học:
   - Đọc kỹ THÔNG TIN BÀI HỌC ở trên
   - Trả lời DỰA TRỰC TIẾP vào thông tin đó
   - Trả lời CỤ THỂ, không chung chung

3. Nếu học sinh hỏi về bài hát:
   - Đọc kỹ phần "THÔNG TIN VỀ BÀI HÁT" nếu có
   - Đọc kỹ phần "Nội dung video/Lời bài hát" để nhận biết bài hát
   - Nếu nhận biết được: Trả lời NGAY "Bài hát này là [TÊN BÀI HÁT] của [TÊN CA SĨ]"
   - Nếu không nhận biết được: Trả lời NGAY "Mình chưa nhận biết được bài hát này. Bạn có thể hỏi giáo viên nhé!"

4. Format trả lời:
   - Trả lời ngắn gọn (2-4 câu), đi thẳng vào vấn đề
   - Ngôn ngữ RẤT ĐƠN GIẢN, thân thiện, phù hợp học sinh tiểu học (6-11 tuổi)
   - Thêm 1 emoji phù hợp 🌟
   - Xưng "mình", gọi học sinh là "bạn" hoặc "em"
   - KHÔNG sử dụng markdown (**, ##, *, -, etc.). Chỉ dùng văn bản thuần túy.

5. CẤM:
   - Hỏi lại học sinh
   - Trả lời chung chung, không cụ thể
   - Lặp lại câu hỏi của học sinh
   - Nói vòng vo, không đi vào trọng tâm

Trả lời bằng tiếng Việt (văn bản thuần túy, không markdown):"""
        
        # Prompt cho câu hỏi đầu tiên
        return f"""Bạn là trợ lý học tập AI của SmartKid, hỗ trợ học sinh học bài "{lesson.title}".

THÔNG TIN BÀI HỌC:
{lesson_context}

TIN NHẮN CỦA HỌC SINH:
"{question_content}"

YÊU CẦU QUAN TRỌNG:
1. Nếu học sinh chỉ chào (hi, hello, xin chào...), hãy chào lại thân thiện và TÓM TẮT NGẮN GỌN nội dung bài học, sau đó gợi ý 2-3 câu hỏi học sinh có thể hỏi.
2. Nếu học sinh hỏi về nội dung bài học, hãy trả lời dựa trên thông tin bài học ở trên (đọc kỹ THÔNG TIN BÀI HỌC).
3. Nếu học sinh hỏi về bài hát (tên bài hát, ca sĩ, nhạc sĩ...), hãy:
   - Đọc kỹ phần "THÔNG TIN VỀ BÀI HÁT" nếu có
   - Đọc kỹ phần "Nội dung video/Lời bài hát" để nhận biết bài hát
   - Nếu nhận biết được, trả lời RÕ RÀNG: "Bài hát này là [TÊN BÀI HÁT] của [TÊN CA SĨ]"
   - Nếu không nhận biết được, thành thật nói và gợi ý hỏi giáo viên
4. Sử dụng ngôn ngữ RẤT ĐƠN GIẢN, thân thiện, phù hợp với học sinh tiểu học (6-11 tuổi).
5. Nếu câu hỏi không liên quan đến bài học, hãy nhẹ nhàng hướng dẫn học sinh quay lại nội dung bài.
6. Trả lời ngắn gọn, dễ hiểu (tối đa 200 từ).
7. Nếu không có đủ thông tin để trả lời, hãy gợi ý học sinh hỏi giáo viên.
8. Luôn khuyến khích và động viên học sinh.
9. KHÔNG sử dụng markdown (**, ##, *, -, etc.). Chỉ dùng văn bản thuần túy.
10. Dùng emoji phù hợp để sinh động hơn (🌟, 👍, 📚, ✨, etc.).
11. Gọi học sinh là "bạn" hoặc "em".
12. KHÔNG được trả lời chung chung - phải trả lời cụ thể dựa trên thông tin bài học.

Trả lời bằng tiếng Việt (văn bản thuần túy, không markdown):"""

    def _clean_markdown(self, text):
        """Loại bỏ markdown formatting để dễ đọc cho học sinh tiểu học"""
        import re
        
        # Loại bỏ bold (**text** hoặc __text__)
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)
        
        # Loại bỏ italic (*text* hoặc _text_)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'_(.+?)_', r'\1', text)
        
        # Loại bỏ headers (# ## ### etc.)
        text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
        
        # Loại bỏ bullet points (- hoặc *)
        text = re.sub(r'^\s*[-*]\s+', '• ', text, flags=re.MULTILINE)
        
        # Loại bỏ numbered lists với format "1." thành "1)"
        text = re.sub(r'^(\d+)\.\s+', r'\1) ', text, flags=re.MULTILINE)
        
        # Loại bỏ code blocks
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`(.+?)`', r'\1', text)
        
        # Loại bỏ links [text](url)
        text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
        
        # Loại bỏ multiple newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()
    
    def _call_openrouter_stream(self, prompt):
        """Gọi OpenRouter API với chế độ stream"""
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            yield "OpenRouter API chưa được cấu hình"
            return
        
        model = os.getenv("OPENROUTER_MODEL") or os.getenv("DEEPSEEK_MODEL") or "openai/gpt-4o"
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://smartkid.local",
            "X-Title": "SmartKid AI Assistant",
        }
        
        try:
            with http_requests.post(
                url,
                headers=headers,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1500,
                    "stream": True,
                },
                stream=True,
                timeout=60,
            ) as resp:
                if resp.status_code != 200:
                    yield f"Error {resp.status_code}"
                    return

                for line in resp.iter_lines():
                    if line:
                        line = line.decode("utf-8")
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                data_json = json.loads(data_str)
                                content = data_json.get("choices", [])[0].get("delta", {}).get("content", "")
                                if content:
                                    yield content
                            except:
                                pass
        except Exception as e:
            yield f"Stream Error: {str(e)}"
