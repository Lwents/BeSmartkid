from typing import List, Optional
from django.db import transaction
from django.contrib.auth import get_user_model

from content.models import Exploration, ExplorationState, ExplorationTransition
from content.domains.exploration_domain import (
    ExplorationDomain, CreateExplorationDomain, UpdateExplorationDomain, PublishExplorationDomain
)
from content.domains.exploration_domain import (
    ExplorationStateDomain, ExplorationTransitionDomain, CreateStateDomain, UpdateStateDomain, CreateTransitionDomain
)


User = get_user_model()


class ExplorationService:
    """Service for managing explorations (interactive lessons)."""

    @transaction.atomic
    def create_exploration(self, input_data: CreateExplorationDomain) -> ExplorationDomain:
        input_data.validate()
        owner = User.objects.filter(id=input_data.owner_id).first()
        exploration = Exploration.objects.create(
            title=input_data.title,
            owner=owner,
            language=input_data.language
        )
        return ExplorationDomain.from_model(exploration)

    def list_explorations(self) -> List[ExplorationDomain]:
        return [ExplorationDomain.from_model(e) for e in Exploration.objects.all()]

    @transaction.atomic
    def update_exploration(self, exploration_id: str, update_data: UpdateExplorationDomain) -> Optional[ExplorationDomain]:
        try:
            exp = Exploration.objects.get(id=exploration_id)
        except Exploration.DoesNotExist:
            return None
        update_data.validate()
        if update_data.title: exp.title = update_data.title
        if update_data.language: exp.language = update_data.language
        exp.save()
        return ExplorationDomain.from_model(exp)

    @transaction.atomic
    def publish_exploration(self, exploration_id: str, publish_data: PublishExplorationDomain) -> Optional[ExplorationDomain]:
        try:
            exp = Exploration.objects.get(id=exploration_id)
        except Exploration.DoesNotExist:
            return None
        publish_data.validate()
        exp.published = publish_data.published
        exp.save()
        return ExplorationDomain.from_model(exp)


class ExplorationStateService:
    """Service for managing exploration states."""

    @transaction.atomic
    def create_state(self, input_data: CreateStateDomain) -> ExplorationStateDomain:
        input_data.validate()
        exploration = Exploration.objects.get(id=input_data.exploration_id)
        state = ExplorationState.objects.create(
            exploration=exploration,
            name=input_data.name,
            content=input_data.content,
            interaction=input_data.interaction
        )
        return ExplorationStateDomain.from_model(state)

    def list_states(self, exploration_id: str) -> List[ExplorationStateDomain]:
        return [ExplorationStateDomain.from_model(s) for s in ExplorationState.objects.filter(exploration_id=exploration_id)]

    @transaction.atomic
    def update_state(self, state_id: str, update_data: UpdateStateDomain) -> Optional[ExplorationStateDomain]:
        try:
            state = ExplorationState.objects.get(id=state_id)
        except ExplorationState.DoesNotExist:
            return None
        update_data.validate()
        if update_data.name: state.name = update_data.name
        if update_data.content: state.content.update(update_data.content)
        if update_data.interaction: state.interaction.update(update_data.interaction)
        state.save()
        return ExplorationStateDomain.from_model(state)


class ExplorationTransitionService:
    """Service for managing exploration transitions."""

    @transaction.atomic
    def create_transition(self, input_data: CreateTransitionDomain) -> ExplorationTransitionDomain:
        input_data.validate()
        exploration = Exploration.objects.get(id=input_data.exploration_id)
        from_state = ExplorationState.objects.get(id=input_data.from_state_id)
        to_state = ExplorationState.objects.get(id=input_data.to_state_id)
        transition = ExplorationTransition.objects.create(
            exploration=exploration,
            from_state=from_state,
            to_state=to_state,
            condition=input_data.condition
        )
        return ExplorationTransitionDomain.from_model(transition)

    def list_transitions(self, exploration_id: str) -> List[ExplorationTransitionDomain]:
        return [ExplorationTransitionDomain.from_model(t) for t in ExplorationTransition.objects.filter(exploration_id=exploration_id)]
    


