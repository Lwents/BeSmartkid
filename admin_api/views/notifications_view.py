from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from activities.models import Notification
from django.contrib.auth import get_user_model


class AdminNotificationsView(APIView):
    """
    GET /api/admin/notifications/
    Returns notifications for admin user
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Get admin's notifications"""
        if not request.user.is_staff:
            return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        
        # Get query parameters
        limit = int(request.query_params.get('limit', 50))
        category = request.query_params.get('category')
        is_read = request.query_params.get('is_read')
        
        # Build query
        queryset = Notification.objects.filter(user=request.user)
        
        if category:
            queryset = queryset.filter(category=category)
        
        if is_read is not None:
            is_read_bool = is_read.lower() in ('true', '1', 'yes')
            queryset = queryset.filter(is_read=is_read_bool)
        
        # Order by created_at descending
        notifications = queryset.order_by('-created_at')[:limit]
        
        # Serialize notifications
        notifications_data = []
        for notif in notifications:
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
            'total': len(notifications_data),
            'unread_count': Notification.objects.filter(user=request.user, is_read=False).count(),
        }, status=status.HTTP_200_OK)


class AdminNotificationReadView(APIView):
    """
    PATCH /api/admin/notifications/<id>/read/
    Mark a notification as read
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, id):
        """Mark notification as read"""
        if not request.user.is_staff:
            return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        
        try:
            notification = Notification.objects.get(id=id, user=request.user)
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
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        """Mark all notifications as read"""
        if not request.user.is_staff:
            return Response({"detail": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        
        updated = Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        
        return Response({
            'updated_count': updated,
        }, status=status.HTTP_200_OK)

