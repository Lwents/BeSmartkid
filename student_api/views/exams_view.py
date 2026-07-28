import re
from django.db.models import Count, Q, Avg, Max
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from student_api.permissions import IsStudent
from activities.models import Exercise, ExerciseAttempt, ExerciseAnswer, Question, Choice
from activities.services import (
    get_exercise,
    start_attempt,
    submit_answer,
    finalize_attempt,
    get_attempt_summary,
)
from activities.services import NotFoundError, ValidationError, PermissionDenied
from content.models import Enrollment, Course
from activities.services.exercise_access_service import student_can_access_exercise


def _get_available_exam(student, exam_id):
    try:
        exercise = Exercise.objects.select_related(
            'settings', 'lesson__module__course'
        ).prefetch_related('questions__choices').get(id=exam_id)
    except Exercise.DoesNotExist:
        return None
    if exercise.lesson_id or not student_can_access_exercise(student, exercise):
        return None
    return exercise


def _student_question_payload(question):
    """Expose the question shape needed by students without leaking correct answers."""
    meta = question.meta if isinstance(question.meta, dict) else {}
    raw_type = str(
        meta.get('type') or meta.get('question_type') or meta.get('format') or 'mcq'
    ).strip().lower()
    question_type = {
        'single': 'mcq',
        'multiple_choice': 'mcq',
        'short': 'short_answer',
        'text': 'short_answer',
        'match': 'matching',
    }.get(raw_type, raw_type)
    if question_type not in {'mcq', 'short_answer', 'matching'}:
        question_type = 'mcq' if question.choices.exists() else 'short_answer'

    payload = {
        'id': str(question.id),
        'type': question_type,
        'text': question.prompt,
        'score': float(meta.get('points') or 1),
        'choices': [],
    }
    if question_type == 'mcq':
        payload['choices'] = [
            {'id': str(choice.id), 'text': choice.text}
            for choice in question.choices.all()
        ]
    elif question_type == 'matching':
        pairs = meta.get('pairs') if isinstance(meta.get('pairs'), list) else []
        if not pairs:
            choice_rows = list(question.choices.all())
            pairs = [
                {'left': choice_rows[index].text, 'right': choice_rows[index + 1].text}
                for index in range(0, len(choice_rows) - 1, 2)
            ]
        payload['leftItems'] = [
            {'id': f'L{index + 1}', 'text': str(pair.get('left') or '')}
            for index, pair in enumerate(pairs)
            if isinstance(pair, dict)
        ]
        payload['rightItems'] = [
            {'id': f'R{index + 1}', 'text': str(pair.get('right') or '')}
            for index, pair in enumerate(pairs)
            if isinstance(pair, dict)
        ]
    return payload


class StudentExamsListView(APIView):
    """
    GET /api/student/exams/
    Returns list of available exams (exercises) for student
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request):
        """Chỉ hiển thị bài kiểm tra thuộc khóa học học sinh đã ghi danh."""
        student = request.user
        
        # Get query parameters
        level = request.query_params.get('level', '').strip()  # 'Khối 1–2' or 'Khối 3–5'
        q = request.query_params.get('q', '').strip()
        
        # Lấy lớp của các khóa học học sinh đang tham gia miễn phí.
        enrolled_rows = list(
            Enrollment.objects.filter(student=student, course__published=True)
            .values_list('course_id', 'course__grade')
        )
        enrolled_courses = [grade for _, grade in enrolled_rows]
        enrolled_course_ids = {course_id for course_id, _ in enrolled_rows}
        
        # Normalize grade: "Lớp 1" -> "1", "1" -> "1"
        def normalize_grade(grade_str):
            if not grade_str:
                return None
            grade_str = str(grade_str).strip()
            # Nếu có "Lớp" hoặc "lớp", extract số
            if 'lớp' in grade_str.lower():
                import re
                match = re.search(r'\d+', grade_str)
                if match:
                    return match.group()
            return grade_str
        
        enrolled_grades = set([normalize_grade(g) for g in enrolled_courses if g])  # Loại bỏ None/empty
        
        # Nếu chưa tham gia khóa học nào, không hiển thị bài kiểm tra nào.
        if not enrolled_course_ids:
            return Response([], status=status.HTTP_200_OK)
        
        # Get all exercises (có thể có lesson hoặc không)
        # Chỉ lấy exercise độc lập (không gắn với lesson) hoặc exercise có lesson
        exercises = Exercise.objects.filter(
            published=True
        ).select_related('lesson__module__course', 'settings')
        
        # Loại bỏ exercise gắn với lesson (chỉ giữ exercise độc lập)
        # Vì exercise gắn với lesson sẽ được làm trong lesson, không phải bài kiểm tra độc lập
        exercises = exercises.filter(lesson__isnull=True)
        
        # Apply search filter
        if q:
            exercises = exercises.filter(title__icontains=q)

        exercises = list(exercises)
        settings_course_ids = {
            getattr(getattr(exercise, 'settings', None), 'course_id', None)
            for exercise in exercises
        }
        settings_course_ids.discard(None)
        settings_course_grades = dict(
            Course.objects.filter(id__in=settings_course_ids).values_list('id', 'grade')
        )
        
        exams_data = []
        for exercise in exercises:
            # Lấy grade từ exercise.grade field hoặc từ lesson nếu có
            exercise_grade = None
            
            # Một số database cũ còn cột grade, nhưng model hiện tại có thể không có.
            # getattr giúp endpoint không 500 trong cả hai trạng thái migration.
            model_grade = getattr(exercise, 'grade', None)
            if model_grade:
                exercise_grade = model_grade

            # Đề độc lập bắt buộc liên kết đúng khóa học học sinh đang tham gia.
            settings_obj = getattr(exercise, 'settings', None)
            settings_course_id = getattr(settings_obj, 'course_id', None) if settings_obj else None
            if not settings_course_id or settings_course_id not in enrolled_course_ids:
                continue
            exercise_grade = settings_course_grades.get(settings_course_id) or exercise_grade or ''
            
            # Normalize exercise grade để so sánh
            normalized_exercise_grade = normalize_grade(exercise_grade)
            
            # Chỉ hiển thị đề có lớp phù hợp với khóa học đã ghi danh.
            if normalized_exercise_grade and normalized_exercise_grade not in enrolled_grades:
                continue
            
            # Get settings if exists
            duration_sec = 1800  # Default 30 minutes
            pass_score = 12  # Default
            
            try:
                if settings_obj:
                    duration_sec = settings_obj.time_limit_seconds or duration_sec
                    pass_score = settings_obj.pass_score or pass_score
            except:
                pass
            
            # Map grade to level format (nếu cần)
            # Grade có thể là "1", "2", "3", "4", "5" hoặc "Lớp 1", "Lớp 2", etc.
            level_display = exercise_grade
            if exercise_grade and exercise_grade.isdigit():
                grade_num = int(exercise_grade)
                if grade_num <= 2:
                    level_display = 'Khối 1–2'
                elif grade_num <= 5:
                    level_display = 'Khối 3–5'
            
            # Filter by level if specified
            if level:
                if level == 'Khối 1–2' and level_display != 'Khối 1–2':
                    continue
                elif level == 'Khối 3–5' and level_display != 'Khối 3–5':
                    continue
            
            questions_count = Question.objects.filter(exercise=exercise).count()
            
            exams_data.append({
                'id': str(exercise.id),
                'title': exercise.title,
                'level': level_display,
                'grade': exercise_grade,  # Thêm grade gốc
                'durationSec': duration_sec,
                'passScore': pass_score,
                'questionsCount': questions_count,
                'status': 'published',
                'updatedAt': None,
            })
        
        return Response(exams_data, status=status.HTTP_200_OK)


class StudentExamDetailView(APIView):
    """
    GET /api/student/exams/{id}/
    Returns exam detail for student
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request, pk):
        """Get exam detail"""
        exercise = _get_available_exam(request.user, pk)
        if exercise is None:
            return Response(
                {'detail': 'Exam not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        exercise_domain = get_exercise(str(pk))
        
        # Lấy cấu hình thật của đề (thời gian, điểm đạt, trộn câu hỏi...) thay vì
        # hằng số mặc định - trước đây đề 15 phút vẫn hiện 30 phút / điểm đạt 12.
        settings_obj = getattr(exercise, 'settings', None)
        duration_sec = getattr(settings_obj, 'time_limit_seconds', None) or 1800
        pass_score = getattr(settings_obj, 'pass_score', None)
        pass_score = pass_score if pass_score is not None else 50.0
        shuffle_questions = bool(getattr(settings_obj, 'shuffle_questions', True))
        shuffle_choices = bool(getattr(settings_obj, 'shuffle_choices', True))

        # Khối lớp suy ra từ khóa học gắn với đề.
        level = ''
        course_id = getattr(settings_obj, 'course_id', None) if settings_obj else None
        if course_id:
            course = Course.objects.filter(id=course_id).only('grade').first()
            digits = re.sub(r'\D', '', str(getattr(course, 'grade', '') or '')) if course else ''
            if digits:
                level = 'Khối 1–2' if int(digits) <= 2 else 'Khối 3–5'

        # Convert domain to response format
        exercise_data = {
            'id': str(exercise_domain.id),
            'title': exercise_domain.title,
            'level': level,
            'durationSec': duration_sec,
            'passScore': pass_score,
            'questionsCount': len(exercise_domain.questions) if hasattr(exercise_domain, 'questions') else 0,
            'status': 'published' if exercise_domain.published else 'draft',
            'updatedAt': None,
            'description': getattr(exercise_domain, 'description', ''),
            'shuffleQuestions': shuffle_questions,
            'shuffleChoices': shuffle_choices,
            'questions': [],
        }

        questions_data = []
        
        for question in exercise.questions.all():
            questions_data.append(_student_question_payload(question))
        
        exercise_data['questions'] = questions_data
        
        return Response(exercise_data, status=status.HTTP_200_OK)


class StudentExamStartView(APIView):
    """
    POST /api/student/exams/{id}/start/
    Starts an exam attempt for student
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def post(self, request, pk):
        """Start exam attempt"""
        exercise = _get_available_exam(request.user, pk)
        if exercise is None:
            return Response(
                {'detail': 'Bạn chưa được phép làm bài kiểm tra này'},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            attempt_domain = start_attempt(str(pk), request.user)
        except NotFoundError:
            return Response(
                {'detail': 'Exam not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValidationError as e:
            detail = str(e)
            payload = {'detail': detail}
            if 'hết số lượt làm bài' in detail.lower():
                payload['code'] = 'attempt_limit_reached'
            return Response(
                payload,
                status=status.HTTP_400_BAD_REQUEST
            )
        except PermissionDenied as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Convert to response format
        attempt_data = {
            'id': str(attempt_domain.id),
            'examId': str(attempt_domain.exercise_id),
            'startedAt': attempt_domain.started_at.isoformat() if hasattr(attempt_domain, 'started_at') else None,
            'deadlineAt': None,  # Calculate from duration
            'questions': [],
            'answers': {},
        }
        
        # Get questions for attempt
        for question in exercise.questions.all():
            attempt_data['questions'].append(_student_question_payload(question))
        
        return Response(attempt_data, status=status.HTTP_201_CREATED)


def _summary_to_result(pk, attempt_id, summary):
    """Map attempt summary (score/questions keys) sang format app mong đợi
    (totalScore/maxScore/correctCount/totalCount/passed/detail)."""
    questions = summary.get('questions', []) or []
    total_score = sum(float(q.get('answer_score') or 0) for q in questions)
    max_score = sum(float(q.get('points') or 0) for q in questions)
    correct_count = sum(1 for q in questions if q.get('correct'))
    total_count = len(questions)
    percent = float(summary.get('score') or 0)
    pass_score = 50.0
    try:
        exercise = Exercise.objects.select_related('settings').get(id=pk)
        pass_score = float(exercise.settings.pass_score)
    except Exception:
        pass
    return {
        'attemptId': str(attempt_id),
        'examId': str(pk),
        'totalScore': total_score,
        'maxScore': max_score,
        'score': percent,
        'correctCount': correct_count,
        'totalCount': total_count,
        'passed': percent >= pass_score,
        'detail': questions,
    }


class StudentExamSubmitView(APIView):
    """
    POST /api/student/exams/{id}/submit/
    Submits exam answers and finalizes attempt
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def post(self, request, pk, attempt_id):
        """Submit exam answers"""
        student = request.user
        exercise = _get_available_exam(student, pk)
        if exercise is None:
            return Response(
                {'detail': 'Bạn chưa được phép làm bài kiểm tra này'},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            attempt = ExerciseAttempt.objects.get(
                id=attempt_id,
                exercise=exercise,
                student=student,
            )
        except ExerciseAttempt.DoesNotExist:
            return Response(
                {'detail': 'Không tìm thấy lượt làm bài'},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        # Submit all answers
        answers = request.data.get('answers', {})
        for question_id, answer in answers.items():
            try:
                submit_answer(
                    attempt_id=str(attempt_id),
                    question_id=str(question_id),
                    answer_payload=answer,
                    actor_user=student,
                )
            except (NotFoundError, ValidationError, PermissionDenied) as e:
                return Response(
                    {'detail': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Finalize attempt
        try:
            summary = finalize_attempt(str(attempt_id), actor_user=student, force=False)
        except (NotFoundError, ValidationError, PermissionDenied) as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Convert summary to response format
        result_data = _summary_to_result(pk, attempt_id, summary)
        return Response(result_data, status=status.HTTP_200_OK)


class StudentExamResultView(APIView):
    """
    GET /api/student/exams/{id}/result/{attempt_id}/
    Returns exam result for student
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request, pk, attempt_id):
        """Get exam result"""
        exercise = _get_available_exam(request.user, pk)
        if exercise is None:
            return Response({'detail': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)
        if not ExerciseAttempt.objects.filter(
            id=attempt_id,
            exercise=exercise,
            student=request.user,
        ).exists():
            return Response({'detail': 'Result not found'}, status=status.HTTP_404_NOT_FOUND)
        try:
            summary = get_attempt_summary(str(attempt_id))
        except NotFoundError:
            return Response(
                {'detail': 'Attempt not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Convert to response format
        result_data = _summary_to_result(pk, attempt_id, summary)
        return Response(result_data, status=status.HTTP_200_OK)


class StudentExamRankingView(APIView):
    """
    GET /api/student/exams/{id}/ranking/
    Returns ranking for exam
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request, pk):
        """Get exam ranking"""
        student = request.user
        exercise = _get_available_exam(student, pk)
        if exercise is None:
            return Response({'detail': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)

        attempts = list(ExerciseAttempt.objects.filter(
            exercise_id=pk,
            finished_at__isnull=False
        ).select_related('student').prefetch_related('answers'))

        def duration_seconds(attempt):
            if not attempt.finished_at or not attempt.started_at:
                return 0
            return max(0, int((attempt.finished_at - attempt.started_at).total_seconds()))

        attempts.sort(key=lambda attempt: (
            -float(attempt.score or 0),
            duration_seconds(attempt),
            attempt.finished_at,
        ))
        best_by_student = {}
        for attempt in attempts:
            key = attempt.student_id or str(attempt.id)
            if key not in best_by_student:
                best_by_student[key] = attempt

        total_questions = exercise.questions.count()
        ranked_attempts = list(best_by_student.values())
        top = []
        me = None
        for index, attempt in enumerate(ranked_attempts):
            rank = index + 1
            seconds = duration_seconds(attempt)
            correct_count = sum(1 for answer in attempt.answers.all() if answer.correct)
            attempt_student = attempt.student
            name = 'Học viên'
            if attempt_student:
                name = attempt_student.get_full_name() or attempt_student.username
            row = {
                'id': rank,
                'rank': rank,
                'name': name,
                'score': float(attempt.score or 0),
                'correct': correct_count,
                'total': total_questions,
                'time': f"{seconds // 60:02d}:{seconds % 60:02d}",
                'isMe': attempt.student_id == student.id,
            }
            if rank <= 100:
                top.append(row)
            if row['isMe']:
                me = dict(row)

        return Response({
            'top': top,
            'me': me,
            'participants': len(ranked_attempts),
        }, status=status.HTTP_200_OK)


class StudentCertificatesView(APIView):
    """
    GET /api/student/exams/certificates/
    Returns certificates for student
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request):
        """Get student certificates"""
        student = request.user
        
        # Get completed attempts with passing scores
        attempts = ExerciseAttempt.objects.filter(
            student=student,
            finished_at__isnull=False,
            score__gte=50  # Passing score threshold
        ).select_related('exercise').order_by('-finished_at')
        
        certificates = []
        for attempt in attempts:
            certificates.append({
                'id': str(attempt.id),
                'title': f'Chứng chỉ {attempt.exercise.title}',
                'score': float(attempt.score) if attempt.score else 0,
                'total': 100,  # Default
                'issuedAt': attempt.finished_at.isoformat() if attempt.finished_at else None,
                'thumbnail': None,
                'image': None,
                'pdf': None,
            })
        
        return Response(certificates, status=status.HTTP_200_OK)
