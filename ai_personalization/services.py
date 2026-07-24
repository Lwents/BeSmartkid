# ai_personalization/services.py

from django.utils import timezone
from ai_personalization.models import LearningEvent, ContentSkill, UserSkillMastery, RecommendationLog
from content.models import Lesson, Course  # adjust import to your content app
# (opt) from .models import SpacedRepetitionEntry

def update_mastery(user, skill, outcome, alpha=0.2):
    """Simple moving-average update of mastery."""
    obj, _ = UserSkillMastery.objects.get_or_create(user=user, skill=skill)
    old = obj.mastery
    new = old + alpha * (float(outcome) - old)
    # clamp to [0,1]
    obj.mastery = max(0.0, min(1.0, new))
    obj.save()
    return obj

def lesson_score(user, lesson, weights=None):
    if weights is None:
        weights = {'w1': 0.6, 'w2': 0.25, 'w3': -0.15, 'w4': 0.1}
    # 1) mastery average
    skills = ContentSkill.objects.filter(lesson=lesson)
    if not skills.exists():
        mastery_avg = 0.5
    else:
        vals = []
        total_w = 0.0
        for s in skills:
            total_w += s.weight
            try:
                m = UserSkillMastery.objects.get(user=user, skill=s.skill).mastery
            except UserSkillMastery.DoesNotExist:
                m = 0.0
            vals.append(m * s.weight)
        mastery_avg = sum(vals) / total_w if total_w > 0 else 0.0

    # 2) due score (dummy for now)
    due = 0.0
    # if SpacedRepetitionEntry implemented, you can check sr.next_review <= now → due = 1.0

    # 3) novelty penalty: overlapping recent skills
    recent = LearningEvent.objects.filter(user=user).order_by('-timestamp')[:10]
    recent_skills = set()
    for ev in recent:
        if ev.lesson:
            recent_skills.update(ContentSkill.objects.filter(lesson=ev.lesson).values_list('skill', flat=True))
    overlap = len(set(s.skill for s in skills) & recent_skills)
    novelty_penalty = overlap / (len(skills) + 1) if skills.exists() else 0.0

    # 4) recency boost
    if hasattr(lesson, 'created_at'):
        age_days = (timezone.now() - lesson.created_at).days
        recency = max(0.0, 1 - age_days / 365.0)
    else:
        recency = 0.0

    score_val = (
        weights['w1'] * (1 - mastery_avg)
        + weights['w2'] * due
        + weights['w3'] * novelty_penalty
        + weights['w4'] * recency
    )
    # clamp
    final = max(0.0, min(1.0, score_val))
    # gather reason dict
    reason = {
        'mastery_avg': mastery_avg,
        'due': due,
        'novelty_penalty': novelty_penalty,
        'recency': recency,
        'raw_score': final,
    }
    return final, reason


class RuleEngine:
    def __init__(self, user, course):
        self.user = user
        self.course = course

    def get_candidates(self):
        lessons = Lesson.objects.filter(course=self.course)
        # excluding completed lessons:
        completed = LearningEvent.objects.filter(
            user=self.user, event_type='complete', course=self.course
        ).values_list('lesson__id', flat=True)
        cand = lessons.exclude(id__in=completed)
        return cand

    def recommend(self, top_n=5):
        candidates = self.get_candidates()
        scored = []
        for lesson in candidates:
            s, reason = lesson_score(self.user, lesson)
            scored.append((s, lesson, reason))
        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, lesson, reason in scored[:top_n]:
            # log
            rec = RecommendationLog.objects.create(
                user=self.user,
                lesson=lesson,
                score=score,
                reason=reason,
                source='rule'
            )
            results.append({
                'recommendation_id': str(rec.id),
                'lesson_id': str(lesson.id),
                'score': score,
                'reason': reason,
            })
        return results
