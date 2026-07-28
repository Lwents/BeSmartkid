from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from activities.models import Notification
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q

from admin_api.permissions import IsAdmin
from admin_api.pagination import page_link, positive_int_query
from admin_api.services import record_admin_action


TEACHER_QA_CATEGORIES = ("lesson_question", "lesson_question_reply")


def admin_notifications_for(user):
    return Notification.objects.filter(user=user).exclude(
        category__in=TEACHER_QA_CATEGORIES
    )


class AdminNotificationsView(APIView):
    """
    GET /api/admin/notifications/
    Returns notifications for admin user
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request):
        """Get admin's notifications"""
        page = positive_int_query(request, 'page', 1)
        page_size = positive_int_query(
            request, 'pageSize', 50, aliases=('page_size', 'limit'), maximum=100
        )
        category = request.query_params.get('category')
        is_read = request.query_params.get('is_read')
        
        # Build query
        queryset = admin_notifications_for(request.user)
        
        if category:
            queryset = queryset.filter(category=category)
        
        if is_read is not None:
            is_read_bool = is_read.lower() in ('true', '1', 'yes')
            queryset = queryset.filter(is_read=is_read_bool)
        
        # Order by created_at descending
        queryset = queryset.order_by('-created_at')
        paginator = Paginator(queryset, page_size)
        if page > max(paginator.num_pages, 1):
            return Response(
                {'page': 'Trang yêu cầu vượt quá số trang hiện có.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        page_obj = paginator.page(page)
        
        # Serialize notifications
        notifications_data = []
        for notif in page_obj:
            notifications_data.append({
                'id': str(notif.id),
                'title': notif.title,
                'message': notif.message,
                'type': notif.type,
                'category': notif.category,
                'is_read': notif.is_read,
                'created_at': notif.created_at.isoformat(),
                'metadata': notif.metadata or {},
            })
        
        return Response({
            'notifications': notifications_data,
            'results': notifications_data,
            'total': paginator.count,
            'count': paginator.count,
            'page': page,
            'page_size': page_size,
            'total_pages': paginator.num_pages,
            'next': page_link(request, page + 1) if page_obj.has_next() else None,
            'previous': page_link(request, page - 1) if page_obj.has_previous() else None,
            'unread_count': admin_notifications_for(request.user).filter(is_read=False).count(),
        }, status=status.HTTP_200_OK)

    def post(self, request):
        title = str(request.data.get('title') or '').strip()
        message = str(request.data.get('message') or '').strip()
        audience = str(request.data.get('audience') or 'all').strip().lower()
        notification_type = str(request.data.get('type') or 'info').strip().lower()

        errors = {}
        if not title:
            errors['title'] = 'Vui lòng nhập tiêu đề thông báo.'
        elif len(title) > 255:
            errors['title'] = 'Tiêu đề không được vượt quá 255 ký tự.'
        if not message:
            errors['message'] = 'Vui lòng nhập nội dung thông báo.'
        elif len(message) > 3000:
            errors['message'] = 'Nội dung không được vượt quá 3000 ký tự.'
        if audience not in {'student', 'instructor', 'all'}:
            errors['audience'] = 'Nhóm nhận thông báo không hợp lệ.'
        if notification_type not in {'info', 'success', 'warning', 'error'}:
            errors['type'] = 'Mức thông báo không hợp lệ.'
        if errors:
            return Response({'detail': 'Thông báo chưa hợp lệ.', 'errors': errors},
                            status=status.HTTP_400_BAD_REQUEST)

        User = get_user_model()
        recipients = User.objects.filter(is_active=True).exclude(pk=request.user.pk)
        if audience == 'student':
            recipients = recipients.filter(role='student')
        elif audience == 'instructor':
            recipients = recipients.filter(Q(role='instructor') | Q(role='teacher'))
        else:
            recipients = recipients.filter(
                Q(role='student') | Q(role='instructor') | Q(role='teacher')
            )

        created_count = 0
        pending = []
        for user_id in recipients.values_list('id', flat=True).iterator(chunk_size=1000):
            pending.append(Notification(
                user_id=user_id,
                title=title,
                message=message,
                type=notification_type,
                category='admin_broadcast',
                metadata={
                    'audience': audience,
                    'sent_by': str(request.user.id),
                },
            ))
            if len(pending) >= 500:
                Notification.objects.bulk_create(pending, batch_size=500)
                created_count += len(pending)
                pending.clear()
        if pending:
            Notification.objects.bulk_create(pending, batch_size=500)
            created_count += len(pending)
        record_admin_action(
            request=request,
            action='notification.broadcast',
            target_type='notification',
            details={'audience': audience, 'recipientCount': created_count, 'title': title},
        )
        return Response({
            'detail': f'Đã gửi thông báo tới {created_count} người dùng.',
            'created_count': created_count,
        }, status=status.HTTP_201_CREATED)


class AdminNotificationReadView(APIView):
    """
    PATCH /api/admin/notifications/<id>/read/
    Mark a notification as read
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def patch(self, request, id):
        """Mark notification as read"""
        try:
            notification = admin_notifications_for(request.user).get(id=id)
            notification.is_read = True
            notification.save(update_fields=['is_read'])
            
            return Response({
                'id': str(notification.id),
                'is_read': True,
            }, status=status.HTTP_200_OK)
        except Notification.DoesNotExist:
            return Response({"detail": "Notification not found"}, status=status.HTTP_404_NOT_FOUND)


class AdminNotificationReadAllView(APIView):
    """
    PATCH /api/admin/notifications/read-all/
    Mark all notifications as read
    """
    permission_classes = [IsAuthenticated, IsAdmin]

    def patch(self, request):
        """Mark all notifications as read"""
        updated = admin_notifications_for(request.user).filter(is_read=False).update(is_read=True)
        
        return Response({
            'updated_count': updated,
        }, status=status.HTTP_200_OK)
