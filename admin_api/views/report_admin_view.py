from datetime import datetime, timedelta
from django.db.models import Count, Avg
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from admin_api.permissions import IsAdmin
from content.models import Course, Enrollment, LessonProgress, Subject
from activities.models import TeacherFeedback, ExerciseAttempt
from custom_account.models import UserModel
from progress.models import UserProgress, UserLessonProgress
from ai_personalization.models import LearningEvent


class AdminUserReportView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """Get user analytics reports"""
        report_type = request.query_params.get('type', 'kpis')  # kpis, timeseries, by-role
        from_date = request.query_params.get('from')
        to_date = request.query_params.get('to')

        if report_type == 'kpis':
            return self._get_user_kpis(from_date, to_date)
        elif report_type == 'timeseries':
            return self._get_user_timeseries(from_date, to_date)
        elif report_type == 'by-role':
            return self._get_user_by_role()
        else:
            return Response({'error': 'Invalid report type'}, status=status.HTTP_400_BAD_REQUEST)

    def _get_user_kpis(self, from_date, to_date):
        """Get user KPIs"""
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        dau = UserModel.objects.filter(last_login__gte=today_start).count()
        mau = UserModel.objects.filter(last_login__gte=now - timedelta(days=30)).count()

        if from_date:
            from_date = datetime.fromisoformat(from_date).date()
            new_users = UserModel.objects.filter(created_on__date__gte=from_date).count()
        else:
            new_users = UserModel.objects.filter(created_on__gte=now - timedelta(days=7)).count()

        active_users = UserModel.objects.filter(last_login__gte=now - timedelta(days=7)).count()

        return Response({
            'dau': dau,
            'mau': mau,
            'newUsers': new_users,
            'activeUsers': active_users
        }, status=status.HTTP_200_OK)

    def _get_user_timeseries(self, from_date, to_date):
        """Get user time series"""
        if not from_date:
            from_date = (timezone.now() - timedelta(days=30)).date()
        else:
            from_date = datetime.fromisoformat(from_date).date()

        if not to_date:
            to_date = timezone.now().date()
        else:
            to_date = datetime.fromisoformat(to_date).date()

        current = from_date
        points = []

        while current <= to_date:
            next_date = current + timedelta(days=1)
            day_start = timezone.make_aware(datetime.combine(current, datetime.min.time()))
            day_end = timezone.make_aware(datetime.combine(next_date, datetime.min.time()))

            dau = UserModel.objects.filter(
                last_login__gte=day_start,
                last_login__lt=day_end
            ).count()

            new_users = UserModel.objects.filter(
                created_on__gte=day_start,
                created_on__lt=day_end
            ).count()

            points.append({
                'date': current.isoformat(),
                'dau': dau,
                'newUsers': new_users
            })

            current = next_date

        return Response(points, status=status.HTTP_200_OK)

    def _get_user_by_role(self):
        """Get user count by role"""
        roles = UserModel.objects.values('role').annotate(count=Count('id'))
        result = [{'role': r['role'], 'count': r['count']} for r in roles]
        return Response(result, status=status.HTTP_200_OK)


class AdminLearningReportView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """Get learning analytics reports"""
        report_type = request.query_params.get('type', 'kpis')  # kpis, completion, score-by-subject, at-risk
        from_date = request.query_params.get('from')
        to_date = request.query_params.get('to')

        if report_type == 'kpis':
            # Calculate average completion percentage
            # Ưu tiên UserProgress; nếu trống thì tính từ LessonProgress.completed
            # (dữ liệu thật mà app ghi khi học sinh hoàn thành bài học)
            all_progress = UserProgress.objects.all()
            if all_progress.exists():
                avg_completion = all_progress.aggregate(avg=Avg('progress_percentage'))['avg'] or 0
            else:
                total_lesson_progress = LessonProgress.objects.count()
                if total_lesson_progress:
                    completed_count = LessonProgress.objects.filter(completed=True).count()
                    avg_completion = completed_count * 100.0 / total_lesson_progress
                else:
                    avg_completion = 0

            # Calculate average exercise score
            # Ưu tiên LessonProgress.exercise_score; nếu trống thì lấy điểm thật
            # từ các lượt làm bài (ExerciseAttempt.score, thang 100)
            all_lesson_progress = LessonProgress.objects.filter(exercise_score__isnull=False)
            if all_lesson_progress.exists():
                avg_score = all_lesson_progress.aggregate(avg=Avg('exercise_score'))['avg'] or 0
            else:
                avg_score = ExerciseAttempt.objects.filter(
                    score__isnull=False
                ).aggregate(avg=Avg('score'))['avg'] or 0

            # Calculate average time spent from LearningEvent
            # Get all learning events with time_spent in detail
            avg_time_spent = 0
            try:
                # Get unique users who have learning events
                unique_users = LearningEvent.objects.values('user').distinct().count()

                if unique_users > 0:
                    # Sum all time_spent from events (more efficient)
                    total_time = 0
                    for event in LearningEvent.objects.only('detail').iterator():
                        if event.detail and isinstance(event.detail, dict):
                            total_time += event.detail.get('time_spent', 0)

                    # Convert seconds to minutes and calculate average per user
                    if total_time > 0:
                        avg_time_spent = round(total_time / unique_users / 60, 0)
                if not avg_time_spent:
                    # Fallback: thời gian làm bài (time_taken, giây) ghi trong attempt
                    total_time = 0
                    users = set()
                    for attempt in ExerciseAttempt.objects.only('metadata', 'student').iterator():
                        meta = attempt.metadata or {}
                        seconds = meta.get('time_taken', 0) if isinstance(meta, dict) else 0
                        if seconds:
                            total_time += seconds
                            users.add(attempt.student_id)
                    if total_time and users:
                        avg_time_spent = round(total_time / len(users) / 60, 1)
            except Exception:
                avg_time_spent = 0
            
            return Response({
                'avgCompletion': round(float(avg_completion), 2),
                'avgScore': round(float(avg_score), 2),
                'avgTimeSpentMin': int(avg_time_spent)
            }, status=status.HTTP_200_OK)
        elif report_type == 'completion':
            # Get completion rates by date (time series)
            from_date = request.query_params.get('from')
            to_date = request.query_params.get('to')
            
            if not from_date:
                from_date = (timezone.now() - timedelta(days=30)).date()
            else:
                from_date = datetime.strptime(from_date, '%Y-%m-%d').date()
            
            if not to_date:
                to_date = timezone.now().date()
            else:
                to_date = datetime.strptime(to_date, '%Y-%m-%d').date()
            
            completion_data = []
            current_date = from_date
            while current_date <= to_date:
                # Get average completion for this date
                progress_records = UserProgress.objects.filter(
                    updated_at__date=current_date
                )
                if progress_records.exists():
                    avg_completion = progress_records.aggregate(avg=Avg('progress_percentage'))['avg'] or 0
                else:
                    # If no data for this date, use overall average
                    all_progress = UserProgress.objects.all()
                    avg_completion = all_progress.aggregate(avg=Avg('progress_percentage'))['avg'] or 0
                
                completion_data.append({
                    'date': current_date.strftime('%Y-%m-%d'),
                    'completion': round(float(avg_completion), 2)
                })
                current_date += timedelta(days=1)
            
            return Response(completion_data, status=status.HTTP_200_OK)
        elif report_type == 'score-by-subject':
            # Get scores by subject
            subject_map = {
                'math': 'Toán',
                'vietnamese': 'Tiếng Việt',
                'english': 'Tiếng Anh',
                'science': 'Khoa học',
                'history': 'Lịch sử'
            }
            
            subjects = {}
            lesson_progresses = LessonProgress.objects.filter(exercise_score__isnull=False).select_related('lesson__module__course__subject')
            for lp in lesson_progresses:
                if lp.lesson and lp.lesson.module and lp.lesson.module.course and lp.lesson.module.course.subject:
                    subject_slug = lp.lesson.module.course.subject.slug
                    if subject_slug not in subjects:
                        subjects[subject_slug] = {'scores': [], 'count': 0}
                    subjects[subject_slug]['scores'].append(float(lp.exercise_score))
                    subjects[subject_slug]['count'] += 1
            
            result = []
            for subject_slug, data in subjects.items():
                avg_score = sum(data['scores']) / len(data['scores']) if data['scores'] else 0
                subject_name = subject_map.get(subject_slug, subject_slug)
                result.append({
                    'subject': subject_name,
                    'avgScore': round(avg_score, 2)
                })
            return Response(result, status=status.HTTP_200_OK)
        elif report_type == 'at-risk':
            # Find students with low completion rates
            at_risk_progress = UserProgress.objects.filter(progress_percentage__lt=30).select_related('user', 'user__profile', 'course')
            result = []
            for progress in at_risk_progress[:50]:  # Limit to 50
                # Get student name from profile or email
                student_name = progress.user.email
                if hasattr(progress.user, 'profile') and progress.user.profile and progress.user.profile.display_name:
                    student_name = progress.user.profile.display_name
                elif progress.user.username:
                    student_name = progress.user.username
                
                # Get class/grade from course
                class_name = progress.course.grade or 'N/A'
                
                result.append({
                    'userId': str(progress.user.id),
                    'name': student_name,
                    'className': class_name,
                    'progress': round(float(progress.progress_percentage), 2),
                    'lastActiveAt': progress.updated_at.isoformat() if progress.updated_at else None
                })
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'Invalid report type'}, status=status.HTTP_400_BAD_REQUEST)


class AdminContentReportView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """Get content analytics reports"""
        report_type = request.query_params.get('type', 'kpis')  # kpis, views-by-subject, top
        from_date = request.query_params.get('from')
        to_date = request.query_params.get('to')

        if report_type == 'kpis':
            total_published = Course.objects.filter(published=True).count()
            total_enrollments = Enrollment.objects.count()
            avg_rating = (
                TeacherFeedback.objects.filter(course__published=True).aggregate(avg=Avg('rating'))['avg']
                or 0
            )
            return Response({
                'totalPublished': total_published,
                'totalEnrollments': total_enrollments,
                'avgRating': round(float(avg_rating), 1)
            }, status=status.HTTP_200_OK)
        elif report_type == 'views-by-subject':
            # Gộp views theo môn học (subject) giống e-learning
            subject_map = {
                'math': 'Toán',
                'vietnamese': 'Tiếng Việt',
                'english': 'Tiếng Anh',
                'science': 'Khoa học',
                'history': 'Lịch sử'
            }

            # Group by subject and sum enrollments
            from django.db.models import Sum
            subject_stats = (
                Course.objects.filter(published=True)
                .values('subject__slug', 'subject__title')
                .annotate(total_views=Count('enrollments', distinct=True))
                .order_by('-total_views')
            )
            
            result = []
            for stat in subject_stats:
                subject_slug = stat.get('subject__slug')
                subject_title = stat.get('subject__title')
                label = subject_map.get(subject_slug, subject_title or 'Khác')
                result.append({'subject': label, 'views': stat['total_views'] or 0})

            return Response(result, status=status.HTTP_200_OK)
        elif report_type == 'top':
            # Get top courses by enrollments (only published), views = real enrollments, rating = avg feedback
            top_courses = Course.objects.filter(published=True).annotate(
                enrollments_count=Count('enrollments', distinct=True),
                avg_rating=Avg('feedbacks__rating'),
            ).order_by('-enrollments_count')[:10]
            
            result = []
            for course in top_courses:
                views = course.enrollments_count  # Use actual enrollments as views
                rating = course.avg_rating or 0.0
                
                result.append({
                    'courseId': str(course.id),
                    'title': course.title,
                    'views': views,
                    'enrollments': course.enrollments_count,
                    'rating': round(float(rating), 1)
                })
            return Response(result, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'Invalid report type'}, status=status.HTTP_400_BAD_REQUEST)
