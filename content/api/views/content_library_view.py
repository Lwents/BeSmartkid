from rest_framework import generics, status, permissions
from rest_framework.response import Response
from django.db.models import Q
from django.core.paginator import Paginator

from content import models
from content.serializers import ContentLibrarySerializer
from custom_account.api.permissions import RestrictRoles
from rest_framework import permissions


class LibraryRolePermission(permissions.BasePermission):
    """Allow teacher/instructor/admin."""
    allowed_roles = {'teacher', 'admin', 'instructor'}

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        role = getattr(request.user, 'role', None)
        if role in self.allowed_roles:
            return True
        # staff/superuser fallback
        if getattr(request.user, 'is_staff', False) or getattr(request.user, 'is_superuser', False):
            return True
        return False


class ContentLibraryListCreateView(generics.ListCreateAPIView):
    """
    GET /api/content-library/     -> list (with filters)
    POST /api/content-library/     -> create (auth, teacher)
    """
    serializer_class = ContentLibrarySerializer
    # Allow instructors/teachers/admins
    permission_classes = [permissions.IsAuthenticated, LibraryRolePermission]

    def get_queryset(self):
        queryset = models.ContentLibrary.objects.filter(owner=self.request.user)
        
        # Search
        q = self.request.query_params.get('q', '').strip()
        if q:
            queryset = queryset.filter(Q(title__icontains=q) | Q(subject__icontains=q))
        
        # Filter by grade_band
        grade_band = self.request.query_params.get('gradeBand', '').strip()
        if grade_band:
            queryset = queryset.filter(grade_band=grade_band)
        
        # Filter by type
        ctype = self.request.query_params.get('type', '').strip()
        if ctype:
            queryset = queryset.filter(type=ctype)
        
        return queryset.order_by('-updated_at')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        # Pagination
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('pageSize', 12))
        
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)
        
        serializer = self.get_serializer(page_obj.object_list, many=True)
        
        return Response({
            'items': serializer.data,
            'total': paginator.count,
            'page': page,
            'pageSize': page_size,
            'totalPages': paginator.num_pages
        })

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class ContentLibraryDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/content-library/<id>/     -> detail
    PUT /api/content-library/<id>/   -> update (owner only)
    DELETE /api/content-library/<id>/ -> delete (owner only)
    """
    serializer_class = ContentLibrarySerializer
    permission_classes = [permissions.IsAuthenticated, LibraryRolePermission]
    lookup_field = 'id'

    def get_queryset(self):
        return models.ContentLibrary.objects.filter(owner=self.request.user)

    def perform_update(self, serializer):
        serializer.save()

    def perform_destroy(self, instance):
        instance.delete()
