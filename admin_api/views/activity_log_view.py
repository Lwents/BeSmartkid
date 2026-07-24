from datetime import datetime, timedelta
from django.db.models import Q
from django.core.paginator import Paginator
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from admin_api.permissions import IsAdmin
from custom_account.models import UserModel


class AdminActivityLogView(APIView):
    permission_classes = [IsAuthenticated, IsAdmin]

    def get(self, request, log_id=None):
        """Get activity logs list or detail"""
        if log_id:
            return self.get_detail(request, log_id)
        return self.get_list(request)
    
    def get_list(self, request):
        """Get activity logs"""
        # Placeholder - in production, query actual activity log model
        # For now, use user login history as placeholder

        q = request.query_params.get('q', '')
        action = request.query_params.get('action')
        user_id = request.query_params.get('userId')
        from_date = request.query_params.get('from')
        to_date = request.query_params.get('to')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('pageSize', 20))

        # Use user model to create activity logs from login history and signups
        # In production, this should use a dedicated ActivityLog model
        queryset = UserModel.objects.all()

        if q:
            queryset = queryset.filter(
                Q(email__icontains=q) |
                Q(username__icontains=q)
            )

        if user_id:
            queryset = queryset.filter(id=user_id)

        # Build activity log items from user data
        items = []
        for user in queryset:
            # Get user role label
            role_label = 'Admin' if user.is_staff or user.role == 'admin' else (
                'Giáo viên' if user.role == 'instructor' or user.role == 'teacher' else 'Học sinh'
            )
            
            # Add signup activity
            if user.created_on:
                items.append({
                    'id': f"{user.id}_signup",
                    'userId': str(user.id),
                    'userEmail': user.email,
                    'userRole': role_label,  # Add role label
                    'action': 'user.signup',
                    'ip': None,  # Not tracked in UserModel
                    'userAgent': None,  # Not tracked in UserModel
                    'timestamp': user.created_on.isoformat(),
                    'status': 'success',
                    'details': {'role': user.role, 'roleLabel': role_label}
                })
            
            # Add login activity if available
            if user.last_login:
                items.append({
                    'id': f"{user.id}_login",
                    'userId': str(user.id),
                    'userEmail': user.email,
                    'userRole': role_label,  # Add role label
                    'action': 'user.login',
                    'ip': None,  # Not tracked in UserModel
                    'userAgent': None,  # Not tracked in UserModel
                    'timestamp': user.last_login.isoformat(),
                    'status': 'success',
                    'details': {'role': user.role, 'roleLabel': role_label}
                })

        # Apply date filters
        if from_date:
            try:
                from_date_obj = datetime.fromisoformat(from_date.replace('Z', '+00:00'))
                items = [item for item in items if datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00')) >= from_date_obj]
            except:
                pass
        
        if to_date:
            try:
                to_date_obj = datetime.fromisoformat(to_date.replace('Z', '+00:00'))
                items = [item for item in items if datetime.fromisoformat(item['timestamp'].replace('Z', '+00:00')) <= to_date_obj]
            except:
                pass

        # Apply action filter
        if action:
            items = [item for item in items if action in item['action']]

        # Sort by timestamp descending
        items.sort(key=lambda x: x['timestamp'], reverse=True)

        # Paginate
        total = len(items)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_items = items[start:end]

        return Response({
            'items': paginated_items,
            'total': total
        }, status=status.HTTP_200_OK)

    def get_detail(self, request, log_id):
        """Get detailed activity log by ID"""
        # Parse log_id format: "{userId}_{action}" or just use it as is
        try:
            if '_' in log_id:
                user_id_str, action_type = log_id.split('_', 1)
                user_id = int(user_id_str)
            else:
                user_id = int(log_id)
                action_type = None
            
            user = UserModel.objects.get(id=user_id)
            role_label = 'Admin' if user.is_staff or user.role == 'admin' else (
                'Giáo viên' if user.role == 'instructor' or user.role == 'teacher' else 'Học sinh'
            )
            
            # Build detailed log item
            if action_type == 'signup' and user.created_on:
                log_item = {
                    'id': f"{user.id}_signup",
                    'userId': str(user.id),
                    'userEmail': user.email,
                    'userRole': role_label,
                    'action': 'user.signup',
                    'ip': getattr(user, 'last_login_ip', None),
                    'userAgent': getattr(user, 'last_login_user_agent', None),
                    'timestamp': user.created_on.isoformat(),
                    'status': 'success',
                    'details': {
                        'role': user.role,
                        'roleLabel': role_label,
                        'username': user.username,
                        'name': getattr(user, 'display_name', user.username),
                        'emailVerified': getattr(user, 'email_verified', False),
                        'createdAt': user.created_on.isoformat(),
                    }
                }
            elif (action_type == 'login' or action_type is None) and user.last_login:
                log_item = {
                    'id': f"{user.id}_login",
                    'userId': str(user.id),
                    'userEmail': user.email,
                    'userRole': role_label,
                    'action': 'user.login',
                    'ip': getattr(user, 'last_login_ip', None),
                    'userAgent': getattr(user, 'last_login_user_agent', None),
                    'timestamp': user.last_login.isoformat(),
                    'status': 'success',
                    'details': {
                        'role': user.role,
                        'roleLabel': role_label,
                        'username': user.username,
                        'name': getattr(user, 'display_name', user.username),
                        'lastLogin': user.last_login.isoformat(),
                    }
                }
            else:
                # Fallback: return signup if available
                if user.created_on:
                    log_item = {
                        'id': f"{user.id}_signup",
                        'userId': str(user.id),
                        'userEmail': user.email,
                        'userRole': role_label,
                        'action': 'user.signup',
                        'ip': None,
                        'userAgent': None,
                        'timestamp': user.created_on.isoformat(),
                        'status': 'success',
                        'details': {
                            'role': user.role,
                            'roleLabel': role_label,
                            'username': user.username,
                        }
                    }
                else:
                    return Response({'error': 'Log not found'}, status=status.HTTP_404_NOT_FOUND)
            
            return Response(log_item, status=status.HTTP_200_OK)
        except (ValueError, UserModel.DoesNotExist):
            return Response({'error': 'Log not found'}, status=status.HTTP_404_NOT_FOUND)




