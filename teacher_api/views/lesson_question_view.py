from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.conf import settings

from teacher_api.permissions import IsTeacher
from activities.models import LessonQuestion, LessonQuestionReply, Notification


def avatar_for(user, request=None):
    """Get avatar URL for user, with fallback to profile avatar_url"""
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
    return {
        "id": str(rep.id),
        "user": rep.user.username,
        "avatar": avatar_for(rep.user, request),
        "gender": gender,
        "user_id": rep.user.id,
        "is_teacher": rep.is_teacher,
        "content": rep.content,
        "created_at": rep.created_at.isoformat(),
        "reactions_count": rep.reactions.count() if hasattr(rep, "reactions") else 0,
        "is_owner": bool(user and user.id == rep.user.id),
    }


def serialize_question(q: LessonQuestion, user=None, request=None):
    profile = getattr(q.student, "profile", None)
    gender = getattr(profile, "gender", None) if profile else None
    return {
        "id": str(q.id),
        "lesson_id": str(q.lesson_id),
        "student_id": q.student_id,
        "student": q.student.username,
        "avatar": avatar_for(q.student, request),
        "gender": gender,
        "content": q.content,
        "created_at": q.created_at.isoformat(),
        "replies": [serialize_reply(r, user=user, request=request) for r in q.replies.all()],
    }


class TeacherLessonQuestionView(APIView):
    """
    GET: list questions for a lesson (or all)
    POST /reply/ on an existing question
    PATCH/DELETE reply by teacher (own reply)
    """
    permission_classes = [IsAuthenticated, IsTeacher]

    def get(self, request):
        lesson_id = request.query_params.get("lesson_id")
        qs = LessonQuestion.objects.all().select_related(
            "student", "student__profile", "lesson"
        ).prefetch_related("replies__user", "replies__user__profile")
        if lesson_id:
            qs = qs.filter(lesson_id=lesson_id)
        data = [serialize_question(q, user=request.user, request=request) for q in qs.order_by("-created_at")]
        return Response({"items": data}, status=status.HTTP_200_OK)

    def post(self, request, pk):
        question = get_object_or_404(LessonQuestion, id=pk)
        content = (request.data.get("content") or "").strip()
        if len(content) < 2:
            return Response({"detail": "Nội dung quá ngắn"}, status=status.HTTP_400_BAD_REQUEST)

        rep = LessonQuestionReply.objects.create(
            question=question,
            user=request.user,
            content=content,
            is_teacher=True,
        )

        # Notify student
        Notification.objects.create(
            user=question.student,
            title=f"Giáo viên trả lời: {question.lesson.title}",
            message=content,
            type="info",
            category="lesson_question_reply",
            metadata={
                "lesson_question_id": str(question.id),
                "lesson_id": str(question.lesson_id),
                "course_id": str(question.lesson.module.course_id) if question.lesson.module else None,
                "teacher_id": str(request.user.id),
                "teacher": request.user.username,
                "reply_id": str(rep.id),
            },
        )

        return Response({"item": serialize_question(question, user=request.user, request=request)}, status=status.HTTP_201_CREATED)

    def patch(self, request, pk):
        rep = get_object_or_404(LessonQuestionReply, id=pk, user=request.user)
        content = (request.data.get("content") or "").strip()
        if len(content) < 2:
            return Response({"detail": "Nội dung quá ngắn"}, status=status.HTTP_400_BAD_REQUEST)
        rep.content = content
        rep.save(update_fields=["content"])
        return Response({"item": serialize_question(rep.question, user=request.user, request=request)}, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        rep = get_object_or_404(LessonQuestionReply, id=pk, user=request.user)
        Notification.objects.filter(metadata__reply_id=str(rep.id)).delete()
        q = rep.question
        rep.delete()
        return Response({"item": serialize_question(q, user=request.user, request=request)}, status=status.HTTP_200_OK)
