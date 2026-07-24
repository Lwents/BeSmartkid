# tests/api/test_integration.py
"""Integration tests for full workflows."""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from rest_framework import status

from tests.base_test import BaseAPITestCase


@pytest.mark.django_db
class TestAssignmentWorkflow(BaseAPITestCase):
    """Test complete assignment workflow."""
    
    def setUp(self):
        """Setup test case."""
        super().setUp()
        from django.contrib.auth import get_user_model
        from uuid import uuid4
        
        User = get_user_model()
        
        self.teacher = User.objects.create_user(
            username='teacher',
            password='pass'
        )
        self.teacher.role = 'teacher'
        self.teacher.save()
        
        self.student = User.objects.create_user(
            username='student',
            password='pass'
        )
        self.student.role = 'student'
        self.student.save()
        
        self.classroom_id = str(uuid4())
    
    def test_complete_workflow(self):
        """Test complete assignment workflow: create -> publish -> submit -> grade."""
        
        # Step 1: Teacher creates assignment
        self.authenticate_user(self.teacher)
        
        create_data = {
            'title': 'Math Homework',
            'description': 'Complete exercises 1-10',
            'assignment_type': 'homework',
            'max_score': '100.00',
            'due_date': (datetime.utcnow() + timedelta(days=7)).isoformat(),
            'classroom_id': self.classroom_id,
            'allow_late_submissions': True,
            'late_penalty_percent': '10.00',
            'max_attempts': 2
        }
        
        response = self.client.post(
            '/api/v1/assignments/',
            create_data,
            format='json'
        )
        assert response.status_code == status.HTTP_201_CREATED
        assignment_id = response.data['id']
        
        # Step 2: Teacher publishes assignment
        response = self.client.post(
            f'/api/v1/assignments/{assignment_id}/publish/'
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'published'
        
        # Step 3: Student submits assignment
        self.authenticate_user(self.student)
        
        submit_data = {
            'content': 'My completed homework'
        }
        
        response = self.client.post(
            f'/api/v1/assignments/{assignment_id}/submit/',
            submit_data,
            format='json'
        )
        assert response.status_code == status.HTTP_201_CREATED
        submission_id = response.data['id']
        assert response.data['status'] == 'submitted'
        
        # Step 4: Teacher grades submission
        self.authenticate_user(self.teacher)
        
        grade_data = {
            'score': '90.00',
            'max_score': '100.00',
            'feedback': 'Great work!'
        }
        
        response = self.client.post(
            f'/api/v1/assignments/{assignment_id}/submissions/{submission_id}/grade/',
            grade_data,
            format='json'
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data['final_score'] == 90.0
        assert response.data['letter_grade'] == 'A'
        assert response.data['feedback'] == 'Great work!'