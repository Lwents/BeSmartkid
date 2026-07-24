from typing import List, Optional
from django.db import transaction

from content.models import Module, Course
from content.domains.module_domain import (
    ModuleDomain, CreateModuleDomain, UpdateModuleDomain, ReorderModulesDomain
)


class ModuleService:
    """Service for managing course modules."""

    @transaction.atomic
    def create_module(self, input_data: CreateModuleDomain) -> ModuleDomain:
        input_data.validate()
        course = Course.objects.get(id=input_data.course_id)
        module = Module.objects.create(
            course=course,
            title=input_data.title,
            position=input_data.position
        )
        return ModuleDomain.from_model(module)

    def list_modules(self, course_id: str) -> List[ModuleDomain]:
        return [ModuleDomain.from_model(m) for m in Module.objects.filter(course_id=course_id)]

    @transaction.atomic
    def update_module(self, module_id: str, update_data: UpdateModuleDomain) -> Optional[ModuleDomain]:
        try:
            module = Module.objects.get(id=module_id)
        except Module.DoesNotExist:
            return None
        update_data.validate()
        if update_data.title: module.title = update_data.title
        if update_data.position is not None: module.position = update_data.position
        module.save()
        return ModuleDomain.from_model(module)

    @transaction.atomic
    def reorder_modules(self, course_id: str, reorder_data: ReorderModulesDomain) -> None:
        reorder_data.validate()
        for mod_id, pos in reorder_data.order_map.items():
            Module.objects.filter(id=mod_id, course_id=course_id).update(position=pos)
