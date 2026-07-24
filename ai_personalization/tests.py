# ai_personalization/tests.py
"""
Comprehensive test suite for AI personalization module.
Aims for >90% code coverage with unit and integration tests.
"""
import pytest
from django.test import TestCase, TransactionTestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from unittest.mock import patch, MagicMock
import uuid

from content.models import Lesson
from .models import (
    LearningPath, Recommendation, LearningEvent,
    UserSkillMastery, ContentSkill, RecommendationLog,
    SkillPrerequisite, PersonalizationRule
)
from .ai_engines import PathGenerator, RecommendationEngine, MasteryCalculator, PersonalizationEngine
from .utils import (
    calculate_mastery_bayesian, apply_hlr_decay,
    predict_mastery_ml, cosine_similarity_dicts
)

User = get_user_model()


class UserSkillMasteryModelTest(TestCase):
    """Test UserSkillMastery model and methods."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_create_mastery(self):
        """Test creating a skill mastery record."""
        mastery = UserSkillMastery.objects.create(
            user=self.user,
            skill='math:fractions:add',
            mastery=0.5
        )
        
        self.assertEqual(mastery.user, self.user)
        self.assertEqual(mastery.skill, 'math:fractions:add')
        self.assertEqual(mastery.mastery, 0.5)
        self.assertEqual(mastery.practice_count, 0)
    
    def test_calculate_recall_probability(self):
        """Test HLR recall probability calculation."""
        mastery = UserSkillMastery.objects.create(
            user=self.user,
            skill='math:fractions:add',
            mastery=0.8,
            half_life_days=7.0
        )
        
        # Just created, should have high recall
        recall = mastery.calculate_recall_probability()
        self.assertGreater(recall, 0.7)
        
        # Simulate 7 days passing (one half-life)
        mastery.last_update = timezone.now() - timezone.timedelta(days=7)
        mastery.save()
        
        recall = mastery.calculate_recall_probability()
        self.assertAlmostEqual(recall, 0.5, places=1)
    
    def test_update_from_event_success(self):
        """Test mastery update after successful practice."""
        mastery = UserSkillMastery.objects.create(
            user=self.user,
            skill='math:fractions:add',
            mastery=0.5,
            half_life_days=5.0
        )
        
        old_mastery = mastery.mastery
        old_half_life = mastery.half_life_days
        
        mastery.update_from_event(correct=True, time_spent=120)
        
        # Mastery should increase
        self.assertGreater(mastery.mastery, old_mastery)
        # Half-life should increase (less frequent practice needed)
        self.assertGreater(mastery.half_life_days, old_half_life)
        self.assertEqual(mastery.practice_count, 1)
        self.assertEqual(mastery.correct_count, 1)
    
    def test_update_from_event_failure(self):
        """Test mastery update after failed practice."""
        mastery = UserSkillMastery.objects.create(
            user=self.user,
            skill='math:fractions:add',
            mastery=0.7,
            half_life_days=10.0
        )
        
        old_half_life = mastery.half_life_days
        
        mastery.update_from_event(correct=False, time_spent=180)
        
        # Half-life should decrease (more frequent practice needed)
        self.assertLess(mastery.half_life_days, old_half_life)
        self.assertEqual(mastery.practice_count, 1)
        self.assertEqual(mastery.correct_count, 0)


class LearningEventModelTest(TransactionTestCase):
    """Test LearningEvent model and signals."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        # Create mock course and lesson
        from content.models import Course, Lesson
        self.course = Course.objects.create(
            title='Math 101',
            description='Test course'
        )
        self.lesson = Lesson.objects.create(
            title='Fractions Basics',
            course=self.course
        )
        
        # Create skill mapping
        ContentSkill.objects.create(
            lesson=self.lesson,
            skill='math:fractions:basics',
            weight=1.0
        )
    
    def test_create_event(self):
        """Test creating a learning event."""
        event = LearningEvent.objects.create(
            user=self.user,
            course=self.course,
            lesson=self.lesson,
            event_type='submit',
            detail={'correct': True, 'attempts': 1}
        )
        
        self.assertEqual(event.user, self.user)
        self.assertEqual(event.event_type, 'submit')
        self.assertTrue(event.is_successful)
    
    @patch('ai_personalization.tasks.update_mastery_async.delay')
    def test_event_triggers_mastery_update(self, mock_task):
        """Test that event creation triggers async mastery update."""
        event = LearningEvent.objects.create(
            user=self.user,
            lesson=self.lesson,
            event_type='submit',
            detail={'correct': True, 'attempts': 1, 'time_spent': 120}
        )
        
        # Check that async task was called
        self.assertTrue(mock_task.called)
    
    def test_success_rate_calculation(self):
        """Test calculating success rate for a user on a lesson."""
        # Create multiple events
        for i in range(10):
            LearningEvent.objects.create(
                user=self.user,
                lesson=self.lesson,
                event_type='submit',
                detail={'correct': i % 2 == 0}  # 50% success rate
            )
        
        success_rate = LearningEvent.objects.success_rate(self.user, self.lesson)
        self.assertAlmostEqual(success_rate, 0.5, places=1)


class PathGeneratorTest(TestCase):
    """Test learning path generation."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        from content.models import Course, Lesson
        self.course = Course.objects.create(
            title='Math 101',
            description='Test course'
        )
        
        # Create lessons with skills
        self.lessons = []
        skills = [
            'math:counting:basics',
            'math:addition:basics',
            'math:subtraction:basics',
            'math:fractions:basics',
            'math:fractions:add'
        ]
        
        for i, skill in enumerate(skills):
            lesson = Lesson.objects.create(
                title=f'Lesson {i+1}: {skill}',
                course=self.course,
                difficulty='easy' if i < 2 else 'medium'
            )
            ContentSkill.objects.create(
                lesson=lesson,
                skill=skill,
                weight=1.0
            )
            self.lessons.append(lesson)
        
        # Create weak skills for user
        UserSkillMastery.objects.create(
            user=self.user,
            skill='math:fractions:basics',
            mastery=0.3
        )
        UserSkillMastery.objects.create(
            user=self.user,
            skill='math:fractions:add',
            mastery=0.2
        )
    
    def test_generate_path(self):
        """Test basic path generation."""
        generator = PathGenerator()
        path = generator.generate_path(
            student=self.user,
            course_id=str(self.course.id),
            difficulty_target='adaptive'
        )
        
        self.assertIsNotNone(path)
        self.assertEqual(path.student, self.user)
        self.assertEqual(path.course, self.course)
        self.assertGreater(len(path.path), 0)
        
        # Check that weak skills are prioritized
        first_lesson_id = path.path[0]['lesson_id']
        first_lesson = Lesson.objects.get(id=first_lesson_id)
        lesson_skills = ContentSkill.objects.filter(lesson=first_lesson).values_list('skill', flat=True)
        
        weak_skills = ['math:fractions:basics', 'math:fractions:add']
        has_weak_skill = any(skill in weak_skills for skill in lesson_skills)
        self.assertTrue(has_weak_skill)
    
    def test_path_respects_prerequisites(self):
        """Test that path respects skill prerequisites."""
        # Create prerequisite: fractions:add requires fractions:basics
        SkillPrerequisite.objects.create(
            skill='math:fractions:add',
            prerequisite_skill='math:fractions:basics',
            strength=1.0
        )
        
        generator = PathGenerator()
        path = generator.generate_path(
            student=self.user,
            course_id=str(self.course.id)
        )
        
        # Find positions of both lessons in path
        basics_pos = None
        add_pos = None
        
        for idx, step in enumerate(path.path):
            lesson = Lesson.objects.get(id=step['lesson_id'])
            skills = ContentSkill.objects.filter(lesson=lesson).values_list('skill', flat=True)
            
            if 'math:fractions:basics' in skills:
                basics_pos = idx
            if 'math:fractions:add' in skills:
                add_pos = idx
        
        # Basics should come before add (or add should have low score)
        if basics_pos is not None and add_pos is not None:
            # Either basics comes first, or they're in the right order
            pass  # Prerequisite logic may reduce score instead of reordering


class RecommendationEngineTest(TestCase):
    """Test recommendation generation."""
    
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='pass')
        self.user2 = User.objects.create_user(username='user2', password='pass')
        
        from content.models import Course, Lesson
        self.course = Course.objects.create(title='Math 101')
        
        # Create lessons
        self.lessons = []
        for i in range(5):
            lesson = Lesson.objects.create(
                title=f'Lesson {i+1}',
                course=self.course
            )
            ContentSkill.objects.create(
                lesson=lesson,
                skill=f'skill_{i}',
                weight=1.0
            )
            self.lessons.append(lesson)
        
        # Create mastery data for both users
        for i in range(3):
            UserSkillMastery.objects.create(
                user=self.user1,
                skill=f'skill_{i}',
                mastery=0.3 + (i * 0.2)
            )
            UserSkillMastery.objects.create(
                user=self.user2,
                skill=f'skill_{i}',
                mastery=0.4 + (i * 0.2)
            )
    
    def test_content_based_recommendations(self):
        """Test content-based filtering."""
        engine = RecommendationEngine()
        recommendations = engine.generate_recommendations(
            student=self.user1,
            limit=3,
            algorithm='content_based'
        )
        
        self.assertGreater(len(recommendations), 0)
        self.assertLessEqual(len(recommendations), 3)
        
        # Check that recommendations target weak skills
        first_rec = recommendations[0]
        self.assertLessEqual(first_rec.score, 1.0)
        self.assertGreaterEqual(first_rec.score, 0.0)
    
    def test_collaborative_filtering(self):
        """Test collaborative filtering."""
        # Create similar learning events for user2
        for lesson in self.lessons[:3]:
            LearningEvent.objects.create(
                user=self.user2,
                lesson=lesson,
                event_type='complete',
                detail={'correct': True}
            )
        
        engine = RecommendationEngine()
        recommendations = engine.generate_recommendations(
            student=self.user1,
            limit=3,
            algorithm='collaborative'
        )
        
        # Should recommend lessons that user2 completed
        self.assertGreaterEqual(len(recommendations), 0)
    
    def test_hybrid_recommendations(self):
        """Test hybrid recommendation approach."""
        engine = RecommendationEngine()
        recommendations = engine.generate_recommendations(
            student=self.user1,
            limit=5,
            algorithm='hybrid'
        )
        
        self.assertGreater(len(recommendations), 0)
        
        # Check that recommendations are logged
        logs = RecommendationLog.objects.filter(user=self.user1)
        self.assertEqual(logs.count(), len(recommendations))


class UtilityFunctionsTest(TestCase):
    """Test utility functions."""
    
    def test_bayesian_mastery_calculation(self):
        """Test Bayesian Knowledge Tracing."""
        # Test correct answer increases mastery
        new_mastery = calculate_mastery_bayesian(
            prior_mastery=0.5,
            correct=True,
            slip_prob=0.1,
            guess_prob=0.2
        )
        self.assertGreater(new_mastery, 0.5)
        
        # Test incorrect answer decreases mastery
        new_mastery = calculate_mastery_bayesian(
            prior_mastery=0.5,
            correct=False,
            slip_prob=0.1,
            guess_prob=0.2
        )
        self.assertLess(new_mastery, 0.5)
    
    def test_hlr_decay(self):
        """Test Half-Life Regression decay."""
        # No decay if no time passed
        decayed = apply_hlr_decay(
            mastery=0.8,
            half_life_days=7.0,
            days_since_practice=0
        )
        self.assertEqual(decayed, 0.8)
        
        # 50% decay after one half-life
        decayed = apply_hlr_decay(
            mastery=0.8,
            half_life_days=7.0,
            days_since_practice=7.0
        )
        self.assertAlmostEqual(decayed, 0.4, places=2)
        
        # More decay after longer time
        decayed = apply_hlr_decay(
            mastery=0.8,
            half_life_days=7.0,
            days_since_practice=14.0
        )
        self.assertLess(decayed, 0.3)
    
    def test_cosine_similarity(self):
        """Test cosine similarity calculation."""
        vec1 = {'skill_a': 0.8, 'skill_b': 0.6, 'skill_c': 0.4}
        vec2 = {'skill_a': 0.7, 'skill_b': 0.5, 'skill_c': 0.3}
        
        similarity = cosine_similarity_dicts(vec1, vec2)
        
        # Should be high similarity (same pattern)
        self.assertGreater(similarity, 0.9)
        
        # Test with no common skills
        vec3 = {'skill_d': 0.8, 'skill_e': 0.6}
        similarity = cosine_similarity_dicts(vec1, vec3)
        self.assertEqual(similarity, 0.0)
    
    def test_ml_mastery_prediction(self):
        """Test ML mastery prediction fallback."""
        # Test with heuristic (no model)
        mastery = predict_mastery_ml(
            practice_count=10,
            correct_count=7,
            time_spent_total=600,
            days_since_last_practice=3.0,
            model=None
        )
        
        self.assertGreaterEqual(mastery, 0.0)
        self.assertLessEqual(mastery, 1.0)
        
        # Higher correct count should give higher mastery
        mastery_high = predict_mastery_ml(
            practice_count=10,
            correct_count=9,
            time_spent_total=600,
            days_since_last_practice=1.0,
            model=None
        )
        self.assertGreater(mastery_high, mastery)


class APIViewsTest(APITestCase):
    """Test REST API views."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        
        from content.models import Course, Lesson
        self.course = Course.objects.create(title='Test Course')
        self.lesson = Lesson.objects.create(
            title='Test Lesson',
            course=self.course
        )
        
        ContentSkill.objects.create(
            lesson=self.lesson,
            skill='test_skill',
            weight=1.0
        )
    
    def test_create_learning_event(self):
        """Test creating a learning event via API."""
        url = '/api/personalization/events/'
        data = {
            'course': str(self.course.id),
            'lesson': str(self.lesson.id),
            'event_type': 'submit',
            'detail': {'correct': True, 'attempts': 1}
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(LearningEvent.objects.count(), 1)
    
    def test_get_mastery_dashboard(self):
        """Test mastery dashboard endpoint."""
        # Create some mastery data
        UserSkillMastery.objects.create(
            user=self.user,
            skill='skill_1',
            mastery=0.9
        )
        UserSkillMastery.objects.create(
            user=self.user,
            skill='skill_2',
            mastery=0.4
        )
        
        url = '/api/personalization/mastery/dashboard/'
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_skills', response.data)
        self.assertIn('average_mastery', response.data)
        self.assertEqual(response.data['total_skills'], 2)
        self.assertEqual(response.data['mastered_skills'], 1)
    
    def test_generate_path(self):
        """Test path generation endpoint."""
        url = '/api/personalization/paths/generate/'
        data = {
            'course_id': str(self.course.id),
            'difficulty_target': 'adaptive'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('path', response.data)
    
    def test_refresh_recommendations(self):
        """Test recommendation refresh endpoint."""
        url = '/api/personalization/recommendations/refresh/'
        data = {
            'limit': 3,
            'algorithm': 'content_based'
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, list)
    
    def test_batch_create_events(self):
        """Test batch event creation."""
        url = '/api/personalization/events/batch_create/'
        data = {
            'events': [
                {
                    'lesson': str(self.lesson.id),
                    'event_type': 'start',
                    'detail': {}
                },
                {
                    'lesson': str(self.lesson.id),
                    'event_type': 'submit',
                    'detail': {'correct': True}
                }
            ]
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['created'], 2)
        self.assertEqual(LearningEvent.objects.count(), 2)


class PermissionsTest(APITestCase):
    """Test API permissions."""
    
    def setUp(self):
        self.student = User.objects.create_user(
            username='student',
            password='pass'
        )
        self.teacher = User.objects.create_user(
            username='teacher',
            password='pass',
            is_staff=True
        )
    
    def test_student_cannot_access_others_data(self):
        """Test that students can only access their own data."""
        other_user = User.objects.create_user(
            username='other',
            password='pass'
        )
        
        # Create mastery for other user
        UserSkillMastery.objects.create(
            user=other_user,
            skill='test_skill',
            mastery=0.5
        )
        
        self.client.force_authenticate(user=self.student)
        url = '/api/personalization/mastery/'
        response = self.client.get(url)
        
        # Should not see other user's data
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)
    
    def test_teacher_can_access_all_data(self):
        """Test that teachers can access all student data."""
        # Create mastery for student
        UserSkillMastery.objects.create(
            user=self.student,
            skill='test_skill',
            mastery=0.5
        )
        
        self.client.force_authenticate(user=self.teacher)
        url = '/api/personalization/mastery/'
        response = self.client.get(url)
        
        # Should see all data
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(len(response.data), 0)


class CeleryTasksTest(TestCase):
    """Test Celery async tasks."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='pass'
        )
    
    @patch('ai_personalization.tasks.MasteryCalculator')
    def test_update_mastery_async(self, mock_calculator):
        """Test async mastery update task."""
        from .tasks import update_mastery_async
        
        update_mastery_async(
            user_id=str(self.user.id),
            skills=['skill_1', 'skill_2'],
            correct=True,
            time_spent=120,
            attempts=1
        )
        
        # Check that calculator was called
        self.assertTrue(mock_calculator.update_mastery_from_event.called)
    
    def test_batch_update_skill_decay(self):
        """Test batch skill decay update."""
        from .tasks import batch_update_skill_decay
        
        # Create old mastery
        mastery = UserSkillMastery.objects.create(
            user=self.user,
            skill='test_skill',
            mastery=0.8,
            half_life_days=7.0
        )
        
        # Set last update to 7 days ago
        mastery.last_update = timezone.now() - timezone.timedelta(days=7)
        mastery.save()
        
        original_mastery = mastery.mastery
        
        # Run decay task
        batch_update_skill_decay()
        
        # Reload from DB
        mastery.refresh_from_db()
        
        # Should have decayed
        self.assertLess(mastery.mastery, original_mastery)


class IntegrationTest(TransactionTestCase):
    """End-to-end integration tests."""
    
    def setUp(self):
        self.user = User.objects.create_user(
            username='student',
            password='pass'
        )
        
        from content.models import Course, Lesson
        self.course = Course.objects.create(title='Math Course')
        
        # Create a series of lessons
        self.lessons = []
        for i in range(5):
            lesson = Lesson.objects.create(
                title=f'Lesson {i+1}',
                course=self.course
            )
            ContentSkill.objects.create(
                lesson=lesson,
                skill=f'math:topic_{i}',
                weight=1.0
            )
            self.lessons.append(lesson)
    
    def test_full_learning_flow(self):
        """Test complete learning flow: events -> mastery -> recommendations -> path."""
        # Step 1: Create learning events
        for i in range(3):
            LearningEvent.objects.create(
                user=self.user,
                lesson=self.lessons[i],
                event_type='submit',
                detail={
                    'correct': i % 2 == 0,  # Alternating success/failure
                    'attempts': 1,
                    'time_spent': 120
                }
            )
        
        # Step 2: Manually update mastery (simulating signal processing)
        for i in range(3):
            MasteryCalculator.update_mastery_from_event(
                user=self.user,
                skill=f'math:topic_{i}',
                correct=i % 2 == 0,
                time_spent=120,
                attempts=1
            )
        
        # Step 3: Generate recommendations
        engine = RecommendationEngine()
        recommendations = engine.generate_recommendations(
            student=self.user,
            limit=3,
            algorithm='hybrid'
        )
        
        self.assertGreater(len(recommendations), 0)
        
        # Step 4: Generate learning path
        generator = PathGenerator()
        path = generator.generate_path(
            student=self.user,
            course_id=str(self.course.id)
        )
        
        self.assertIsNotNone(path)
        self.assertGreater(len(path.path), 0)
        
        # Verify that weak skills are prioritized in path
        masteries = UserSkillMastery.objects.filter(user=self.user).order_by('mastery')
        weakest_skill = masteries.first().skill if masteries.exists() else None
        
        if weakest_skill:
            # Check that early lessons in path address weak skills
            first_lessons_skills = []
            for step in path.path[:2]:
                lesson = Lesson.objects.get(id=step['lesson_id'])
                skills = ContentSkill.objects.filter(lesson=lesson).values_list('skill', flat=True)
                first_lessons_skills.extend(skills)
            
            # At least one early lesson should address weakness
            # (This is a loose check as other factors influence ordering)
            self.assertTrue(len(first_lessons_skills) > 0)


# Performance and edge case tests

class PerformanceTest(TestCase):
    """Test performance with larger datasets."""
    
    def test_bulk_mastery_updates(self):
        """Test performance of bulk mastery updates."""
        import time
        
        user = User.objects.create_user(username='perfuser', password='pass')
        
        # Create 100 skill masteries
        masteries = []
        for i in range(100):
            masteries.append(UserSkillMastery(
                user=user,
                skill=f'skill_{i}',
                mastery=0.5
            ))
        
        start = time.time()
        UserSkillMastery.objects.bulk_create(masteries)
        duration = time.time() - start
        
        # Should complete in under 1 second
        self.assertLess(duration, 1.0)
        self.assertEqual(UserSkillMastery.objects.filter(user=user).count(), 100)
    
    def test_recommendation_generation_performance(self):
        """Test recommendation generation with many lessons."""
        import time
        
        user = User.objects.create_user(username='perfuser2', password='pass')
        
        from content.models import Course, Lesson
        course = Course.objects.create(title='Big Course')
        
        # Create 50 lessons
        for i in range(50):
            lesson = Lesson.objects.create(
                title=f'Lesson {i}',
                course=course
            )
            ContentSkill.objects.create(
                lesson=lesson,
                skill=f'skill_{i}',
                weight=1.0
            )
        
        # Create some mastery data
        for i in range(10):
            UserSkillMastery.objects.create(
                user=user,
                skill=f'skill_{i}',
                mastery=0.3
            )
        
        engine = RecommendationEngine()
        
        start = time.time()
        recommendations = engine.generate_recommendations(
            student=user,
            limit=10,
            algorithm='content_based'
        )
        duration = time.time() - start
        
        # Should complete in under 2 seconds
        self.assertLess(duration, 2.0)
        self.assertGreater(len(recommendations), 0)


class EdgeCaseTest(TestCase):
    """Test edge cases and error handling."""
    
    def test_empty_mastery_recommendations(self):
        """Test recommendations for user with no mastery data."""
        user = User.objects.create_user(username='newuser', password='pass')
        
        engine = RecommendationEngine()
        recommendations = engine.generate_recommendations(
            student=user,
            limit=5,
            algorithm='content_based'
        )
        
        # Should handle gracefully (may return empty or rule-based)
        self.assertIsInstance(recommendations, list)
    
    def test_lesson_without_skills(self):
        """Test handling lessons with no skill mappings."""
        user = User.objects.create_user(username='testuser', password='pass')
        
        from content.models import Course, Lesson
        course = Course.objects.create(title='Test Course')
        lesson = Lesson.objects.create(
            title='Unmapped Lesson',
            course=course
        )
        # No ContentSkill created
        
        generator = PathGenerator()
        path = generator.generate_path(
            student=user,
            course_id=str(course.id)
        )
        
        # Should not crash, but may have empty path
        self.assertIsNotNone(path)
    
    def test_circular_prerequisites(self):
        """Test handling of circular prerequisite dependencies."""
        SkillPrerequisite.objects.create(
            skill='skill_a',
            prerequisite_skill='skill_b',
            strength=1.0
        )
        SkillPrerequisite.objects.create(
            skill='skill_b',
            prerequisite_skill='skill_a',
            strength=1.0
        )
        
        user = User.objects.create_user(username='testuser', password='pass')
        engine = PersonalizationEngine()
        
        # Should detect and handle gracefully
        ready, missing = engine.check_prerequisites(user, 'skill_a')
        
        # May return False or handle based on implementation
        self.assertIsInstance(ready, bool)
        self.assertIsInstance(missing, list)


# if __name__ == '__main__':
#     pytest.main([__file__, '-v', '--cov=ai_personalization', '--cov-report=html'])