# ai_personalization/management/commands/train_ml_model.py
"""
Train ML model for mastery prediction.
Usage: python manage.py train_ml_model --input data/training.csv
"""
from django.core.management.base import BaseCommand
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import mean_absolute_error, r2_score
import pandas as pd
import pickle
import os


class Command(BaseCommand):
    help = 'Train ML model for mastery prediction'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--input',
            type=str,
            default='training_data.csv',
            help='Input training data file'
        )
        parser.add_argument(
            '--output',
            type=str,
            default='models/mastery_predictor.pkl',
            help='Output model file'
        )
    
    def handle(self, *args, **options):
        input_path = options['input']
        output_path = options['output']
        
        self.stdout.write(f'Loading training data from {input_path}...')
        
        # Load data
        df = pd.read_csv(input_path)
        
        self.stdout.write(f'Loaded {len(df)} records')
        
        # Prepare features and labels
        feature_columns = [
            'practice_count', 'correct_count', 'incorrect_count',
            'time_spent_total', 'hint_count', 'skip_count',
            'days_since_start', 'session_count'
        ]
        
        X = df[feature_columns].values
        y = df['mastery'].values
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42
        )
        
        self.stdout.write('Training Random Forest model...')
        
        # Train model
        model = RandomForestRegressor(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            random_state=42,
            n_jobs=-1
        )
        
        model.fit(X_train, y_train)
        
        # Evaluate
        y_pred_train = model.predict(X_train)
        y_pred_test = model.predict(X_test)
        
        train_mae = mean_absolute_error(y_train, y_pred_train)
        test_mae = mean_absolute_error(y_test, y_pred_test)
        train_r2 = r2_score(y_train, y_pred_train)
        test_r2 = r2_score(y_test, y_pred_test)
        
        self.stdout.write(f'\nModel Performance:')
        self.stdout.write(f'  Train MAE: {train_mae:.4f}')
        self.stdout.write(f'  Test MAE:  {test_mae:.4f}')
        self.stdout.write(f'  Train R²:  {train_r2:.4f}')
        self.stdout.write(f'  Test R²:   {test_r2:.4f}')
        
        # Cross-validation
        cv_scores = cross_val_score(
            model, X, y, cv=5, scoring='neg_mean_absolute_error'
        )
        self.stdout.write(f'  CV MAE:    {-cv_scores.mean():.4f} (+/- {cv_scores.std():.4f})')
        
        # Feature importance
        self.stdout.write(f'\nFeature Importance:')
        for feature, importance in zip(feature_columns, model.feature_importances_):
            self.stdout.write(f'  {feature:20s}: {importance:.4f}')
        
        # Save model
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'wb') as f:
            pickle.dump(model, f)
        
        self.stdout.write(self.style.SUCCESS(
            f'\nModel saved to {output_path}'
        ))