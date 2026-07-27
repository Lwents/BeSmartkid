from typing import Any, Dict
from django.http import HttpResponse
from rest_framework import status, permissions, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser

# Import your serializers and services
from activities.serializers import (
    ExerciseModelSerializer,
    QuestionModelSerializer,
    ChoiceModelSerializer,
    StartAttemptSerializer,
    SubmitAnswerSerializer,
    FinalizeAttemptSerializer,
    ExerciseAttemptModelSerializer,
    ExerciseAnswerModelSerializer,
    exercise_domain_to_response,
    attempt_domain_to_response,
)
from activities.services import (
    get_exercise,
    list_exercises,
    save_exercise,
    delete_exercise,
    add_question,
    delete_question,
    add_choice,
    delete_choice,
    start_attempt,
    submit_answer,
    finalize_attempt,
    regrade_attempt,
    get_attempt_summary,
    exercise_stats,
    export_results_csv,
)
from activities.services import ServiceError, NotFoundError, ValidationError, PermissionDenied
from activities.services.ai_question_generator import (
    normalize_ai_questions,
    parse_ai_questions,
)
from activities.api.permissions import IsAdminOrReadOnly
from activities.services.exercise_access_service import (
    can_manage_course,
    can_manage_exercise,
    can_view_exercise,
    course_from_exercise_payload,
    is_admin,
    is_student,
    is_teacher,
    student_can_access_exercise,
)
import os
import time
import requests

# Models used for permission checks or lookups (optional)
from django.apps import apps
ExerciseModel = apps.get_model("activities", "Exercise")
ExerciseAttemptModel = apps.get_model("activities", "ExerciseAttempt")
ExerciseAnswerModel = apps.get_model("activities", "ExerciseAnswer")


class ExerciseListCreateView(APIView):
    """
    GET /api/activities/exercises/  -> list exercises (optional filtering by lesson)
    POST /api/activities/exercises/ -> create exercise (admin/instructor)
    """
    permission_classes = [IsAdminOrReadOnly]

    def get(self, request: Request):
        lesson_id = request.query_params.get("lesson_id")
        include_stats = request.query_params.get("include_stats", "false").lower() == "true"
        q = request.query_params.get("q", "").strip()
        status_filter = request.query_params.get("status", "").strip()
        level_filter = request.query_params.get("level", "").strip()
        
        filters = {}
        if lesson_id:
            filters["lesson_id"] = lesson_id
        domains = list_exercises(filters=filters)
        data = [ExerciseModelSerializer.from_domain(d) for d in domains]

        exercise_models = {
            str(exercise.id): exercise
            for exercise in ExerciseModel.objects.filter(
                id__in=[item["id"] for item in data]
            ).select_related("settings", "lesson__module__course")
        }
        if is_admin(request.user):
            pass
        elif is_teacher(request.user):
            data = [
                item for item in data
                if can_manage_exercise(request.user, exercise_models.get(str(item["id"])))
            ]
        elif is_student(request.user):
            data = [
                item for item in data
                if student_can_access_exercise(
                    request.user,
                    exercise_models.get(str(item["id"])),
                )
            ]
        else:
            data = []
        
        # Filter by search query (title)
        if q:
            q_lower = q.lower()
            data = [item for item in data if q_lower in (item.get("title") or "").lower()]
        
        # Filter by status (published/draft)
        if status_filter:
            if status_filter == "published":
                data = [item for item in data if item.get("published", False)]
            elif status_filter == "draft":
                data = [item for item in data if not item.get("published", False)]
        
        # Filter by level
        if level_filter:
            level_lower = level_filter.lower()
            data = [item for item in data if level_lower in (item.get("level") or "").lower()]
        
        # Loại bỏ bài luyện tập AI (không hiển thị trong danh sách bài kiểm tra)
        # Các bài AI Practice có title bắt đầu bằng "AI Practice" hoặc có metadata type = 'ai_practice'
        data = [item for item in data if not (
            (item.get("title") or "").startswith("AI Practice") or
            (item.get("metadata") or {}).get("type") == "ai_practice"
        )]

        # Add stats if requested
        if include_stats:
            from activities.services.analytic_service import exercise_stats
            for item in data:
                try:
                    stats = exercise_stats(str(item["id"]))
                    item["submissions"] = stats.get("submissions", 0)
                    item["avgScore"] = stats.get("avgScore", 0)
                    item["avg_score"] = stats.get("avgScore", 0)  # Alias
                    item["passRate"] = stats.get("passRate", 0)
                    item["pass_rate"] = stats.get("passRate", 0)  # Alias
                except Exception:
                    item["submissions"] = 0
                    item["avgScore"] = 0
                    item["avg_score"] = 0
                    item["passRate"] = 0
                    item["pass_rate"] = 0

        # Attach current user's latest attempt info so FE biết đã làm hay chưa
        if request.user and request.user.is_authenticated and data:
            ex_ids = [item["id"] for item in data if item.get("id")]
            attempt_map = {}
            qs = ExerciseAttemptModel.objects.filter(
                exercise_id__in=ex_ids,
                student=request.user
            ).order_by("exercise_id", "-started_at")
            for att in qs:
                key = str(att.exercise_id)
                # keep first (latest ordered by started_at desc per exercise)
                if key not in attempt_map:
                    attempt_map[key] = att
            for item in data:
                att = attempt_map.get(str(item.get("id")))
                if att:
                    item["my_attempt"] = {
                        "id": str(att.id),
                        "finished_at": att.finished_at.isoformat() if att.finished_at else None,
                        "score": float(att.score) if att.score is not None else None,
                    }
                    item["done"] = bool(att.finished_at)
                else:
                    item["my_attempt"] = None
                    item["done"] = False
        
        return Response(data)

    def post(self, request: Request):
        serializer = ExerciseModelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        course = course_from_exercise_payload(request.data)
        if not is_admin(request.user):
            if course is None:
                return Response(
                    {"detail": "Bài kiểm tra phải thuộc một khóa học hợp lệ."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not can_manage_course(request.user, course):
                return Response(
                    {"detail": "Bạn không có quyền tạo bài kiểm tra cho khóa học này."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        # map to domain
        domain = serializer.to_domain()
        try:
            created = save_exercise(domain)
        except (ValidationError, ServiceError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ExerciseModelSerializer.from_domain(created), status=status.HTTP_201_CREATED)


class ExerciseDetailView(APIView):
    """
    GET /api/activities/exercises/{id}/
    PATCH /api/activities/exercises/{id}/
    DELETE /api/activities/exercises/{id}/
    """
    permission_classes = [IsAdminOrReadOnly]

    def get(self, request: Request, exercise_id: str):
        try:
            model = ExerciseModel.objects.select_related(
                "settings", "lesson__module__course"
            ).get(id=exercise_id)
        except ExerciseModel.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if not can_view_exercise(request.user, model):
            return Response({"detail": "Không được phép truy cập"}, status=status.HTTP_403_FORBIDDEN)
        domain = get_exercise(exercise_id)
        return Response(ExerciseModelSerializer.from_domain(domain))

    def patch(self, request: Request, exercise_id: str):
        # partial update; load model, then merge changes using serializer
        try:
            model = ExerciseModel.objects.select_related(
                "settings", "lesson__module__course"
            ).prefetch_related("questions__choices").get(id=exercise_id)
        except ExerciseModel.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if not can_manage_exercise(request.user, model):
            return Response({"detail": "Không được phép chỉnh sửa"}, status=status.HTTP_403_FORBIDDEN)

        incoming_settings = request.data.get("settings") or {}
        changes_course = "lesson" in request.data or (
            hasattr(incoming_settings, "__contains__") and "course_id" in incoming_settings
        )
        if changes_course:
            target_course = course_from_exercise_payload(request.data)
            if target_course is None:
                return Response(
                    {"detail": "Khóa học hoặc bài học được chọn không hợp lệ."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not can_manage_course(request.user, target_course):
                return Response(
                    {"detail": "Bạn không có quyền chuyển bài kiểm tra sang khóa học này."},
                    status=status.HTTP_403_FORBIDDEN,
                )

        serializer = ExerciseModelSerializer(instance=model, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        domain = serializer.to_domain()
        try:
            updated = save_exercise(domain)
        except (ValidationError, ServiceError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ExerciseModelSerializer.from_domain(updated))

    def delete(self, request: Request, exercise_id: str):
        try:
            model = ExerciseModel.objects.select_related(
                "settings", "lesson__module__course"
            ).get(id=exercise_id)
        except ExerciseModel.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if not can_manage_exercise(request.user, model):
            return Response({"detail": "Không được phép xóa"}, status=status.HTTP_403_FORBIDDEN)
        try:
            delete_exercise(exercise_id)
        except NotFoundError:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class GenerateQuestionsAIView(APIView):
    """
    POST /api/activities/ai/generate-questions/
    Multipart body: file (PDF/DOCX/TXT), count, level
    Đọc nội dung tài liệu giáo viên tải lên, gửi cho OpenRouter để sinh câu hỏi
    bám theo đúng nội dung tài liệu.
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminOrReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    MAX_FILE_BYTES = 20 * 1024 * 1024
    MAX_TEXT_CHARS = 15000
    MAX_QUESTIONS = 50
    BATCH_SIZE = 8
    EXTRA_GENERATION_CALLS = 3

    def post(self, request: Request):
        upload = request.FILES.get("file")
        if not upload:
            return Response(
                {"detail": "Cần chọn tài liệu (PDF, Word hoặc text) để tạo câu hỏi."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if upload.size and upload.size > self.MAX_FILE_BYTES:
            return Response(
                {"detail": "Tài liệu quá lớn (tối đa 20MB)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            extracted_text = self._extract_text(upload)
        except Exception as exc:  # noqa: BLE001
            return Response(
                {"detail": f"Không đọc được nội dung tài liệu: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        extracted_text = (extracted_text or "").strip()
        if not extracted_text:
            return Response(
                {"detail": "Tài liệu không có nội dung văn bản để tạo câu hỏi."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(extracted_text) > self.MAX_TEXT_CHARS:
            extracted_text = extracted_text[: self.MAX_TEXT_CHARS]

        level = request.data.get("level", "")
        try:
            count = int(request.data.get("count") or 10)
        except (TypeError, ValueError):
            return Response(
                {"detail": f"Số câu hỏi phải là một số từ 1 đến {self.MAX_QUESTIONS}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if count < 1 or count > self.MAX_QUESTIONS:
            return Response(
                {"detail": f"Số câu hỏi phải từ 1 đến {self.MAX_QUESTIONS}."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        model = (
            request.data.get("model")
            or os.getenv("OPENROUTER_MODEL")
            or os.getenv("DEEPSEEK_MODEL")
            or "openai/gpt-4o"
        )

        questions = []
        seen_prompts = set()
        errors = []
        model_used = model
        minimum_calls = (count + self.BATCH_SIZE - 1) // self.BATCH_SIZE
        max_calls = minimum_calls + self.EXTRA_GENERATION_CALLS

        for _ in range(max_calls):
            remaining = count - len(questions)
            if remaining <= 0:
                break
            batch_count = min(self.BATCH_SIZE, remaining)
            prompt = self._generation_prompt(
                extracted_text,
                level,
                batch_count,
                [item["text"] for item in questions],
            )
            ai_result = self._call_openrouter_api(
                prompt,
                model=model,
                expected_count=batch_count,
            )
            if ai_result.get("error"):
                errors.append(ai_result["error"])
                if len(errors) >= self.EXTRA_GENERATION_CALLS:
                    break
                continue
            model_used = ai_result.get("model", model_used)
            candidates = parse_ai_questions(ai_result.get("text", ""))
            questions.extend(normalize_ai_questions(
                candidates,
                seen_prompts=seen_prompts,
                limit=remaining,
            ))

        if not questions:
            detail = errors[-1] if errors else "AI chưa tạo được câu hỏi hợp lệ."
            return Response({"detail": detail}, status=status.HTTP_502_BAD_GATEWAY)

        questions = questions[:count]
        complete = len(questions) == count
        return Response({
            "model": model_used,
            "questions": questions,
            "requestedCount": count,
            "generatedCount": len(questions),
            "complete": complete,
            "warning": "" if complete else (
                f"AI chỉ tạo được {len(questions)}/{count} câu hợp lệ. "
                "Bạn có thể thử lại với tài liệu rõ ràng hơn."
            ),
        })

    def _generation_prompt(self, extracted_text, level, count, existing_questions):
        avoid_repeats = ""
        if existing_questions:
            recent = existing_questions[-self.MAX_QUESTIONS:]
            avoid_repeats = (
                "\nKHÔNG được lặp lại các câu đã tạo sau:\n- "
                + "\n- ".join(recent)
                + "\n"
            )
        return (
            f"Bạn là trợ lý tạo đề thi tiểu học. Dưới đây là nội dung một tài liệu bài học"
            f", phù hợp trình độ \"{level or 'Tiểu học'}\".\n"
            f"Hãy dựa vào ĐÚNG nội dung tài liệu này để tạo CHÍNH XÁC {count} câu hỏi trắc nghiệm."
            " Không được bịa thông tin ngoài tài liệu.\n\n"
            "=== NỘI DUNG TÀI LIỆU ===\n"
            f"{extracted_text}\n"
            "=== HẾT TÀI LIỆU ===\n\n"
            "QUY TẮC BẮT BUỘC:\n"
            "- CHỈ tạo câu hỏi loại 'single' (trắc nghiệm 1 đáp án đúng) hoặc 'boolean' (đúng/sai).\n"
            "- Mỗi câu hỏi 'single' phải có 3-4 choices và correct_indices chứa index đáp án đúng.\n"
            "- Câu hỏi 'boolean' có correct_answer là true hoặc false.\n\n"
            "- Không để trống câu hỏi, không để trống phương án, không lặp phương án.\n"
            "- Không đánh số thứ tự ở đầu nội dung câu hỏi.\n"
            f"{avoid_repeats}\n"
            "Trả về JSON thuần (KHÔNG có markdown code block):\n"
            "{\n"
            '  "questions": [\n'
            '    {"type": "single", "text": "Câu hỏi?", "score": 1, "choices": ["A", "B", "C", "D"], "correct_indices": [0]},\n'
            '    {"type": "boolean", "text": "Đúng hay sai?", "score": 1, "correct_answer": true}\n'
            "  ]\n"
            "}\n"
        )

    def _extract_text(self, upload) -> str:
        name = (getattr(upload, "name", "") or "").lower()
        content_type = (getattr(upload, "content_type", "") or "").lower()

        if name.endswith(".pdf") or "pdf" in content_type:
            from pypdf import PdfReader

            reader = PdfReader(upload)
            parts = []
            for page in reader.pages:
                parts.append(page.extract_text() or "")
            return "\n".join(parts)

        if name.endswith(".docx") or "wordprocessingml" in content_type:
            import docx

            document = docx.Document(upload)
            return "\n".join(paragraph.text for paragraph in document.paragraphs)

        if (
            name.endswith(".txt")
            or content_type.startswith("text/")
            or name.endswith(".md")
        ):
            return upload.read().decode("utf-8", errors="ignore")

        raise ValueError("Định dạng tài liệu không được hỗ trợ (chỉ PDF, DOCX, TXT).")


    def _call_openrouter_api(self, prompt, model, expected_count=5):
        """Gọi OpenRouter API để tạo câu hỏi"""
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            return {"error": "OpenRouter API chưa được cấu hình"}

        base_url = (
            os.getenv("OPENROUTER_BASE_URL")
            or "https://openrouter.ai/api/v1"
        ).rstrip("/")
        url = f"{base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://smartkid.local",
            "X-Title": "SmartKid AI Question Generator",
        }

        try:
            resp = requests.post(
                url,
                headers=headers,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max(2400, min(6000, expected_count * 550)),
                    "temperature": 0.2,
                    "stream": False,
                },
                timeout=90,
            )

            if resp.status_code == 200:
                data = resp.json()
                try:
                    text = data.get("choices", [])[0].get("message", {}).get("content", "")
                    if text and text.strip():
                        return {"text": text.strip(), "model": model, "raw": data}
                    return {"error": "OpenRouter trả về nội dung rỗng"}
                except (IndexError, KeyError, TypeError) as e:
                    return {"error": f"Lỗi parse OpenRouter: {str(e)}"}

            try:
                error_data = resp.json()
                error_msg = error_data.get("error", {}).get("message", f"Lỗi {resp.status_code}")
            except Exception:
                error_msg = f"Lỗi OpenRouter API {resp.status_code}"
            return {"error": error_msg}

        except Exception as e:
            return {"error": f"Lỗi kết nối OpenRouter: {str(e)}"}
