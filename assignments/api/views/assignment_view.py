# api/v1/views/assignment_views.py
"""ViewSets for Assignment API."""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from ..serializers.assignment_serializer import (
    AssignmentCreateSerializer,
    AssignmentResponseSerializer,
    SubmissionCreateSerializer,
    GradeSubmissionSerializer
)
from ..permissions import IsTeacher, IsStudent, IsAssignmentOwner, CanGrade
from assignments.application.services.assignment_service import AssignmentService
from assignments.application.services.submission_service import SubmissionService
from assignments.application.services.grading_service import GradingService
from assignments.infrastructure.repositories.assignment_repository import AssignmentRepository
from assignments.infrastructure.repositories.submission_repository import SubmissionRepository
from assignments.infrastructure.repositories.grade_repository import GradeRepository
from assignments.domain.exceptions import (
    AssignmentNotFound,
    SubmissionNotAllowed,
    InvalidGrade
)


class AssignmentViewSet(viewsets.ViewSet):
    """ViewSet for assignment CRUD operations."""
    
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'assignment_type', 'classroom']
    search_fields = ['title', 'description']
    ordering_fields = ['created_at', 'due_date', 'title']
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Initialize services
        assignment_repo = AssignmentRepository()
        submission_repo = SubmissionRepository()
        grade_repo = GradeRepository()
        
        self.assignment_service = AssignmentService(assignment_repo)
        self.submission_service = SubmissionService(submission_repo, assignment_repo)
        self.grading_service = GradingService(grade_repo, submission_repo, assignment_repo)
    
    def create(self, request):
        """Create new assignment."""
        self.permission_classes = [IsAuthenticated, IsTeacher]
        self.check_permissions(request)
        
        serializer = AssignmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        dto = serializer.to_dto(teacher_id=request.user.id)
        
        try:
            result = self.assignment_service.create_assignment(dto)
            response_serializer = AssignmentResponseSerializer(result)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def retrieve(self, request, pk=None):
        """Get assignment by ID."""
        try:
            result = self.assignment_service.get_assignment(pk)
            serializer = AssignmentResponseSerializer(result)
            return Response(serializer.data)
        except AssignmentNotFound as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_404_NOT_FOUND
            )
    
    def list(self, request):
        """List assignments (filtered by classroom if provided)."""
        classroom_id = request.query_params.get('classroom_id')
        
        if classroom_id:
            try:
                assignments = self.assignment_service.list_classroom_assignments(classroom_id)
                serializer = AssignmentResponseSerializer(assignments, many=True)
                return Response(serializer.data)
            except Exception as e:
                return Response(
                    {'error': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        return Response(
            {'error': 'classroom_id required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsTeacher])
    def publish(self, request, pk=None):
        """Publish assignment."""
        try:
            result = self.assignment_service.publish_assignment(pk)
            serializer = AssignmentResponseSerializer(result)
            return Response(serializer.data)
        except AssignmentNotFound as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsStudent])
    def submit(self, request, pk=None):
        """Submit assignment."""
        serializer = SubmissionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        dto = serializer.to_dto(
            assignment_id=pk,
            student_id=request.user.id
        )
        
        try:
            # Create submission
            submission = self.submission_service.create_submission(dto)
            # Submit it
            submitted = self.submission_service.submit_assignment(submission.id)
            
            return Response(
                {
                    'id': str(submitted.id),
                    'status': submitted.status.value,
                    'submitted_at': submitted.submitted_at,
                    'is_late': submitted.is_late,
                    'late_days': submitted.late_days
                },
                status=status.HTTP_201_CREATED
            )
        except (AssignmentNotFound, SubmissionNotAllowed) as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=True, methods=['post'], url_path='submissions/(?P<submission_id>[^/.]+)/grade')
    def grade_submission(self, request, pk=None, submission_id=None):
        """Grade a submission."""
        self.permission_classes = [IsAuthenticated, CanGrade]
        self.check_permissions(request)
        
        serializer = GradeSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        dto = serializer.to_dto(
            submission_id=submission_id,
            grader_id=request.user.id
        )
        
        try:
            grade = self.grading_service.grade_submission(dto)
            
            return Response(
                {
                    'id': str(grade.id),
                    'raw_score': float(grade.raw_score.points),
                    'final_score': float(grade.score.points),
                    'max_score': float(grade.score.max_points),
                    'percentage': float(grade.score.percentage),
                    'letter_grade': grade.score.to_letter_grade(),
                    'late_penalty_applied': float(grade.late_penalty_applied),
                    'feedback': grade.feedback,
                    'graded_at': grade.graded_at
                },
                status=status.HTTP_201_CREATED
            )
        except (InvalidGrade, AssignmentNotFound) as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )