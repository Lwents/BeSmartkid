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
    exercise_stats,
)
from activities.services import NotFoundError, ValidationError, PermissionDenied
from content.models import Enrollment, Course


class StudentExamsListView(APIView):
    """
    GET /api/student/exams/
    Returns list of available exams (exercises) for student
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request):
        """Get list of exams - chỉ hiển thị cho học sinh đã mua khóa học cùng lớp"""
        student = request.user
        
        # Get query parameters
        level = request.query_params.get('level', '').strip()  # 'Khối 1–2' or 'Khối 3–5'
        q = request.query_params.get('q', '').strip()
        
        # Lấy danh sách grade của các khóa học đã mua
        enrolled_rows = list(
            Enrollment.objects.filter(student=student)
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
        
        # Nếu chưa mua khóa học nào, không hiển thị bài kiểm tra nào
        if not enrolled_grades:
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

            # Đề độc lập liên kết khóa học qua ExerciseSettings.course_id.
            settings_obj = getattr(exercise, 'settings', None)
            settings_course_id = getattr(settings_obj, 'course_id', None) if settings_obj else None
            if settings_course_id:
                if settings_course_id not in enrolled_course_ids:
                    continue
                exercise_grade = settings_course_grades.get(settings_course_id) or exercise_grade
            
            # Ưu tiên 2: Nếu exercise có lesson, lấy grade từ course
            elif exercise.lesson and exercise.lesson.module and exercise.lesson.module.course:
                exercise_grade = exercise.lesson.module.course.grade
            
            # Nếu không có grade, bỏ qua (chỉ hiển thị cho người đã mua khóa học)
            if not exercise_grade:
                continue
            
            # Normalize exercise grade để so sánh
            normalized_exercise_grade = normalize_grade(exercise_grade)
            
            # Chỉ hiển thị exercise có grade match với grade của course đã mua
            if normalized_exercise_grade not in enrolled_grades:
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
            if exercise_grade.isdigit():
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
        try:
            exercise_domain = get_exercise(str(pk))
        except NotFoundError:
            return Response(
                {'detail': 'Exam not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Convert domain to response format
        exercise_data = {
            'id': str(exercise_domain.id),
            'title': exercise_domain.title,
            'level': 'Khối 1–2',  # Default, should be in domain
            'durationSec': 1800,  # Default
            'passScore': 12,  # Default
            'questionsCount': len(exercise_domain.questions) if hasattr(exercise_domain, 'questions') else 0,
            'status': 'published' if exercise_domain.published else 'draft',
            'updatedAt': None,
            'description': getattr(exercise_domain, 'description', ''),
            'shuffleQuestions': True,  # Default
            'shuffleChoices': True,  # Default
            'questions': [],
        }
        
        # Get questions with choices
        exercise = Exercise.objects.prefetch_related('questions__choices').get(id=pk)
        questions_data = []
        
        for question in exercise.questions.all():
            question_data = {
                'id': str(question.id),
                'type': 'single',  # Default, should be determined from question
                'text': question.prompt,
                'score': 1,  # Default
                'choices': [],
            }
            
            # Get choices
            choices = question.choices.all()
            for choice in choices:
                question_data['choices'].append({
                    'id': str(choice.id),
                    'text': choice.text,
                })

            # Không gửi đáp án đúng trước khi học sinh nộp bài.
            questions_data.append(question_data)
        
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
        try:
            attempt_domain = start_attempt(str(pk), request.user)
        except NotFoundError:
            return Response(
                {'detail': 'Exam not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except ValidationError as e:
            return Response(
                {'detail': str(e)},
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
        exercise = Exercise.objects.prefetch_related('questions__choices').get(id=pk)
        for question in exercise.questions.all():
            question_data = {
                'id': str(question.id),
                'type': 'single',  # Default
                'text': question.prompt,
                'score': 1,
                'choices': [],
            }
            
            choices = question.choices.all()
            for choice in choices:
                question_data['choices'].append({
                    'id': str(choice.id),
                    'text': choice.text,
                })
            
            attempt_data['questions'].append(question_data)
        
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
        
        try:
            stats = exercise_stats(str(pk))
        except NotFoundError:
            return Response(
                {'detail': 'Exam not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get all students who have completed the exam (top 100)
        top_attempts = ExerciseAttempt.objects.filter(
            exercise_id=pk,
            finished_at__isnull=False
        ).select_related('student').order_by('-score', 'finished_at')[:100]
        
        # Get exercise to get total questions
        from activities.models import Exercise, ExerciseAnswer
        try:
            exercise = Exercise.objects.get(id=pk)
            total_questions = exercise.questions.count()
        except Exercise.DoesNotExist:
            total_questions = 0
        
        top = []
        for idx, attempt in enumerate(top_attempts):
            # Calculate correct answers
            correct_count = ExerciseAnswer.objects.filter(
                attempt=attempt,
                correct=True
            ).count() if hasattr(attempt, 'answers') else 0
            
            # Calculate time taken
            time_taken = '00:00'
            if attempt.finished_at and attempt.started_at:
                from datetime import timedelta
                duration = attempt.finished_at - attempt.started_at
                total_seconds = int(duration.total_seconds())
                minutes = total_seconds // 60
                seconds = total_seconds % 60
                time_taken = f"{minutes:02d}:{seconds:02d}"
            
            # Get avatar from student profile
            avatar = None
            if attempt.student:
                try:
                    profile = getattr(attempt.student, 'profile', None)
                    if profile:
                        avatar = getattr(profile, 'avatar_url', None) or getattr(attempt.student, 'avatar', None)
                except:
                    pass
            
            top.append({
                'id': idx + 1,
                'name': attempt.student.get_full_name() or attempt.student.username if attempt.student else 'Unknown',
                'avatar': avatar,
                'gender': getattr(attempt.student, 'gender', None) if attempt.student else None,
                'score': float(attempt.score) if attempt.score else 0,
                'correct': correct_count,
                'total': total_questions,
                'time': time_taken,
            })
        
        # Get student's rank
        student_attempts = ExerciseAttempt.objects.filter(
            exercise_id=pk,
            student=student,
            finished_at__isnull=False
        ).order_by('-score')
        
        me = None
        if student_attempts.exists():
            best_attempt = student_attempts.first()
            # Calculate rank (simplified)
            rank = ExerciseAttempt.objects.filter(
                exercise_id=pk,
                finished_at__isnull=False,
                score__gt=best_attempt.score if best_attempt.score else 0
            ).count() + 1
            
            # Calculate correct answers for student
            correct_count = ExerciseAnswer.objects.filter(
                attempt=best_attempt,
                correct=True
            ).count() if hasattr(best_attempt, 'answers') else 0
            
            # Calculate time taken
            time_taken = '00:00'
            if best_attempt.finished_at and best_attempt.started_at:
                from datetime import timedelta
                duration = best_attempt.finished_at - best_attempt.started_at
                total_seconds = int(duration.total_seconds())
                minutes = total_seconds // 60
                seconds = total_seconds % 60
                time_taken = f"{minutes:02d}:{seconds:02d}"
            
            # Get avatar
            avatar = None
            if best_attempt.student:
                try:
                    profile = getattr(best_attempt.student, 'profile', None)
                    if profile:
                        avatar = getattr(profile, 'avatar_url', None) or getattr(best_attempt.student, 'avatar', None)
                except:
                    pass
            
            me = {
                'rank': rank,
                'score': float(best_attempt.score) if best_attempt.score else 0,
                'correct': correct_count,
                'total': total_questions,
                'time': time_taken,
                'avatar': avatar,
                'gender': getattr(best_attempt.student, 'gender', None) if best_attempt.student else None,
            }
        
        return Response({
            'top': top,
            'me': me,
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
