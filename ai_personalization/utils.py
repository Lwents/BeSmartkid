# ai_personalization/utils.py
"""
Utility functions for AI personalization: mastery calculation, ML predictions, similarity metrics.
"""
import numpy as np
from typing import List, Dict, Tuple
from scipy.stats import beta
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
import logging

logger = logging.getLogger(__name__)


def calculate_mastery_bayesian(
    prior_mastery: float,
    correct: bool,
    slip_prob: float = 0.1,
    guess_prob: float = 0.2
) -> float:
    """
    Bayesian Knowledge Tracing (BKT) update.
    
    Args:
        prior_mastery: Current mastery estimate (0-1)
        correct: Whether answer was correct
        slip_prob: P(incorrect | mastered) - probability of slip
        guess_prob: P(correct | not mastered) - probability of guess
    
    Returns:
        Updated mastery estimate
    """
    if correct:
        # P(mastered | correct) using Bayes' theorem
        numerator = prior_mastery * (1 - slip_prob)
        denominator = numerator + (1 - prior_mastery) * guess_prob
        posterior = numerator / denominator if denominator > 0 else prior_mastery
    else:
        # P(mastered | incorrect)
        numerator = prior_mastery * slip_prob
        denominator = numerator + (1 - prior_mastery) * (1 - guess_prob)
        posterior = numerator / denominator if denominator > 0 else prior_mastery
    
    return max(0.0, min(1.0, posterior))


def apply_hlr_decay(
    mastery: float,
    half_life_days: float,
    days_since_practice: float
) -> float:
    """
    Apply Half-Life Regression decay to mastery.
    Formula: p = 2^(-Δ/h)
    
    Args:
        mastery: Current mastery level
        half_life_days: Half-life in days
        days_since_practice: Days since last practice
    
    Returns:
        Decayed mastery estimate
    """
    if days_since_practice <= 0:
        return mastery
    
    decay_factor = 2 ** (-days_since_practice / half_life_days)
    return mastery * decay_factor


def predict_mastery_ml(
    practice_count: int,
    correct_count: int,
    time_spent_total: float,
    days_since_last_practice: float,
    model: RandomForestRegressor = None
) -> float:
    """
    Predict mastery using ML model (Random Forest).
    
    Args:
        practice_count: Total practice attempts
        correct_count: Correct attempts
        time_spent_total: Total time spent in seconds
        days_since_last_practice: Days since last practice
        model: Trained sklearn model (if None, uses simple heuristic)
    
    Returns:
        Predicted mastery (0-1)
    """
    if model is None:
        # Fallback heuristic if no model available
        if practice_count == 0:
            return 0.0
        
        success_rate = correct_count / practice_count
        recency_factor = np.exp(-days_since_last_practice / 7.0)  # 7-day decay
        time_factor = min(1.0, time_spent_total / 1800)  # 30 min max
        
        mastery = 0.4 * success_rate + 0.4 * recency_factor + 0.2 * time_factor
        return max(0.0, min(1.0, mastery))
    
    # Use trained model
    features = np.array([[
        practice_count,
        correct_count,
        time_spent_total,
        days_since_last_practice
    ]])
    
    prediction = model.predict(features)[0]
    return max(0.0, min(1.0, prediction))


def compute_similarity_matrix(
    user_skill_vectors: Dict[str, Dict[str, float]]
) -> np.ndarray:
    """
    Compute user similarity matrix for collaborative filtering.
    
    Args:
        user_skill_vectors: {user_id: {skill: mastery}}
    
    Returns:
        NxN similarity matrix
    """
    user_ids = list(user_skill_vectors.keys())
    n_users = len(user_ids)
    
    similarity_matrix = np.zeros((n_users, n_users))
    
    for i, user_i in enumerate(user_ids):
        for j, user_j in enumerate(user_ids):
            if i == j:
                similarity_matrix[i][j] = 1.0
            elif i < j:
                # Cosine similarity
                sim = cosine_similarity_dicts(
                    user_skill_vectors[user_i],
                    user_skill_vectors[user_j]
                )
                similarity_matrix[i][j] = sim
                similarity_matrix[j][i] = sim
    
    return similarity_matrix


def cosine_similarity_dicts(dict1: Dict, dict2: Dict) -> float:
    """Calculate cosine similarity between two dictionaries."""
    common_keys = set(dict1.keys()) & set(dict2.keys())
    
    if not common_keys:
        return 0.0
    
    dot_product = sum(dict1[k] * dict2[k] for k in common_keys)
    mag1 = np.sqrt(sum(dict1[k]**2 for k in common_keys))
    mag2 = np.sqrt(sum(dict2[k]**2 for k in common_keys))
    
    if mag1 == 0 or mag2 == 0:
        return 0.0
    
    return dot_product / (mag1 * mag2)


def extract_features_from_events(events: List[Dict]) -> np.ndarray:
    """
    Extract ML features from learning events for mastery prediction.
    
    Args:
        events: List of event dicts
    
    Returns:
        Feature matrix (n_events, n_features)
    """
    features = []
    
    for event in events:
        feature_vector = [
            event.get('practice_count', 0),
            event.get('correct_count', 0),
            event.get('incorrect_count', 0),
            event.get('time_spent', 0),
            event.get('hint_count', 0),
            event.get('skip_count', 0),
            event.get('days_since_start', 0),
            event.get('session_count', 0)
        ]
        features.append(feature_vector)
    
    return np.array(features)


def calculate_skill_decay_rates(skill_events: List[Dict]) -> Dict[str, float]:
    """
    Calculate personalized decay rates for skills based on historical data.
    
    Args:
        skill_events: List of events for a skill
    
    Returns:
        Dict with decay parameters
    """
    if not skill_events:
        return {'half_life_days': 7.0, 'decay_rate': 0.1}
    
    # Analyze spacing between successful practices
    success_intervals = []
    last_success_time = None
    
    for event in sorted(skill_events, key=lambda x: x['timestamp']):
        if event.get('correct'):
            if last_success_time:
                interval = (event['timestamp'] - last_success_time).days
                if interval > 0:
                    success_intervals.append(interval)
            last_success_time = event['timestamp']
    
    if success_intervals:
        # Median interval as half-life estimate
        half_life = np.median(success_intervals)
    else:
        half_life = 7.0  # Default 1 week
    
    decay_rate = np.log(2) / half_life
    
    return {
        'half_life_days': float(half_life),
        'decay_rate': float(decay_rate),
        'confidence': min(1.0, len(success_intervals) / 10.0)
    }









