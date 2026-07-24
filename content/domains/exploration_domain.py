import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Iterable, Tuple
from collections import deque

from content.services.exceptions import DomainValidationError, NotFoundError, InvalidOperation
from content.domains.lesson_domain import LessonDomain 
from content.domains.value_objects import CreateExplorationCommand, AddExplorationStateCommand, AddExplorationTransitionCommand


class ExplorationStateDomain:
    def __init__(self, exploration_id: str, name: str, content: Dict[str, Any], interaction: Dict[str, Any], id: Optional[str] = None):
        self.id = id or str(uuid.uuid4())
        self.exploration_id = exploration_id
        self.name = name
        self.content = content or {}
        self.interaction = interaction or {}
        self.validate()

    def validate(self):
        if not self.exploration_id:
            raise DomainValidationError("ExplorationState.exploration_id required.")
        if not self.name or not self.name.strip():
            raise DomainValidationError("ExplorationState.name required.")
        if not isinstance(self.content, dict) or not isinstance(self.interaction, dict):
            raise DomainValidationError("content and interaction must be dicts.")
        # interaction may require a schema like {'type': 'text'/'choice', 'hints': [...]} but leave flexible

    def to_dict(self):
        return {"id": self.id, "exploration_id": self.exploration_id, "name": self.name, "content": self.content, "interaction": self.interaction}


class ExplorationTransitionDomain:
    def __init__(self, exploration_id: str, from_state: str, to_state: str, condition: Dict[str, Any], id: Optional[str] = None):
        self.id = id or str(uuid.uuid4())
        self.exploration_id = exploration_id
        self.from_state = from_state
        self.to_state = to_state
        self.condition = condition or {}
        self.validate()

    def validate(self):
        if not self.exploration_id:
            raise DomainValidationError("ExplorationTransition.exploration_id required.")
        if not self.from_state or not self.to_state:
            raise DomainValidationError("from_state and to_state required.")
        if not isinstance(self.condition, dict):
            raise DomainValidationError("condition must be dict.")

    def to_dict(self):
        return {"id": self.id, "exploration_id": self.exploration_id, "from_state": self.from_state, "to_state": self.to_state, "condition": self.condition}


class ExplorationDomain:
    """
    Exploration is an aggregate representing an interactive, state-based activity.
    Business rules enforced here:
    - Must define an initial_state_name before publishing/running.
    - All transitions must refer to existing states.
    - All states (except maybe intentionally archived) should be reachable from initial state (no isolated states).
    - Schema version must be >=1.
    """

    def __init__(self, title: str, owner_id: Optional[int] = None, language: str = "vi", initial_state_name: Optional[str] = None, schema_version: int = 1, published: bool = False, id: Optional[str] = None):
        self.id = id or str(uuid.uuid4())
        self.title = title
        self.owner_id = owner_id
        self.language = language
        self.initial_state_name = initial_state_name
        self.schema_version = int(schema_version)
        self.published = published
        self.states: List[ExplorationStateDomain] = []
        self.transitions: List[ExplorationTransitionDomain] = []
        self.validate()

    def validate(self):
        if not self.title or not self.title.strip():
            raise DomainValidationError("Exploration.title required.")
        if not isinstance(self.schema_version, int) or self.schema_version < 1:
            raise DomainValidationError("schema_version must be >=1.")
        # initial_state_name may be None until enough states added

    def add_state(self, name: str, content: Dict[str, Any], interaction: Dict[str, Any]) -> ExplorationStateDomain:
        if any(s.name == name for s in self.states):
            raise DomainValidationError("State name must be unique within exploration.")
        s = ExplorationStateDomain(exploration_id=self.id, name=name, content=content, interaction=interaction)
        self.states.append(s)
        return s

    def add_transition(self, from_state: str, to_state: str, condition: Dict[str, Any]) -> ExplorationTransitionDomain:
        # validation: ensure states exist (in-memory)
        if not any(s.name == from_state for s in self.states):
            raise NotFoundError(f"from_state '{from_state}' not found.")
        if not any(s.name == to_state for s in self.states):
            raise NotFoundError(f"to_state '{to_state}' not found.")
        t = ExplorationTransitionDomain(exploration_id=self.id, from_state=from_state, to_state=to_state, condition=condition)
        self.transitions.append(t)
        return t

    def get_state(self, name: str) -> ExplorationStateDomain:
        s = next((st for st in self.states if st.name == name), None)
        if not s:
            raise NotFoundError("State not found.")
        return s

    def validate_graph(self):
        # 1. initial_state must exist
        if not self.initial_state_name:
            raise DomainValidationError("Exploration.initial_state_name must be set before validating graph.")
        if not any(s.name == self.initial_state_name for s in self.states):
            raise DomainValidationError("initial_state_name does not correspond to any state.")

        # 2. all transitions refer to valid states (already checked on add_transition, but re-check)
        state_names = {s.name for s in self.states}
        for t in self.transitions:
            if t.from_state not in state_names or t.to_state not in state_names:
                raise DomainValidationError("Transition refers to non-existent state.")

        # 3. reachability: every state should be reachable from initial_state (unless explicitly marked archived)
        adj = {s.name: [] for s in self.states}
        for t in self.transitions:
            adj[t.from_state].append(t.to_state)

        # BFS from initial
        start = self.initial_state_name
        visited = set()
        q = deque([start])
        while q:
            cur = q.popleft()
            if cur in visited:
                continue
            visited.add(cur)
            for nb in adj.get(cur, []):
                if nb not in visited:
                    q.append(nb)
        unreachable = [s.name for s in self.states if s.name not in visited]
        if unreachable:
            raise DomainValidationError(f"Unreachable states exist: {unreachable}")
        return True

    def publish(self):
        # to publish exploration, ensure graph valid
        self.validate_graph()
        self.published = True

    def unpublish(self):
        self.published = False

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "owner_id": self.owner_id,
            "language": self.language,
            "initial_state_name": self.initial_state_name,
            "schema_version": self.schema_version,
            "published": self.published,
            "states": [s.to_dict() for s in self.states],
            "transitions": [t.to_dict() for t in self.transitions]
        }

    @classmethod
    def from_model(cls, model):
        e = cls(title=model.title, owner_id=(model.owner.id if getattr(model,'owner',None) else None), language=model.language, initial_state_name=getattr(model,'initial_state_name',None), schema_version=getattr(model,'schema_version',1), published=model.published, id=str(model.id))
        if hasattr(model, "states_prefetched") and model.states_prefetched:
            for s_m in model.states_prefetched:
                e.states.append(ExplorationStateDomain(exploration_id=e.id, name=s_m.name, content=s_m.content, interaction=s_m.interaction, id=str(s_m.id)))
        if hasattr(model, "transitions_prefetched") and model.transitions_prefetched:
            for t_m in model.transitions_prefetched:
                e.transitions.append(ExplorationTransitionDomain(exploration_id=e.id, from_state=t_m.from_state.name if getattr(t_m,'from_state',None) else t_m.from_state, to_state=t_m.to_state.name if getattr(t_m,'to_state',None) else t_m.to_state, condition=t_m.condition, id=str(t_m.id)))
        return e
    

# --- Domain classes for input, output validation (DTOs) ---
class CreateExplorationDomain:
    """
    Domain service for creating a new exploration.
    Mimics Oppia creation use case: Takes command, creates aggregate, returns it.
    """
    def execute(self, command: CreateExplorationCommand) -> ExplorationDomain:
        command.validate()
        exploration = ExplorationDomain(
            title=command.title,
            owner_id=command.owner_id,
            language=command.language,
            initial_state_name=command.initial_state_name,
            schema_version=command.schema_version
        )
        # Emit event (placeholder)
        # DomainEvents.raise(ExplorationCreatedEvent(exploration))
        return exploration


class UpdateExplorationDomain:
    """Command object for updating an exploration."""
    def __init__(self, title: Optional[str] = None, language: Optional[str] = None,
                 initial_state_name: Optional[str] = None):
        self.title = title
        self.language = language
        self.initial_state_name = initial_state_name

    def validate(self):
        if self.title is not None and (not self.title or not self.title.strip()):
            raise DomainValidationError("Exploration title cannot be empty.")

class CreateStateDomain:
    """
    Domain service for adding a new state to an exploration.
    Mimics Oppia add state use case: Takes command, adds via aggregate, returns the state.
    """
    def __init__(self, exploration: ExplorationDomain):
        self.exploration = exploration

    def execute(self, command: AddExplorationStateCommand) -> ExplorationStateDomain:
        command.validate()
        self.exploration.validate()
        new_state = self.exploration.add_state(
            name=command.name,
            content=command.content,
            interaction=command.interaction
        )
        # Optional: validate graph post-add if desired
        # self.exploration.validate_graph()  # But may fail if incomplete
        # Emit event (placeholder)
        return new_state

class UpdateStateDomain:
    """
    Domain service for updating an existing state's content or interaction.
    Mimics Oppia update state: Only on unpublished, validates changes.
    """
    def __init__(self, exploration: ExplorationDomain):
        self.exploration = exploration

    def execute(self, name: str, new_content: Optional[Dict[str, Any]] = None, new_interaction: Optional[Dict[str, Any]] = None) -> ExplorationStateDomain:
        if not name:
            raise DomainValidationError("state name required.")
        self.exploration.validate()
        updated_state = self.exploration.update_state(name, new_content, new_interaction)
        # Emit event (placeholder)
        return updated_state

class DeleteStateDomain:
    """
    Domain service for deleting a state and related transitions.
    Mimics Oppia delete state: Handles cleanup.
    """
    def __init__(self, exploration: ExplorationDomain):
        self.exploration = exploration

    def execute(self, name: str):
        if not name:
            raise DomainValidationError("state name required.")
        self.exploration.validate()
        self.exploration.delete_state(name)
        # Emit event (placeholder)

class CreateTransitionDomain:
    """
    Domain service for adding a new transition.
    Mimics Oppia add transition use case.
    """
    def __init__(self, exploration: ExplorationDomain):
        self.exploration = exploration

    def execute(self, command: AddExplorationTransitionCommand) -> ExplorationTransitionDomain:
        command.validate()
        self.exploration.validate()
        new_transition = self.exploration.add_transition(
            from_state=command.from_state,
            to_state=command.to_state,
            condition=command.condition
        )
        # Emit event (placeholder)
        return new_transition

class UpdateTransitionDomain:
    """
    Domain service for updating an existing transition.
    Mimics Oppia update transition.
    """
    def __init__(self, exploration: ExplorationDomain):
        self.exploration = exploration

    def execute(self, transition_id: str, new_from_state: Optional[str] = None, new_to_state: Optional[str] = None, new_condition: Optional[Dict[str, Any]] = None) -> ExplorationTransitionDomain:
        if not transition_id:
            raise DomainValidationError("transition_id required.")
        self.exploration.validate()
        updated_transition = self.exploration.update_transition(transition_id, new_from_state, new_to_state, new_condition)
        # Emit event (placeholder)
        return updated_transition

class DeleteTransitionDomain:
    """
    Domain service for deleting a transition.
    Mimics Oppia delete transition.
    """
    def __init__(self, exploration: ExplorationDomain):
        self.exploration = exploration

    def execute(self, transition_id: str):
        if not transition_id:
            raise DomainValidationError("transition_id required.")
        self.exploration.validate()
        self.exploration.delete_transition(transition_id)
        # Emit event (placeholder)

class SetInitialStateDomain:
    """
    Domain service for setting the initial state.
    Mimics Oppia set init state.
    """
    def __init__(self, exploration: ExplorationDomain):
        self.exploration = exploration

    def execute(self, name: str):
        if not name:
            raise DomainValidationError("state name required.")
        self.exploration.validate()
        self.exploration.set_initial_state(name)
        # Emit event (placeholder)

class PublishExplorationDomain:
    """
    Domain service for publishing the exploration.
    Mimics Oppia publish workflow: Validates graph, sets published.
    """
    def __init__(self, exploration: ExplorationDomain):
        self.exploration = exploration

    def execute(self):
        self.exploration.validate()
        self.exploration.publish()
        # Emit event (placeholder)

class UnpublishExplorationDomain:
    """
    Domain service for unpublishing.
    """
    def __init__(self, exploration: ExplorationDomain):
        self.exploration = exploration

    def execute(self):
        self.exploration.unpublish()
        # Emit event (placeholder)