# ai_personalization/management/commands/populate_personalization_data.py
"""
Django management command to populate database with sample personalization data.
Usage: python manage.py populate_personalization_data
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from content.models import Course, Lesson, Module
from ai_personalization.models import (
    UserSkillMastery, ContentSkill, LearningEvent,
    SkillPrerequisite, PersonalizationRule, UserProfile
)
import random
import uuid

User = get_user_model()


class Command(BaseCommand):
    help = 'Populate database with sample personalization data for testing'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--users',
            type=int,
            default=100,
            help='Number of users to create'
        )
        parser.add_argument(
            '--courses',
            type=int,
            default=10,
            help='Number of courses to create'
        )
        parser.add_argument(
            '--lessons-per-course',
            type=int,
            default=5,
            help='Number of lessons per course'
        )
    
    def handle(self, *args, **options):
        num_users = options['users']
        num_courses = options['courses']
        lessons_per_course = options['lessons_per_course']
        
        self.stdout.write('Creating users...')
        users = self._create_users(num_users)
        
        self.stdout.write('Creating courses and lessons...')
        courses, lessons = self._create_courses_and_lessons(num_courses, lessons_per_course)
        
        self.stdout.write('Creating skill mappings...')
        skills = self._create_skill_mappings(lessons)
        
        self.stdout.write('Creating skill prerequisites...')
        self._create_prerequisites(skills)
        
        self.stdout.write('Creating user profiles...')
        self._create_user_profiles(users)
        
        self.stdout.write('Creating learning events...')
        self._create_learning_events(users, lessons)
        
        self.stdout.write('Creating skill masteries...')
        self._create_skill_masteries(users, skills)
        
        self.stdout.write('Creating personalization rules...')
        self._create_personalization_rules()
        
        self.stdout.write(self.style.SUCCESS(
            f'Successfully populated database:\n'
            f'  - {num_users} users\n'
            f'  - {num_courses} courses\n'
            f'  - {len(lessons)} lessons\n'
            f'  - {len(skills)} skills'
        ))
    
    def _create_users(self, count):
        """Create sample users."""
        users = []
        for i in range(count):
            user, created = User.objects.get_or_create(
                username=f'student_{i}',
                defaults={
                    'email': f'student_test_{i}@example.com',
                }
            )
            
            if created:
                user.set_password('password123')
                user.save()
            users.append(user)
        return users
    
    def _create_courses_and_lessons(self, num_courses, lessons_per_course):
        """Create sample courses and lessons."""
        subjects = ['Math', 'Science', 'English', 'History', 'Geography']
        courses = []
        all_lessons = []
        
        for i in range(num_courses):
            subject = random.choice(subjects)
            course, _ = Course.objects.get_or_create(
                title=f'{subject} Grade {(i % 5) + 1}',
                defaults={
                    'description': f'Introduction to {subject} for primary students',
                    'grade': (i % 5) + 1
                }
            )
            courses.append(course)

            # Create lessons for this course
            for j in range(lessons_per_course):
                module, _ = Module.objects.get_or_create(course=course)
                lesson, _ = Lesson.objects.get_or_create(
                    title=f'{course.title} - Lesson {j+1}',
                    module=module,
                    # defaults={
                    #     'description': f'Lesson {j+1} content',
                    #     'difficulty': random.choice(['easy', 'medium', 'hard']),
                    #     'estimated_time_minutes': random.randint(15, 45)
                    # }
                )
                all_lessons.append(lesson)
        
        return courses, all_lessons
    
    def _create_skill_mappings(self, lessons):
        """Create skill mappings for lessons."""
        skill_categories = {
            'math': ['counting', 'addition', 'subtraction', 'multiplication', 'fractions', 'decimals'],
            'science': ['plants', 'animals', 'weather', 'matter', 'energy'],
            'english': ['reading', 'writing', 'grammar', 'vocabulary', 'spelling'],
        }
        
        skills = set()
        
        for lesson in lessons:
            # Determine subject from course title
            subject = 'math'
            if 'Science' in lesson.module.course.title: 
                subject = 'science'
            elif 'English' in lesson.module.course.title:
                subject = 'english'
            
            # Assign 1-3 skills per lesson
            num_skills = random.randint(1, 3)
            categories = skill_categories.get(subject, skill_categories['math'])
            
            for _ in range(num_skills):
                category = random.choice(categories)
                level = random.choice(['basics', 'intermediate', 'advanced'])
                skill = f'{subject}:{category}:{level}'
                skills.add(skill)
                
                ContentSkill.objects.get_or_create(
                    lesson=lesson,
                    skill=skill,
                    defaults={'weight': random.uniform(0.7, 1.0)}
                )
        
        return list(skills)
    
    def _create_prerequisites(self, skills):
        """Create skill prerequisite relationships."""
        # Group skills by category
        skill_groups = {}
        for skill in skills:
            parts = skill.split(':')
            if len(parts) >= 2:
                key = f'{parts[0]}:{parts[1]}'
                if key not in skill_groups:
                    skill_groups[key] = []
                skill_groups[key].append(skill)
        
        # Create prerequisites within groups
        for group_skills in skill_groups.values():
            group_skills.sort()  # basics < intermediate < advanced
            
            for i in range(1, len(group_skills)):
                # Advanced requires intermediate, intermediate requires basics
                SkillPrerequisite.objects.get_or_create(
                    skill=group_skills[i],
                    prerequisite_skill=group_skills[i-1],
                    defaults={'strength': random.uniform(0.7, 1.0)}
                )
    
    def _create_user_profiles(self, users):
        """Create user profiles."""
        age_groups = ['6-8', '9-11', '12-14']
        learning_styles = ['visual', 'auditory', 'kinesthetic', 'mixed']
        difficulties = ['easy', 'medium', 'hard', 'adaptive']
        
        for user in users:
            UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'age_group': random.choice(age_groups),
                    'learning_style': random.choice(learning_styles),
                    'difficulty_preference': random.choice(difficulties)
                }
            )
    
    def _create_learning_events(self, users, lessons):
        """Create synthetic learning events."""
        event_types = ['start', 'submit', 'complete', 'hint', 'skip']
        
        # Create 10-50 events per user
        for user in random.sample(users, min(50, len(users))):
            num_events = random.randint(10, 50)
            user_lessons = random.sample(lessons, min(10, len(lessons)))
            
            for _ in range(num_events):
                lesson = random.choice(user_lessons)
                event_type = random.choice(event_types)
                
                # Generate realistic event details
                detail = {}
                if event_type == 'submit':
                    detail['correct'] = random.random() > 0.3  # 70% success rate
                    detail['attempts'] = random.randint(1, 3)
                    detail['time_spent'] = random.randint(30, 300)
                elif event_type == 'complete':
                    detail['correct'] = True
                    detail['time_spent'] = random.randint(60, 600)
                
                LearningEvent.objects.create(
                    user=user,
                    course=lesson.module.course,
                    lesson=lesson,
                    event_type=event_type,
                    detail=detail,
                    timestamp=timezone.now() - timezone.timedelta(
                        days=random.randint(0, 30)
                    ),
                    session_id=uuid.uuid4()
                )
    
    def _create_skill_masteries(self, users, skills):
        """Create skill mastery records based on events."""
        for user in random.sample(users, min(50, len(users))):
            # Get user's events
            events = LearningEvent.objects.filter(user=user)
            
            if not events.exists():
                continue
            
            # Get skills from lessons in events
            lesson_ids = events.values_list('lesson_id', flat=True).distinct()
            content_skills = ContentSkill.objects.filter(
                lesson_id__in=lesson_ids
            ).values_list('skill', flat=True).distinct()
            
            for skill in content_skills:
                # Calculate mastery based on performance
                skill_events = events.filter(
                    lesson__content_skills__skill=skill
                )
                
                total = skill_events.count()
                if total == 0:
                    continue
                
                correct = skill_events.filter(
                    detail__correct=True
                ).count()
                
                mastery = min(1.0, (correct / total) * random.uniform(0.8, 1.2))
                
                UserSkillMastery.objects.get_or_create(
                    user=user,
                    skill=skill,
                    defaults={
                        'mastery': mastery,
                        'practice_count': total,
                        'correct_count': correct,
                        'half_life_days': random.uniform(5.0, 15.0)
                    }
                )
    
    def _create_personalization_rules(self):
        """Create sample personalization rules."""
        rules = [
            {
                'name': 'beginner_boost',
                'description': 'Recommend easy lessons for beginners',
                'condition': {'event_count_below': 10},
                'action': {'difficulty_filter': 'easy', 'boost_score': 0.2},
                'priority': 100
            },
            {
                'name': 'weak_skill_focus',
                'description': 'Focus on weakest skills',
                'condition': {'mastery_below': 0.4},
                'action': {'focus_weak_skills': True, 'limit': 5},
                'priority': 90
            },
            {
                'name': 'prerequisite_check',
                'description': 'Ensure prerequisites are met',
                'condition': {'skill_missing': 'basics'},
                'action': {'enforce_prerequisites': True},
                'priority': 95
            },
        ]
        
        for rule_data in rules:
            PersonalizationRule.objects.get_or_create(
                name=rule_data['name'],
                defaults=rule_data
            )