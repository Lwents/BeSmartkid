# tests/api/test_assignment_views.py
"""Tests for Assignment API views."""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from rest_framework import status

from tests.base_test import BaseAPITestCase
from tests.factories import AssignmentFactory


@pytest.mark.django_db
class TestAssignmentViewSet(BaseAPITestCase):
    """Tests for AssignmentViewSet."""
    
    def setUp(self):
        """Setup test case."""
        super().setUp()
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        # Create users
        self.teacher = User.objects.create_user(
            username='teacher',
            email='teacher@test.com',
            password='pass'
        )
        self.teacher.role = 'teacher'
        self.teacher.save()
        
        self.student = User.objects.create_user(
            username='student',
            email='student@test.com',
            password='pass'
        )
        self.student.role = 'student'
        self.student.save()
    
    def test_create_assignment_as_teacher(self):
        """Test creating assignment as teacher."""
        self.authenticate_user(self.teacher)
        
        data = {
            'title': 'New Assignment',
            'description': 'Test',
            'assignment_type': 'homework',
            'max_score': '100.00',
            'due_date': (datetime.utcnow() + timedelta(days=7)).isoformat(),
            'allow_late_submissions': True,
            'late_penalty_percent': '10.00',
            'max_attempts': 3
        }
        
        response = self.client.post('/api/v1/assignments/', data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['title'] == 'New Assignment'
    
    def test_create_assignment_as_student_forbidden(self):
        """Test creating assignment as student is forbidden."""
        self.authenticate_user(self.student)
        
        data = {
            'title': 'New Assignment',
            'assignment_type': 'homework',
            'max_score': '100.00'
        }
        
        response = self.client.post('/api/v1/assignments/', data, format='json')
        assert response.status_code == status.HTTP_403_FORBIDDEN
    
    def test_publish_assignment(self):
        """Test publishing assignment."""
        self.authenticate_user(self.teacher)
        
        # Create assignment first
        assignment = AssignmentFactory.create(
            teacher=self.teacher,
            status='draft'
        )
        
        response = self.client.post(
            f'/api/v1/assignments/{assignment.id}/publish/'
        )
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'published'