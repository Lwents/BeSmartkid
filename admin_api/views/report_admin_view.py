from datetime import datetime, timedelta
from decimal import Decimal
from django.db.models import Sum, Count, Avg, Q
from django.utils import timezone
from django.db.models import F
from django.http import HttpResponse
import csv
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from admin_api.permissions import IsAdmin
from payments.models import Payment
from content.models import Course, Enrollment, LessonProgress, Subject
from activities.models import TeacherFeedback
from custom_account.models import UserModel
from progress.models import UserProgress, UserLessonProgress
from ai_personalization.models import LearningEvent


class AdminRevenueReportView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """Get revenue reports"""
        report_type = request.query_params.get('type', 'timeseries')  # timeseries, by-gateway, top-courses
        from_date = request.query_params.get('from')
        to_date = request.query_params.get('to')
        granularity = request.query_params.get('granularity', 'day')  # day, week, month

        # Dùng local date để đồng bộ với created_at/paid_at (lưu theo timezone)
        local_today = timezone.localdate()
        if not from_date:
            from_date = local_today - timedelta(days=30)
        else:
            from_date = datetime.fromisoformat(from_date).date()

        if not to_date:
            to_date = local_today
        else:
            to_date = datetime.fromisoformat(to_date).date()

        if report_type == 'timeseries':
            return self._get_timeseries(from_date, to_date, granularity)
        elif report_type == 'by-gateway':
            return self._get_by_gateway(from_date, to_date)
        elif report_type == 'top-courses':
            return self._get_top_courses(from_date, to_date)
        else:
            return Response({'error': 'Invalid report type'}, status=status.HTTP_400_BAD_REQUEST)

    def _get_timeseries(self, from_date, to_date, granularity):
        """Get revenue time series"""
        current = from_date
        points = []

        while current <= to_date:
            next_date = current + timedelta(days=1)
            if granularity == 'week':
                next_date = current + timedelta(days=7)
            elif granularity == 'month':
                next_date = (current.replace(day=28) + timedelta(days=4)).replace(day=1)

            period_payments = Payment.objects.filter(
                created_at__date__gte=current,
                created_at__date__lt=next_date,
            )

            gross = period_payments.filter(status__in=['paid', 'refunded']).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            refunds = period_payments.filter(status='refunded').aggregate(total=Sum('amount'))['total'] or Decimal('0')
            # Chưa lưu phí thực tế của cổng thanh toán, nên không tự giả định 3%.
            net = gross - refunds

            points.append({
                'date': current.isoformat(),
                'gross': float(gross),
                'net': float(net),
                'refunds': float(refunds)
            })

            current = next_date

        return Response(points, status=status.HTTP_200_OK)

    def _get_by_gateway(self, from_date, to_date):
        """Get revenue by gateway"""
        payments = Payment.objects.filter(
            created_at__date__gte=from_date,
            created_at__date__lte=to_date,
            status='paid'
        )

        gateways = {}
        for payment in payments:
            gateway = payment.metadata.get('gateway', 'Unknown') if payment.metadata else 'Unknown'
            if gateway not in gateways:
                gateways[gateway] = 0
            gateways[gateway] += float(payment.amount)

        result = [{'gateway': k, 'amount': v} for k, v in gateways.items()]
        return Response(result, status=status.HTTP_200_OK)

    def _get_top_courses(self, from_date, to_date):
        """
        Get top courses by number of orders (ưu tiên số đơn, sau đó gross).
        Nếu payment không gắn plan → nhóm vào 'Thanh toán tuỳ chỉnh'.
        """
        payments = (
            Payment.objects.filter(
                created_at__date__gte=from_date,
                created_at__date__lte=to_date,
                status='paid',
            )
            .select_related('plan')
        )

        course_revenue = {}

        for payment in payments:
            if payment.plan:
                course_id = str(payment.plan.id)
                title = payment.plan.name
                teacher = getattr(getattr(payment.plan, 'teacher', None), 'name', 'N/A')
            else:
                meta = payment.metadata or {}
                course_ids = meta.get('course_ids') or []
                titles = meta.get('course_titles') or meta.get('title') or []
                if isinstance(titles, str):
                    titles = [titles] * max(1, len(course_ids) or 1)
                # Nếu FE chưa gửi title, cố gắng lấy từ DB theo id và lấy luôn tên GV (owner)
                course_meta_map = {}
                if course_ids:
                    try:
                        courses_qs = Course.objects.filter(id__in=course_ids).select_related('owner', 'owner__profile')
                        for c in courses_qs:
                            teacher_name = (
                                getattr(getattr(c.owner, "profile", None), "display_name", None)
                                or getattr(c.owner, "username", None)
                                or getattr(c.owner, "email", None)
                                or "N/A"
                            )
                            course_meta_map[str(c.id)] = {
                                "title": c.title,
                                "teacher": teacher_name,
                            }
                        if not titles or len(titles) < len(course_ids):
                            titles = [
                                course_meta_map.get(str(cid), {}).get("title", titles[0] if titles else "Thanh toán tuỳ chỉnh")
                                for cid in course_ids
                            ]
                    except Exception:
                        pass
                # Fallback suy đoán course theo giá/enrollment nếu không có metadata
                if not course_ids:
                    try:
                        inferred = list(Course.objects.filter(price=payment.amount).values('id', 'title'))
                        # ưu tiên course mà user vừa enroll trong vòng 1 giờ quanh thời điểm tạo payment
                        if inferred:
                            course_id_set = [c['id'] for c in inferred]
                            recent_enrolls = set(
                                Enrollment.objects.filter(
                                    student_id=payment.user_id,
                                    course_id__in=course_id_set,
                                    enrolled_at__gte=payment.created_at - timedelta(hours=1),
                                    enrolled_at__lte=payment.created_at + timedelta(hours=1),
                                ).values_list('course_id', flat=True)
                            )
                            if recent_enrolls:
                                inferred = [c for c in inferred if c['id'] in recent_enrolls]
                        if len(inferred) == 1:
                            course_ids = [str(inferred[0]['id'])]
                            titles = [inferred[0]['title']]
                            # lấy teacher cho khóa suy đoán
                            course_meta_map[str(inferred[0]['id'])] = {
                                "title": inferred[0]['title'],
                                "teacher": None,  # sẽ fill bên dưới
                            }
                    except Exception:
                        pass

                # Nếu có course_ids nhưng chưa có teacher_map, cố gắng lấy owner để điền teacher
                if course_ids and not course_meta_map:
                    try:
                        courses_qs = Course.objects.filter(id__in=course_ids).select_related('owner', 'owner__profile')
                        for c in courses_qs:
                            teacher_name = (
                                getattr(getattr(c.owner, "profile", None), "display_name", None)
                                or getattr(c.owner, "username", None)
                                or getattr(c.owner, "email", None)
                                or "N/A"
                            )
                            course_meta_map[str(c.id)] = {
                                "title": course_meta_map.get(str(c.id), {}).get("title", c.title),
                                "teacher": teacher_name,
                            }
                    except Exception:
                        pass

                if course_ids:
                    share = float(payment.amount) / max(1, len(course_ids))
                    for idx, cid in enumerate(course_ids):
                        name = titles[idx] if idx < len(titles) else titles[0] if titles else "Thanh toán tuỳ chỉnh"
                        course_id = str(cid)
                        teacher = course_meta_map.get(course_id, {}).get("teacher") or "N/A"
                        if course_id not in course_revenue:
                            course_revenue[course_id] = {
                                'courseId': course_id,
                                'title': name,
                                'teacher': teacher,
                                'gross': 0,
                                'net': 0,
                                'orders': 0,
                            }
                        course_revenue[course_id]['gross'] += share
                        course_revenue[course_id]['orders'] += 1
                    continue
                else:
                    course_id = 'custom'
                    title = (
                        meta.get('title')
                        if isinstance(meta, dict)
                        else None
                    ) or "Thanh toán tuỳ chỉnh"
                    teacher = 'N/A'

            if course_id not in course_revenue:
                course_revenue[course_id] = {
                    'courseId': course_id,
                    'title': title,
                    'teacher': teacher,
                    'gross': 0,
                    'net': 0,
                    'orders': 0,
                }

            course_revenue[course_id]['gross'] += float(payment.amount)
            course_revenue[course_id]['orders'] += 1

        # Payment hiện chưa lưu gateway fee thực tế; không dựng phí 3% giả.
        for data in course_revenue.values():
            data['net'] = data['gross']

        # Sort by orders desc, then gross desc
        result = sorted(
            course_revenue.values(),
            key=lambda x: (x['orders'], x['gross']),
            reverse=True,
        )[:10]
        return Response(result, status=status.HTTP_200_OK)


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
            all_progress = UserProgress.objects.all()
            if all_progress.exists():
                avg_completion = all_progress.aggregate(avg=Avg('progress_percentage'))['avg'] or 0
            else:
                avg_completion = 0
            
            # Calculate average exercise score
            all_lesson_progress = LessonProgress.objects.filter(exercise_score__isnull=False)
            if all_lesson_progress.exists():
                avg_score = all_lesson_progress.aggregate(avg=Avg('exercise_score'))['avg'] or 0
            else:
                avg_score = 0
            
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
