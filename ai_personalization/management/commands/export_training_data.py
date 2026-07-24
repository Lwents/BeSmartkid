# ai_personalization/management/commands/export_training_data.py
"""
Export training data for ML model development.
Usage: python manage.py export_training_data --output data/training.csv
"""
from django.core.management.base import BaseCommand
from ai_personalization.models import UserSkillMastery, LearningEvent
import csv
import json


class Command(BaseCommand):
    help = 'Export training data for ML model development'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--output',
            type=str,
            default='training_data.csv',
            help='Output file path'
        )
        parser.add_argument(
            '--format',
            type=str,
            choices=['csv', 'json'],
            default='csv',
            help='Output format'
        )
    
    def handle(self, *args, **options):
        output_path = options['output']
        output_format = options['format']
        
        self.stdout.write('Collecting training data...')
        
        # Collect features and labels
        training_data = []
        
        masteries = UserSkillMastery.objects.filter(
            practice_count__gte=3
        ).select_related('user')
        
        for mastery in masteries:
            # Get events for this user-skill
            events = LearningEvent.objects.filter(
                user=mastery.user,
                lesson__content_skills__skill=mastery.skill
            ).order_by('timestamp')
            
            if events.count() < 2:
                continue
            
            # Calculate features
            total_time = sum(e.detail.get('time_spent', 0) for e in events)
            hint_count = events.filter(event_type='hint').count()
            skip_count = events.filter(event_type='skip').count()
            
            days_since_start = (events.last().timestamp - events.first().timestamp).days
            
            record = {
                'user_id': str(mastery.user.id),
                'skill': mastery.skill,
                'practice_count': mastery.practice_count,
                'correct_count': mastery.correct_count,
                'incorrect_count': mastery.practice_count - mastery.correct_count,
                'time_spent_total': total_time,
                'hint_count': hint_count,
                'skip_count': skip_count,
                'days_since_start': days_since_start,
                'session_count': events.values('session_id').distinct().count(),
                'mastery': mastery.mastery  # Label
            }
            
            training_data.append(record)
        
        # Export data
        if output_format == 'csv':
            self._export_csv(training_data, output_path)
        else:
            self._export_json(training_data, output_path)
        
        self.stdout.write(self.style.SUCCESS(
            f'Exported {len(training_data)} training records to {output_path}'
        ))
    
    def _export_csv(self, data, path):
        """Export data as CSV."""
        if not data:
            return
        
        with open(path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
    
    def _export_json(self, data, path):
        """Export data as JSON."""
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)