from typing import List, Optional
from django.db import transaction

from content.models import ContentBlock, LessonVersion
from content.domains.content_block_domain import (
    ContentBlockDomain, CreateContentBlockDomain, UpdateContentBlockDomain, ReorderContentBlocksDomain
)


class ContentBlockService:
    """Service for managing content blocks inside a lesson version."""

    @transaction.atomic
    def create_block(self, input_data: CreateContentBlockDomain) -> ContentBlockDomain:
        input_data.validate()
        lesson_version = LessonVersion.objects.get(id=input_data.lesson_version_id)
        block = ContentBlock.objects.create(
            lesson_version=lesson_version,
            type=input_data.type,
            position=input_data.position,
            payload=input_data.payload
        )
        return ContentBlockDomain.from_model(block)

    def list_blocks(self, lesson_version_id: str) -> List[ContentBlockDomain]:
        return [ContentBlockDomain.from_model(b) for b in ContentBlock.objects.filter(lesson_version_id=lesson_version_id)]

    @transaction.atomic
    def update_block(self, block_id: str, update_data: UpdateContentBlockDomain) -> Optional[ContentBlockDomain]:
        try:
            block = ContentBlock.objects.get(id=block_id)
        except ContentBlock.DoesNotExist:
            return None
        update_data.validate()
        if update_data.type: block.type = update_data.type
        if update_data.payload: block.payload.update(update_data.payload)
        if update_data.position is not None: block.position = update_data.position
        block.save()
        return ContentBlockDomain.from_model(block)

    @transaction.atomic
    def reorder_blocks(self, lesson_version_id: str, reorder_data: ReorderContentBlocksDomain) -> None:
        reorder_data.validate()
        for block_id, pos in reorder_data.order_map.items():
            ContentBlock.objects.filter(id=block_id, lesson_version_id=lesson_version_id).update(position=pos)
