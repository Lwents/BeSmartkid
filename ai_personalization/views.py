# # ai_personalization/views.py

# from rest_framework import generics, status
# from rest_framework.views import APIView
# from rest_framework.permissions import IsAuthenticated
# from rest_framework.response import Response
# from .serializers import LearningEventSerializer, RecommendationLogSerializer
# from .models import LearningEvent, RecommendationLog
# from .tasks import process_event
# from .services import RuleEngine

# class LearningEventView(generics.CreateAPIView):
#     permission_classes = [IsAuthenticated]
#     serializer_class = LearningEventSerializer

#     def perform_create(self, serializer):
#         ev = serializer.save(user=self.request.user)
#         # enqueue background task
#         process_event.delay(str(ev.id))

# class NextRecommendationView(APIView):
#     permission_classes = [IsAuthenticated]

#     def get(self, request, *args, **kwargs):
#         course_id = request.query_params.get('course_id')
#         top_n = int(request.query_params.get('top_n', 3))
#         if not course_id:
#             return Response({'error': 'course_id required'}, status=status.HTTP_400_BAD_REQUEST)
#         from content.models import Course
#         try:
#             course = Course.objects.get(id=course_id)
#         except Course.DoesNotExist:
#             return Response({'error': 'invalid course_id'}, status=status.HTTP_400_BAD_REQUEST)

#         engine = RuleEngine(request.user, course)
#         recs = engine.recommend(top_n=top_n)
#         return Response({'recommendations': recs})

# class RecommendationFeedbackView(APIView):
#     permission_classes = [IsAuthenticated]

#     def post(self, request, *args, **kwargs):
#         """
#         Body example:
#         {
#           "recommendation_id": "...",
#           "action": "accepted"|"skipped"|"completed",
#           "feedback": {"outcome": true, "attempts": 2}
#         }
#         """
#         rec_id = request.data.get('recommendation_id')
#         action = request.data.get('action')
#         feedback = request.data.get('feedback', {})
#         try:
#             rec = RecommendationLog.objects.get(id=rec_id, user=request.user)
#         except RecommendationLog.DoesNotExist:
#             return Response({'error': 'invalid recommendation_id'}, status=status.HTTP_400_BAD_REQUEST)
#         rec.acted_at = rec.acted_at or rec.shown_at
#         rec.accepted = (action == 'accepted')
#         rec.feedback = feedback
#         rec.save()
#         return Response({'status': 'ok'})


# ai_personalization/views.py
"""
Complete Django REST Framework views for AI personalization API.
All ViewSets and custom views in one file for easy import.
"""
from rest_framework import viewsets, status, permissions, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.core.cache import cache
from django.db.models import Avg, Count, Q, F
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from typing import Dict, List
import logging

from .models import (
    LearningPath, Recommendation, LearningEvent,
    UserSkillMastery, ContentSkill, RecommendationLog,
    SkillPrerequisite, UserProfile
)
from .serializers import (
    LearningPathSerializer, RecommendationSerializer,
    LearningEventSerializer, UserSkillMasterySerializer,
    ContentSkillSerializer, MasteryDashboardSerializer,
    PathGenerationRequestSerializer, RecommendationRequestSerializer,
    RecommendationLogSerializer, SkillPrerequisiteSerializer
)
from .ai_engines import (
    PersonalizationEngine, PathGenerator, RecommendationEngine
)
from .permissions import IsStudent, IsTeacherOrAdmin, IsOwnerOrTeacher
from .exceptions import PersonalizationError, InsufficientDataError

logger = logging.getLogger(__name__)


class LearningPathViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing personalized learning paths.
    
    Endpoints:
        GET    /api/personalization/paths/              - List paths
        POST   /api/personalization/paths/              - Create path (auto-generate)
        GET    /api/personalization/paths/{id}/         - Get specific path
        PUT    /api/personalization/paths/{id}/         - Update path
        DELETE /api/personalization/paths/{id}/         - Delete path
        POST   /api/personalization/paths/generate/     - Generate new path
        POST   /api/personalization/paths/{id}/regenerate/ - Regenerate existing path
    """
    serializer_class = LearningPathSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['course', 'ai_model']
    ordering_fields = ['generated_at']
    ordering = ['-generated_at']
    
    def get_queryset(self):
        """Filter paths based on user role."""
        user = self.request.user
        
        if user.is_staff or hasattr(user, 'teacher_profile'):
            # Teachers and admins can see all paths
            return LearningPath.objects.all().select_related('student', 'course')
        
        # Students only see their own paths
        return LearningPath.objects.filter(
            student=user
        ).select_related('course')
    
    def perform_create(self, serializer):
        """Auto-set student to current user."""
        serializer.save(student=self.request.user)
    
    @action(detail=False, methods=['post'], permission_classes=[IsStudent])
    def generate(self, request):
        """
        Generate a new personalized learning path.
        
        POST /api/personalization/paths/generate/
        
        Request Body:
        {
            "course_id": "uuid",
            "preferences": {"difficulty": "medium"},
            "focus_areas": ["fractions", "decimals"],
            "difficulty_target": "adaptive"
        }
        
        Response: LearningPath object with ordered lesson list
        """
        serializer = PathGenerationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            generator = PathGenerator()
            path = generator.generate_path(
                student=request.user,
                course_id=serializer.validated_data['course_id'],
                preferences=serializer.validated_data.get('preferences', {}),
                focus_areas=serializer.validated_data.get('focus_areas', []),
                difficulty_target=serializer.validated_data.get('difficulty_target', 'adaptive')
            )
            
            response_serializer = LearningPathSerializer(path)
            
            logger.info(
                f"Generated path for user {request.user.id}, "
                f"course {serializer.validated_data['course_id']}"
            )
            
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            logger.error(f"Path generation failed for user {request.user.id}: {str(e)}")
            return Response(
                {
                    'error': 'Failed to generate learning path',
                    'detail': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'], permission_classes=[IsStudent])
    def regenerate(self, request, pk=None):
        """
        Regenerate an existing path based on updated mastery.
        
        POST /api/personalization/paths/{id}/regenerate/
        
        Response: Updated LearningPath with new lesson ordering
        """
        path = self.get_object()
        
        # Security check: students can only regenerate their own paths
        if path.student != request.user:
            return Response(
                {'error': 'You can only regenerate your own learning paths'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            generator = PathGenerator()
            updated_path = generator.regenerate_path(path)
            
            serializer = LearningPathSerializer(updated_path)
            
            logger.info(f"Regenerated path {pk} for user {request.user.id}")
            
            return Response(serializer.data)
            
        except Exception as e:
            logger.error(f"Path regeneration failed for path {pk}: {str(e)}")
            return Response(
                {
                    'error': 'Failed to regenerate learning path',
                    'detail': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['get'])
    def progress(self, request, pk=None):
        """
        Get progress statistics for a learning path.
        
        GET /api/personalization/paths/{id}/progress/
        
        Response: Progress metrics (completed, in_progress, not_started)
        """
        path = self.get_object()
        
        # Count completed lessons
        completed_lesson_ids = LearningEvent.objects.filter(
            user=path.student,
            event_type='complete'
        ).values_list('lesson_id', flat=True).distinct()
        
        total_lessons = len(path.path)
        completed_count = sum(
            1 for step in path.path 
            if step['lesson_id'] in [str(lid) for lid in completed_lesson_ids]
        )
        
        return Response({
            'total_lessons': total_lessons,
            'completed': completed_count,
            'remaining': total_lessons - completed_count,
            'progress_percentage': (completed_count / total_lessons * 100) if total_lessons > 0 else 0
        })


class RecommendationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for AI-generated recommendations (read-only).
    
    Endpoints:
        GET  /api/personalization/recommendations/           - List recommendations
        GET  /api/personalization/recommendations/{id}/      - Get specific recommendation
        POST /api/personalization/recommendations/refresh/   - Generate fresh recommendations
    """
    serializer_class = RecommendationSerializer
    permission_classes = [permissions.IsAuthenticated, IsStudent]
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ['score', 'generated_at']
    ordering = ['-score', '-generated_at']
    
    def get_queryset(self):
        """
        Get recommendations for current user, cached for 5 minutes.
        Automatically filters out stale recommendations (>7 days old).
        """
        user = self.request.user
        cache_key = f"recommendations:{user.id}"
        
        # Try cache first
        cached_recs = cache.get(cache_key)
        if cached_recs is not None:
            return cached_recs
        
        # Query database
        cutoff_date = timezone.now() - timezone.timedelta(days=7)
        queryset = Recommendation.objects.filter(
            student=user,
            generated_at__gte=cutoff_date
        ).select_related('recommended_lesson', 'recommended_lesson__course').order_by('-score')[:10]
        
        # Convert to list for caching
        queryset_list = list(queryset)
        
        # Cache for 5 minutes
        cache.set(cache_key, queryset_list, 300)
        
        return queryset_list
    
    @action(detail=False, methods=['post'])
    def refresh(self, request):
        """
        Generate fresh recommendations for the user.
        
        POST /api/personalization/recommendations/refresh/
        
        Request Body:
        {
            "limit": 5,
            "exclude_completed": true,
            "include_reasoning": true,
            "algorithm": "hybrid"  // "hybrid", "collaborative", "content_based", "rule_based"
        }
        
        Response: List of new Recommendation objects
        """
        serializer = RecommendationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            engine = RecommendationEngine()
            recommendations = engine.generate_recommendations(
                student=request.user,
                limit=serializer.validated_data.get('limit', 5),
                exclude_completed=serializer.validated_data.get('exclude_completed', True),
                algorithm=serializer.validated_data.get('algorithm', 'hybrid')
            )
            
            # Invalidate cache
            cache_key = f"recommendations:{request.user.id}"
            cache.delete(cache_key)
            
            response_serializer = RecommendationSerializer(recommendations, many=True)
            
            logger.info(
                f"Generated {len(recommendations)} recommendations "
                f"for user {request.user.id} using {serializer.validated_data.get('algorithm', 'hybrid')}"
            )
            
            return Response(response_serializer.data)
            
        except InsufficientDataError as e:
            logger.warning(f"Insufficient data for user {request.user.id}: {str(e)}")
            return Response(
                {
                    'error': 'Insufficient data for personalized recommendations',
                    'detail': str(e),
                    'suggestion': 'Complete a few more lessons to get better recommendations'
                },
                status=status.HTTP_200_OK  # Not an error, just informational
            )
        except Exception as e:
            logger.error(f"Recommendation generation failed for user {request.user.id}: {str(e)}")
            return Response(
                {
                    'error': 'Failed to generate recommendations',
                    'detail': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        """
        Mark a recommendation as accepted (user started the lesson).
        
        POST /api/personalization/recommendations/{id}/accept/
        
        Response: Updated recommendation
        """
        recommendation = self.get_object()
        
        # Log acceptance
        try:
            log = RecommendationLog.objects.filter(
                user=request.user,
                lesson=recommendation.recommended_lesson,
                accepted__isnull=True
            ).order_by('-shown_at').first()
            
            if log:
                log.mark_accepted()
                logger.info(
                    f"User {request.user.id} accepted recommendation "
                    f"{recommendation.id} for lesson {recommendation.recommended_lesson.id}"
                )
            
            return Response({'status': 'accepted'})
            
        except Exception as e:
            logger.error(f"Failed to mark recommendation {pk} as accepted: {str(e)}")
            return Response(
                {'error': 'Failed to record acceptance'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class LearningEventViewSet(viewsets.ModelViewSet):
    """
    ViewSet for learning events (high-throughput writes).
    Optimized for fast event ingestion from frontend.
    
    Endpoints:
        POST /api/personalization/events/                  - Create single event
        POST /api/personalization/events/batch_create/     - Batch create events
        GET  /api/personalization/events/                  - List user events
        GET  /api/personalization/events/{id}/             - Get specific event
    """
    serializer_class = LearningEventSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['event_type', 'lesson', 'course']
    ordering_fields = ['timestamp']
    ordering = ['-timestamp']
    
    def get_queryset(self):
        """Get events for current user only (last 100 by default)."""
        queryset = LearningEvent.objects.filter(
            user=self.request.user
        ).select_related('course', 'lesson').order_by('-timestamp')
        
        # Limit to recent events for performance
        limit = self.request.query_params.get('limit', 100)
        try:
            limit = int(limit)
            queryset = queryset[:min(limit, 1000)]  # Max 1000 events
        except (ValueError, TypeError):
            queryset = queryset[:100]
        
        return queryset
    
    def create(self, request, *args, **kwargs):
        """
        Create a new learning event (optimized for speed).
        
        POST /api/personalization/events/
        
        Request Body:
        {
            "lesson": "uuid",
            "event_type": "submit",
            "detail": {
                "correct": true,
                "attempts": 1,
                "time_spent": 120
            },
            "session_id": "uuid" (optional)
        }
        
        Response: Created event object
        """
        # Automatically set user
        data = request.data.copy()
        data['user'] = request.user.id
        
        # Set timestamp if not provided
        if 'timestamp' not in data:
            data['timestamp'] = timezone.now().isoformat()
        
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        
        # Save event (triggers signal for mastery update)
        self.perform_create(serializer)
        
        headers = self.get_success_headers(serializer.data)
        
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers
        )
    
    @action(detail=False, methods=['post'])
    def batch_create(self, request):
        """
        Batch create multiple events (for offline sync).
        
        POST /api/personalization/events/batch_create/
        
        Request Body:
        {
            "events": [
                {"lesson": "uuid", "event_type": "start", "detail": {}},
                {"lesson": "uuid", "event_type": "submit", "detail": {"correct": true}}
            ]
        }
        
        Response: {"created": count}
        """
        events_data = request.data.get('events', [])
        
        if not isinstance(events_data, list):
            return Response(
                {'error': 'events must be a list'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if len(events_data) > 100:
            return Response(
                {'error': 'Maximum 100 events per batch'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Add user to each event
        for event_data in events_data:
            event_data['user'] = request.user.id
            if 'timestamp' not in event_data:
                event_data['timestamp'] = timezone.now().isoformat()
        
        serializer = self.get_serializer(data=events_data, many=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        logger.info(f"Batch created {len(serializer.data)} events for user {request.user.id}")
        
        return Response(
            {'created': len(serializer.data), 'events': serializer.data},
            status=status.HTTP_201_CREATED
        )
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Get event statistics for current user.
        
        GET /api/personalization/events/statistics/
        
        Response: Aggregated statistics
        """
        events = self.get_queryset()
        
        total_events = events.count()
        by_type = events.values('event_type').annotate(count=Count('id'))
        
        # Calculate success rate
        submit_events = events.filter(event_type='submit')
        successful = submit_events.filter(detail__correct=True).count()
        total_submits = submit_events.count()
        success_rate = (successful / total_submits * 100) if total_submits > 0 else 0
        
        return Response({
            'total_events': total_events,
            'by_type': list(by_type),
            'success_rate': round(success_rate, 2),
            'date_range': {
                'first_event': events.last().timestamp if events.exists() else None,
                'last_event': events.first().timestamp if events.exists() else None
            }
        })


class UserSkillMasteryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing skill mastery (read-only for students).
    Teachers can view all masteries for their students.
    
    Endpoints:
        GET /api/personalization/mastery/                  - List masteries
        GET /api/personalization/mastery/{id}/             - Get specific mastery
        GET /api/personalization/mastery/dashboard/        - Dashboard with stats
        GET /api/personalization/mastery/needs_practice/   - Skills needing practice
    """
    serializer_class = UserSkillMasterySerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['skill']
    ordering_fields = ['mastery', 'last_update', 'practice_count']
    ordering = ['-mastery']
    
    def get_queryset(self):
        """Get masteries for current user or filtered by teacher."""
        user = self.request.user
        
        if user.is_staff or hasattr(user, 'teacher_profile'):
            # Teachers can filter by student
            student_id = self.request.query_params.get('student_id')
            if student_id:
                return UserSkillMastery.objects.filter(
                    user_id=student_id
                ).select_related('user')
            return UserSkillMastery.objects.all().select_related('user')
        
        # Students only see their own masteries
        return UserSkillMastery.objects.filter(user=user)
    
    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """
        Get mastery dashboard with aggregated statistics.
        
        GET /api/personalization/mastery/dashboard/
        
        Response: Statistics including mastered/proficient/learning counts
        """
        masteries = self.get_queryset()
        
        total_skills = masteries.count()
        
        if total_skills == 0:
            return Response({
                'message': 'No skill mastery data yet. Start learning to see your progress!',
                'total_skills': 0
            })
        
        mastered = masteries.filter(mastery__gte=0.9).count()
        proficient = masteries.filter(mastery__gte=0.7, mastery__lt=0.9).count()
        learning = masteries.filter(mastery__gte=0.3, mastery__lt=0.7).count()
        beginner = masteries.filter(mastery__lt=0.3).count()
        
        weak_skills = list(
            masteries.filter(mastery__lt=0.5)
            .order_by('mastery')[:10]
            .values_list('skill', flat=True)
        )
        
        avg_mastery = masteries.aggregate(Avg('mastery'))['mastery__avg'] or 0.0
        
        skills_needing_practice = masteries.filter(
            mastery__lt=0.7
        ).order_by('mastery')[:5]
        
        dashboard_data = {
            'total_skills': total_skills,
            'mastered_skills': mastered,
            'proficient_skills': proficient,
            'learning_skills': learning,
            'beginner_skills': beginner,
            'weak_skills': weak_skills,
            'average_mastery': round(avg_mastery, 3),
            # 'skills_needing_practice': UserSkillMasterySerializer(
            #     skills_needing_practice,
            #     many=True
            # ).data
            'skills_needing_practice': skills_needing_practice
        }
        
        serializer = MasteryDashboardSerializer(dashboard_data)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def needs_practice(self, request):
        """
        Get skills that need practice based on HLR decay.
        
        GET /api/personalization/mastery/needs_practice/
        
        Response: List of skills with recall probability < 0.5
        """
        masteries = self.get_queryset()
        
        # Calculate recall probability for each mastery
        needs_practice = []
        for mastery in masteries:
            recall_prob = mastery.calculate_recall_probability()
            if recall_prob < 0.5:  # Below 50% recall
                days_since = (timezone.now() - mastery.last_update).days
                needs_practice.append({
                    'skill': mastery.skill,
                    'mastery': round(mastery.mastery, 3),
                    'recall_probability': round(recall_prob, 3),
                    'days_since_practice': days_since,
                    'half_life_days': round(mastery.half_life_days, 1),
                    'urgency': 'high' if recall_prob < 0.3 else 'medium'
                })
        
        # Sort by lowest recall probability (most urgent first)
        needs_practice.sort(key=lambda x: x['recall_probability'])
        
        return Response({
            'skills_needing_practice': needs_practice[:10],
            'total_count': len(needs_practice),
            'recommendation': 'Practice these skills soon to maintain your mastery!' if needs_practice else 'Great job! All skills are fresh in memory.'
        })
    
    @action(detail=False, methods=['get'])
    def by_category(self, request):
        """
        Get masteries grouped by skill category.
        
        GET /api/personalization/mastery/by_category/
        
        Response: Masteries grouped by top-level category (e.g., 'math', 'science')
        """
        masteries = self.get_queryset()
        
        categories = {}
        for mastery in masteries:
            # Extract category from skill (e.g., 'math:fractions:add' -> 'math')
            parts = mastery.skill.split(':')
            category = parts[0] if parts else 'uncategorized'
            
            if category not in categories:
                categories[category] = {
                    'category': category,
                    'skills': [],
                    'average_mastery': 0,
                    'total_skills': 0
                }
            
            categories[category]['skills'].append({
                'skill': mastery.skill,
                'mastery': round(mastery.mastery, 3)
            })
            categories[category]['total_skills'] += 1
        
        # Calculate averages
        for cat_data in categories.values():
            total_mastery = sum(s['mastery'] for s in cat_data['skills'])
            cat_data['average_mastery'] = round(
                total_mastery / cat_data['total_skills'], 
                3
            ) if cat_data['total_skills'] > 0 else 0
        
        return Response({
            'categories': list(categories.values())
        })


class PersonalizationAnalyticsView(APIView):
    """
    Analytics endpoint for personalization performance.
    Restricted to teachers and admins.
    
    Endpoints:
        GET /api/personalization/analytics/
    """
    permission_classes = [permissions.IsAuthenticated, IsTeacherOrAdmin]
    
    def get(self, request):
        """
        Get personalization system analytics.
        
        GET /api/personalization/analytics/
        
        Response: System-wide analytics and metrics
        """
        # Recommendation acceptance rate
        logs = RecommendationLog.objects.all()
        total_shown = logs.count()
        total_accepted = logs.filter(accepted=True).count()
        acceptance_rate = (total_accepted / total_shown * 100) if total_shown > 0 else 0
        
        # Acceptance rate by source
        by_source = logs.values('source').annotate(
            total=Count('id'),
            accepted=Count('id', filter=Q(accepted=True))
        ).annotate(
            rate=F('accepted') * 100.0 / F('total')
        )
        
        # Average mastery by age group
        avg_mastery_by_age = UserSkillMastery.objects.values(
            'user__personalization_profile__age_group'
        ).annotate(
            avg_mastery=Avg('mastery'),
            student_count=Count('user', distinct=True)
        )
        
        # Active learning paths
        active_paths = LearningPath.objects.filter(
            generated_at__gte=timezone.now() - timezone.timedelta(days=30)
        ).count()
        
        # Recent events
        recent_events = LearningEvent.objects.filter(
            timestamp__gte=timezone.now() - timezone.timedelta(days=7)
        ).count()
        
        # Success rate trend
        submit_events = LearningEvent.objects.filter(event_type='submit')
        successful = submit_events.filter(detail__correct=True).count()
        total_submits = submit_events.count()
        overall_success_rate = (successful / total_submits * 100) if total_submits > 0 else 0
        
        return Response({
            'recommendation_metrics': {
                'acceptance_rate': round(acceptance_rate, 2),
                'total_shown': total_shown,
                'total_accepted': total_accepted,
                'by_source': list(by_source)
            },
            'mastery_metrics': {
                'by_age_group': list(avg_mastery_by_age)
            },
            'activity_metrics': {
                'active_paths_30d': active_paths,
                'events_7d': recent_events,
                'overall_success_rate': round(overall_success_rate, 2)
            },
            'timestamp': timezone.now().isoformat()
        })


class SkillGraphView(APIView):
    """
    Endpoint for skill dependency graph visualization.
    
    Endpoints:
        GET /api/personalization/skill-graph/
        GET /api/personalization/skill-graph/?skill=math:fractions:add
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """
        Get skill prerequisite graph.
        
        GET /api/personalization/skill-graph/
        GET /api/personalization/skill-graph/?skill=<skill_name>
        
        Response: Skill dependency graph or specific skill's prerequisites
        """
        skill_param = request.query_params.get('skill')
        
        if skill_param:
            # Get prerequisites and dependents for specific skill
            prerequisites = SkillPrerequisite.objects.filter(
                skill=skill_param
            ).values('prerequisite_skill', 'strength')
            
            dependents = SkillPrerequisite.objects.filter(
                prerequisite_skill=skill_param
            ).values('skill', 'strength')
            
            # Check if user has met prerequisites
            if not request.user.is_staff:
                user_masteries = UserSkillMastery.objects.filter(
                    user=request.user,
                    skill__in=[p['prerequisite_skill'] for p in prerequisites]
                ).values('skill', 'mastery')
                
                mastery_map = {m['skill']: m['mastery'] for m in user_masteries}
                
                for prereq in prerequisites:
                    prereq['user_mastery'] = mastery_map.get(
                        prereq['prerequisite_skill'], 
                        0.0
                    )
                    required_mastery = 0.5 + (0.3 * prereq['strength'])
                    prereq['met'] = prereq['user_mastery'] >= required_mastery
            
            return Response({
                'skill': skill_param,
                'prerequisites': list(prerequisites),
                'dependents': list(dependents),
                'ready': all(p.get('met', True) for p in prerequisites)
            })
        
        # Get full graph
        all_prerequisites = SkillPrerequisite.objects.all().values(
            'skill', 'prerequisite_skill', 'strength'
        )
        
        # Build adjacency list
        graph = {}
        all_skills = set()
        
        for prereq in all_prerequisites:
            skill = prereq['skill']
            all_skills.add(skill)
            all_skills.add(prereq['prerequisite_skill'])
            
            if skill not in graph:
                graph[skill] = {
                    'prerequisites': [],
                    'dependents': []
                }
            
            graph[skill]['prerequisites'].append({
                'skill': prereq['prerequisite_skill'],
                'strength': prereq['strength']
            })
            
            # Add to dependent's list
            dep_skill = prereq['prerequisite_skill']
            if dep_skill not in graph:
                graph[dep_skill] = {
                    'prerequisites': [],
                    'dependents': []
                }
            graph[dep_skill]['dependents'].append({
                'skill': skill,
                'strength': prereq['strength']
            })
        
        return Response({
            'graph': graph,
            'total_skills': len(all_skills),
            'total_edges': all_prerequisites.count(),
            'skills': sorted(list(all_skills))
        })

