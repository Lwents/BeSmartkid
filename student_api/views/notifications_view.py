from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import serializers
import logging

from student_api.permissions import IsStudent
from activities.models import Notification

logger = logging.getLogger(__name__)


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'title', 'message', 'type', 'category', 'is_read', 'created_at', 'metadata']
        read_only_fields = ['id', 'created_at']
    
    def to_representation(self, instance):
        """Ensure all fields are properly serialized"""
        data = super().to_representation(instance)
        # Ensure is_read is boolean
        data['is_read'] = bool(instance.is_read) if hasattr(instance, 'is_read') else False
        # Ensure created_at is properly formatted as ISO string
        if 'created_at' in data and data['created_at']:
            if hasattr(instance.created_at, 'isoformat'):
                data['created_at'] = instance.created_at.isoformat()
        return data


class StudentNotificationsView(APIView):
    """
    GET /api/student/notifications/
    List notifications for the authenticated student
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request):
        try:
            user = request.user
            limit = int(request.query_params.get('limit', 20))
            
            notifications = Notification.objects.filter(
                user=user
            ).order_by('-created_at')[:limit]

            serializer = NotificationSerializer(notifications, many=True)
            logger.info(f"Returning {len(serializer.data)} notifications for user {user.id}")
            return Response({
                'notifications': serializer.data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error in StudentNotificationsView: {e}", exc_info=True)
            return Response({'error': f'Internal Server Error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class StudentNotificationReadView(APIView):
    """
    PATCH /api/student/notifications/<id>/read/
    Mark a notification as read
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def patch(self, request, id):
        try:
            user = request.user
            notification = Notification.objects.get(id=id, user=user)
            notification.is_read = True
            notification.save()
            
            return Response({'success': True}, status=status.HTTP_200_OK)

        except Notification.DoesNotExist:
            return Response({'error': 'Notification not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in StudentNotificationReadView: {e}", exc_info=True)
            return Response({'error': f'Internal Server Error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class StudentNotificationReadAllView(APIView):
    """
    PATCH /api/student/notifications/read-all/
    Mark all notifications as read
    """
    permission_classes = [IsAuthenticated, IsStudent]

    def patch(self, request):
        try:
            user = request.user
            Notification.objects.filter(user=user, is_read=False).update(is_read=True)
            
            return Response({'success': True}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error in StudentNotificationReadAllView: {e}", exc_info=True)
            return Response({'error': f'Internal Server Error: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

