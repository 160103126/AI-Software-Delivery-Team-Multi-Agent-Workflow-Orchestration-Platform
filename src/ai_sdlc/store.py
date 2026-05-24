from __future__ import annotations

from copy import deepcopy
from threading import Lock
from typing import Dict

from .state import WorkflowState


class WorkflowStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._workflows: Dict[str, WorkflowState] = {}

    def save(self, workflow_id: str, state: WorkflowState) -> WorkflowState:
        with self._lock:
            self._workflows[workflow_id] = deepcopy(state)
            return deepcopy(state)

    def get(self, workflow_id: str) -> WorkflowState | None:
        with self._lock:
            state = self._workflows.get(workflow_id)
            return deepcopy(state) if state is not None else None

    def list(self) -> Dict[str, WorkflowState]:
        with self._lock:
            return deepcopy(self._workflows)


workflow_store = WorkflowStore()
