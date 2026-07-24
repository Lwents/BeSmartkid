# ai_personalization/ai_engines.py
"""
Core AI engines for personalization: path generation, recommendations, mastery calculation.
Implements hybrid approach: rule-based + ML (scikit-learn) + optional OpenAI integration.
"""
from typing import List, Dict, Optional, Tuple
from django.db.models import Q, Avg, Count
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.core.cache import cache
import numpy as np
import logging

from .models import (
    LearningPath, Recommendation, UserSkillMastery,
    ContentSkill, SkillPrerequisite, PersonalizationRule,
    LearningEvent, RecommendationLog, UserProfile
)
from .utils import (
    calculate_mastery_bayesian, predict_mastery_ml,
    compute_similarity_matrix, apply_hlr_decay
)

User = get_user_model()
logger = logging.getLogger(__name__)


class PersonalizationEngine:
    """
    Base engine for AI personalization.
    Provides common utilities for path generation and recommendations.
    """
    
    def __init__(self):
        self.cache_timeout = 300  # 5 minutes
    
    def get_user_weak_skills(self, user, threshold: float = 0.5, limit: int = 10) -> List[str]:
        """Get user's weakest skills below mastery threshold."""
        weak_skills = UserSkillMastery.objects.filter(
            user=user,
            mastery__lt=threshold
        ).order_by('mastery').values_list('skill', flat=True)[:limit]
        
        return list(weak_skills)
    
    def get_user_strong_skills(self, user, threshold: float = 0.7) -> List[str]:
        """Get user's strong skills above mastery threshold."""
        strong_skills = UserSkillMastery.objects.filter(
            user=user,
            mastery__gte=threshold
        ).values_list('skill', flat=True)
        
        return list(strong_skills)
    
    def check_prerequisites(self, user, skill: str) -> Tuple[bool, List[str]]:
        """
        Check if user has met prerequisites for a skill.
        Returns (ready, missing_prerequisites)
        """
        prerequisites = SkillPrerequisite.objects.filter(skill=skill)
        
        if not prerequisites.exists():
            return True, []
        
        missing = []
        for prereq in prerequisites:
            mastery = UserSkillMastery.objects.filter(
                user=user,
                skill=prereq.prerequisite_skill
            ).first()
            
            # Require mastery above threshold based on prerequisite strength
            required_mastery = 0.5 + (0.3 * prereq.strength)
            
            if not mastery or mastery.mastery < required_mastery:
                missing.append(prereq.prerequisite_skill)
        
        return len(missing) == 0, missing
    
    def apply_personalization_rules(self, user, context: Dict) -> Dict:
        """
        Apply rule-based personalization for cold-start scenarios.
        Returns dict with recommended actions.
        """
        rules = PersonalizationRule.objects.filter(
            is_active=True
        ).order_by('-priority')
        
        actions = {}
        
        for rule in rules:
            if self._evaluate_rule_condition(user, rule.condition, context):
                actions[rule.name] = rule.action
                logger.info(f"Applied rule '{rule.name}' for user {user.id}")
        
        return actions
    
    def _evaluate_rule_condition(self, user, condition: Dict, context: Dict) -> bool:
        """Evaluate if a rule condition is met."""
        try:
            # Simple rule evaluation (extend as needed)
            if 'mastery_below' in condition:
                avg_mastery = UserSkillMastery.objects.filter(
                    user=user
                ).aggregate(Avg('mastery'))['mastery__avg'] or 0.0
                
                if avg_mastery >= condition['mastery_below']:
                    return False
            
            if 'skill_missing' in condition:
                skill = condition['skill_missing']
                mastery = UserSkillMastery.objects.filter(
                    user=user,
                    skill=skill
                ).first()
                
                if mastery and mastery.mastery > 0.3:
                    return False
            
            if 'event_count_below' in condition:
                event_count = LearningEvent.objects.filter(
                    user=user
                ).count()
                
                if event_count >= condition['event_count_below']:
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Rule condition evaluation failed: {str(e)}")
            return False


class PathGenerator(PersonalizationEngine):
    """
    Generates personalized learning paths using skill mastery and prerequisites.
    Inspired by Khan Academy's mastery-based progression.
    """
    
    def generate_path(
        self,
        student,
        course_id: str,
        preferences: Dict = None,
        focus_areas: List[str] = None,
        difficulty_target: str = 'adaptive'
    ) -> LearningPath:
        """
        Generate a personalized learning path for a student.
        
        Algorithm:
        1. Get all lessons in course
        2. Filter by prerequisites (only include ready lessons)
        3. Score lessons based on weak skills, difficulty, and preferences
        4. Order lessons by score and dependency graph
        5. Create LearningPath with ordered lesson list
        """
        from content.models import Course, Lesson
        
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            raise ValueError(f"Course {course_id} not found")
        
        # Get all lessons in course
        lessons = Lesson.objects.filter(course=course).prefetch_related('content_skills')
        
        # Get user's weak skills for prioritization
        weak_skills = self.get_user_weak_skills(student)
        strong_skills = self.get_user_strong_skills(student)
        
        # Score each lesson
        scored_lessons = []
        for lesson in lessons:
            score = self._score_lesson_for_path(
                lesson, student, weak_skills, strong_skills,
                difficulty_target, focus_areas or []
            )
            
            if score > 0:  # Only include lessons with positive score
                scored_lessons.append({
                    'lesson_id': str(lesson.id),
                    'lesson_title': lesson.title,
                    'score': score,
                    'difficulty': getattr(lesson, 'difficulty', 'medium'),
                    'estimated_time': getattr(lesson, 'estimated_time_minutes', 30)
                })
        
        # Sort by score (highest first)
        scored_lessons.sort(key=lambda x: x['score'], reverse=True)
        
        # Add order field
        path_data = []
        for idx, lesson_data in enumerate(scored_lessons, start=1):
            lesson_data['order'] = idx
            path_data.append(lesson_data)
        
        # Create or update learning path
        learning_path, created = LearningPath.objects.update_or_create(
            student=student,
            course=course,
            defaults={
                'path': path_data,
                'ai_model': 'rule-based-v1',
                'metadata': {
                    'weak_skills': weak_skills,
                    'difficulty_target': difficulty_target,
                    'focus_areas': focus_areas or [],
                    'generated_reason': 'skill_mastery_based'
                }
            }
        )
        
        logger.info(
            f"Generated path for {student.username} in {course.title}: "
            f"{len(path_data)} lessons"
        )
        
        return learning_path
    
    def _score_lesson_for_path(
        self,
        lesson,
        student,
        weak_skills: List[str],
        strong_skills: List[str],
        difficulty_target: str,
        focus_areas: List[str]
    ) -> float:
        """
        Score a lesson for inclusion in learning path.
        Higher score = higher priority.
        """
        score = 0.0
        
        # Get skills taught in this lesson
        lesson_skills = ContentSkill.objects.filter(lesson=lesson)
        
        if not lesson_skills.exists():
            return 0.0  # Skip lessons with no skill mapping
        
        # 1. Weak skill coverage (highest weight)
        for content_skill in lesson_skills:
            if content_skill.skill in weak_skills:
                # Higher weight for weaker skills
                weak_rank = weak_skills.index(content_skill.skill)
                score += (5.0 - (weak_rank * 0.3)) * content_skill.weight
        
        # 2. Focus area match
        if focus_areas:
            for content_skill in lesson_skills:
                for focus in focus_areas:
                    if focus in content_skill.skill:
                        score += 3.0 * content_skill.weight
        
        # 3. Prerequisite readiness
        ready, missing = self.check_prerequisites(student, lesson_skills[0].skill)
        if not ready:
            score *= 0.1  # Heavily penalize if prerequisites not met
        
        # 4. Difficulty matching
        lesson_difficulty = getattr(lesson, 'difficulty', 'medium')
        difficulty_scores = {
            'easy': {'easy': 2.0, 'medium': 1.0, 'hard': 0.3, 'adaptive': 1.5},
            'medium': {'easy': 0.5, 'medium': 2.0, 'hard': 1.0, 'adaptive': 1.5},
            'hard': {'easy': 0.3, 'medium': 1.0, 'hard': 2.0, 'adaptive': 1.5},
        }
        
        if lesson_difficulty in difficulty_scores:
            score += difficulty_scores[lesson_difficulty].get(difficulty_target, 1.0)
        
        # 5. Avoid already mastered skills
        for content_skill in lesson_skills:
            if content_skill.skill in strong_skills:
                score *= 0.5  # Reduce priority for mastered content
        
        return max(0.0, score)
    
    def regenerate_path(self, existing_path: LearningPath) -> LearningPath:
        """Regenerate an existing path with updated mastery data."""
        return self.generate_path(
            student=existing_path.student,
            course_id=str(existing_path.course.id),
            preferences=existing_path.metadata.get('preferences', {}),
            focus_areas=existing_path.metadata.get('focus_areas', []),
            difficulty_target=existing_path.metadata.get('difficulty_target', 'adaptive')
        )


class RecommendationEngine(PersonalizationEngine):
    """
    Generates lesson recommendations using hybrid approach:
    - Content-based filtering (skill similarity)
    - Collaborative filtering (similar user patterns)
    - Rule-based fallback
    """
    
    def generate_recommendations(
        self,
        student,
        limit: int = 5,
        exclude_completed: bool = True,
        algorithm: str = 'hybrid'
    ) -> List[Recommendation]:
        """
        Generate personalized lesson recommendations.
        
        Args:
            student: User object
            limit: Number of recommendations to generate
            exclude_completed: Filter out completed lessons
            algorithm: 'hybrid', 'collaborative', 'content_based', 'rule_based'
        """
        # Check cache first
        cache_key = f"recommendations_fresh:{student.id}:{algorithm}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        # Get candidate lessons
        from content.models import Lesson
        lessons = Lesson.objects.prefetch_related('content_skills', 'module__course').all()
        
        if exclude_completed:
            # Filter out lessons with high completion rate
            completed_lesson_ids = LearningEvent.objects.filter(
                user=student,
                event_type='complete'
            ).values_list('lesson_id', flat=True).distinct()
            
            lessons = lessons.exclude(id__in=completed_lesson_ids)
        
        # Generate recommendations based on algorithm
        if algorithm == 'collaborative':
            recommendations = self._collaborative_filtering(student, lessons, limit)
        elif algorithm == 'content_based':
            recommendations = self._content_based_filtering(student, lessons, limit)
        elif algorithm == 'rule_based':
            recommendations = self._rule_based_recommendations(student, lessons, limit)
        else:  # hybrid
            recommendations = self._hybrid_recommendations(student, lessons, limit)
        
        # Delete old recommendations for this user
        Recommendation.objects.filter(
            student=student,
            generated_at__lt=timezone.now() - timezone.timedelta(days=7)
        ).delete()
        
        # Save new recommendations
        recommendation_objs = []
        for rec_data in recommendations:
            rec_obj = Recommendation.objects.create(
                student=student,
                recommended_lesson_id=rec_data['lesson_id'],
                score=rec_data['score'],
                reason=rec_data['reason']
            )
            recommendation_objs.append(rec_obj)
            
            # Log for analytics
            RecommendationLog.objects.create(
                user=student,
                lesson_id=rec_data['lesson_id'],
                score=rec_data['score'],
                reason=rec_data['reason'],
                source=algorithm
            )
        
        # Cache for 5 minutes
        cache.set(cache_key, recommendation_objs, 300)
        
        logger.info(
            f"Generated {len(recommendation_objs)} recommendations "
            f"for {student.username} using {algorithm}"
        )
        
        return recommendation_objs
    
    def _hybrid_recommendations(self, student, lessons, limit: int) -> List[Dict]:
        """Combine multiple recommendation strategies."""
        # Get recommendations from each method
        collaborative = self._collaborative_filtering(student, lessons, limit * 2)
        content_based = self._content_based_filtering(student, lessons, limit * 2)
        rule_based = self._rule_based_recommendations(student, lessons, limit * 2)
        
        # Combine and deduplicate
        all_recs = {}
        
        for rec in collaborative:
            lesson_id = rec['lesson_id']
            all_recs[lesson_id] = {
                **rec,
                'score': rec['score'] * 0.4,  # 40% weight
                'sources': ['collaborative']
            }
        
        for rec in content_based:
            lesson_id = rec['lesson_id']
            if lesson_id in all_recs:
                all_recs[lesson_id]['score'] += rec['score'] * 0.4  # 40% weight
                all_recs[lesson_id]['sources'].append('content_based')
            else:
                all_recs[lesson_id] = {
                    **rec,
                    'score': rec['score'] * 0.4,
                    'sources': ['content_based']
                }
        
        for rec in rule_based:
            lesson_id = rec['lesson_id']
            if lesson_id in all_recs:
                all_recs[lesson_id]['score'] += rec['score'] * 0.2  # 20% weight
                all_recs[lesson_id]['sources'].append('rule_based')
            else:
                all_recs[lesson_id] = {
                    **rec,
                    'score': rec['score'] * 0.2,
                    'sources': ['rule_based']
                }
        
        # Update reasons with source info
        for lesson_id, rec in all_recs.items():
            sources_str = ', '.join(rec['sources'])
            rec['reason'] = f"Hybrid recommendation (sources: {sources_str}). {rec['reason']}"
        
        # Sort by combined score
        sorted_recs = sorted(all_recs.values(), key=lambda x: x['score'], reverse=True)
        
        return sorted_recs[:limit]
    
    def _collaborative_filtering(self, student, lessons, limit: int) -> List[Dict]:
        """
        Recommend lessons based on similar users' learning patterns.
        Uses user-user similarity based on skill mastery vectors.
        """
        # Get student's mastery vector
        student_masteries = UserSkillMastery.objects.filter(user=student)
        student_skills = {m.skill: m.mastery for m in student_masteries}
        
        if not student_skills:
            return []  # Cold start - no mastery data yet
        
        # Find similar users
        similar_users = self._find_similar_users(student, student_skills, limit=10)
        
        if not similar_users:
            return []
        
        # Get lessons these similar users completed successfully
        similar_user_ids = [u['user_id'] for u in similar_users]
        
        successful_events = LearningEvent.objects.filter(
            user_id__in=similar_user_ids,
            event_type='complete',
            detail__correct=True
        ).values('lesson_id').annotate(
            completion_count=Count('id')
        ).order_by('-completion_count')
        
        recommendations = []
        for event_data in successful_events[:limit]:
            lesson_id = event_data['lesson_id']
            try:
                lesson = lessons.get(id=lesson_id)
                
                # Calculate score based on popularity among similar users
                popularity_score = min(1.0, event_data['completion_count'] / 10.0)
                
                recommendations.append({
                    'lesson_id': str(lesson.id),
                    'lesson_title': lesson.title,
                    'score': popularity_score,
                    'reason': f"Users similar to you found this helpful ({event_data['completion_count']} completions)"
                })
            except lessons.model.DoesNotExist:
                continue
        
        return recommendations
    
    def _find_similar_users(self, student, student_skills: Dict, limit: int = 10) -> List[Dict]:
        """Find users with similar skill mastery patterns."""
        # Get all users with skill mastery data
        all_masteries = UserSkillMastery.objects.exclude(
            user=student
        ).select_related('user')
        
        # Group by user
        user_skill_vectors = {}
        for mastery in all_masteries:
            if mastery.user_id not in user_skill_vectors:
                user_skill_vectors[mastery.user_id] = {}
            user_skill_vectors[mastery.user_id][mastery.skill] = mastery.mastery
        
        # Calculate cosine similarity
        similarities = []
        for user_id, other_skills in user_skill_vectors.items():
            similarity = self._cosine_similarity(student_skills, other_skills)
            if similarity > 0.5:  # Threshold for "similar"
                similarities.append({
                    'user_id': user_id,
                    'similarity': similarity
                })
        
        # Sort by similarity
        similarities.sort(key=lambda x: x['similarity'], reverse=True)
        
        return similarities[:limit]
    
    def _cosine_similarity(self, vec1: Dict, vec2: Dict) -> float:
        """Calculate cosine similarity between two skill vectors."""
        # Get common skills
        common_skills = set(vec1.keys()) & set(vec2.keys())
        
        if not common_skills:
            return 0.0
        
        # Calculate dot product and magnitudes
        dot_product = sum(vec1[skill] * vec2[skill] for skill in common_skills)
        mag1 = np.sqrt(sum(vec1[skill]**2 for skill in common_skills))
        mag2 = np.sqrt(sum(vec2[skill]**2 for skill in common_skills))
        
        if mag1 == 0 or mag2 == 0:
            return 0.0
        
        return dot_product / (mag1 * mag2)
    
    def _content_based_filtering(self, student, lessons, limit: int) -> List[Dict]:
        """Recommend lessons based on weak skills and content similarity."""
        weak_skills = self.get_user_weak_skills(student, threshold=0.6, limit=20)
        
        if not weak_skills:
            return []
        
        recommendations = []
        
        for lesson in lessons:
            lesson_skills = ContentSkill.objects.filter(lesson=lesson)
            
            # Calculate relevance score
            relevance = 0.0
            matching_skills = []
            
            for content_skill in lesson_skills:
                if content_skill.skill in weak_skills:
                    # Higher score for weaker skills
                    skill_rank = weak_skills.index(content_skill.skill)
                    skill_weight = (len(weak_skills) - skill_rank) / len(weak_skills)
                    relevance += skill_weight * content_skill.weight
                    matching_skills.append(content_skill.skill)
            
            if relevance > 0:
                # Check prerequisites
                ready, missing = self.check_prerequisites(student, lesson_skills[0].skill)
                
                if not ready:
                    relevance *= 0.2  # Penalize if not ready
                
                skill_list = ', '.join(matching_skills[:3])
                reason = f"Focuses on skills you're developing: {skill_list}"
                
                if not ready:
                    reason += f" (Tip: Complete prerequisites first: {', '.join(missing[:2])})"
                
                recommendations.append({
                    'lesson_id': str(lesson.id),
                    'lesson_title': lesson.title,
                    'score': min(1.0, relevance / 5.0),
                    'reason': reason
                })
        
        # Sort by score
        recommendations.sort(key=lambda x: x['score'], reverse=True)
        
        return recommendations[:limit]
    
    def _rule_based_recommendations(self, student, lessons, limit: int) -> List[Dict]:
        """Generate recommendations using predefined rules."""
        recommendations = []
        
        # Rule 1: Recommend next lessons in sequence
        latest_event = LearningEvent.objects.filter(
            user=student,
            event_type='complete'
        ).order_by('-timestamp').first()
        
        if latest_event and latest_event.lesson:
            # Get next lessons in the same course
            next_lessons = lessons.filter(
                module__course=latest_event.course
            ).exclude(id=latest_event.lesson_id)[:limit]
            
            for idx, lesson in enumerate(next_lessons):
                recommendations.append({
                    'lesson_id': str(lesson.id),
                    'lesson_title': lesson.title,
                    'score': 1.0 - (idx * 0.1),
                    'reason': 'Continue your learning journey in this course'
                })
        
        # Rule 2: Recommend popular lessons for beginners
        if LearningEvent.objects.filter(user=student).count() < 10:
            popular_lessons = LearningEvent.objects.filter(
                event_type='complete'
            ).values('lesson_id').annotate(
                count=Count('id')
            ).order_by('-count')[:limit]
            
            for event_data in popular_lessons:
                try:
                    lesson = lessons.get(id=event_data['lesson_id'])
                    recommendations.append({
                        'lesson_id': str(lesson.id),
                        'lesson_title': lesson.title,
                        'score': min(0.8, event_data['count'] / 100.0),
                        'reason': f'Popular among students ({event_data["count"]} completions)'
                    })
                except lessons.model.DoesNotExist:
                    continue
        
        return recommendations[:limit]


class MasteryCalculator:
    """
    Calculate and update skill mastery using Bayesian Knowledge Tracing
    and Half-Life Regression (inspired by Duolingo).
    """
    
    @staticmethod
    def update_mastery_from_event(
        user,
        skill: str,
        correct: bool,
        time_spent: float = 0,
        attempts: int = 1
    ) -> float:
        """
        Update mastery for a skill based on learning event.
        Returns new mastery value.
        """
        mastery_obj, created = UserSkillMastery.objects.get_or_create(
            user=user,
            skill=skill,
            defaults={'mastery': 0.0}
        )
        
        # Use Half-Life Regression inspired by Duolingo
        mastery_obj.update_from_event(correct, time_spent)
        
        return mastery_obj.mastery
    
    @staticmethod
    def batch_update_masteries(
        user,
        skill_observations: List[Dict]
    ):
        """
        Batch update multiple skills.
        skill_observations: [{'skill': str, 'correct': bool, 'time_spent': float}, ...]
        """
        for observation in skill_observations:
            MasteryCalculator.update_mastery_from_event(
                user=user,
                skill=observation['skill'],
                correct=observation['correct'],
                time_spent=observation.get('time_spent', 0),
                attempts=observation.get('attempts', 1)
            )