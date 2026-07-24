from typing import List, Optional
from django.db import transaction

from content.models import Subject
from content.domains.subject_domain import SubjectDomain, CreateSubjectDomain, UpdateSubjectDomain


class SubjectService:
    """Application service for managing subjects."""

    @transaction.atomic
    def create_subject(self, input_data: CreateSubjectDomain) -> SubjectDomain:
        """Create a new subject."""
        input_data.validate()
        subject = Subject.objects.create(
            title=input_data.title,
            slug=input_data.slug
        )
        return SubjectDomain.from_model(subject)

    def get_subject(self, subject_id: str) -> Optional[SubjectDomain]:
        """Retrieve a subject by id."""
        try:
            subject = Subject.objects.get(id=subject_id)
            return SubjectDomain.from_model(subject)
        except Subject.DoesNotExist:
            return None

    def list_subjects(self) -> List[SubjectDomain]:
        """List all subjects."""
        return [SubjectDomain.from_model(s) for s in Subject.objects.all()]

    @transaction.atomic
    def update_subject(self, subject_id: str, update_data: UpdateSubjectDomain) -> Optional[SubjectDomain]:
        """Update subject."""
        try:
            subject = Subject.objects.get(id=subject_id)
        except Subject.DoesNotExist:
            return None
        update_data.validate()
        subject.title = update_data.title or subject.title
        subject.slug = update_data.slug or subject.slug
        subject.save()
        return SubjectDomain.from_model(subject)

    @transaction.atomic
    def delete_subject(self, subject_id: str) -> bool:
        """Delete a subject."""
        try:
            Subject.objects.get(id=subject_id).delete()
            return True
        except Subject.DoesNotExist:
            return False
