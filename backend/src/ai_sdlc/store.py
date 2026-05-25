from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Dict

logger = logging.getLogger(__name__)

# Try to import Firestore, fall back to in-memory if not available
try:
    from google.cloud import firestore
    FIRESTORE_AVAILABLE = True
except ImportError:
    FIRESTORE_AVAILABLE = False
    logger.warning("Firestore not available, using in-memory storage for local development")


class WorkflowStore:
    """Workflow store with Firestore support and in-memory fallback."""

    def __init__(self) -> None:
        """Initialize store - use Firestore if available, otherwise in-memory."""
        self.use_firestore = False
        self._workflows: Dict[str, dict] = {}  # In-memory fallback

        if FIRESTORE_AVAILABLE:
            try:
                self.db = firestore.Client()
                self.collection = self.db.collection("workflows")
                self.use_firestore = True
                logger.info("Using Firestore for workflow storage")
            except Exception as e:
                logger.warning(f"Firestore unavailable ({e}), falling back to in-memory storage")
                self.use_firestore = False
        else:
            logger.info("Using in-memory storage for local development")

    def save(self, workflow_id: str, state: dict) -> dict:
        """Save workflow state."""
        try:
            state_copy = dict(state)
            state_copy["_updated_at"] = datetime.utcnow()
            state_copy["_workflow_id"] = workflow_id
            state_copy.pop("project_archive_base64", None)  # CRITICAL: Prevent 1MB Firestore limit crash

            # Convert non-serializable objects
            for key in list(state_copy.keys()):
                if not self._is_serializable(state_copy[key]):
                    state_copy[key] = str(state_copy[key])

            if self.use_firestore:
                self.collection.document(workflow_id).set(state_copy, merge=True)
            else:
                self._workflows[workflow_id] = state_copy

            logger.debug(f"Saved workflow {workflow_id}")
            return state
        except Exception as e:
            logger.error(f"Failed to save workflow {workflow_id}: {e}")
            # Fall back to in-memory if Firestore fails
            self._workflows[workflow_id] = state
            return state

    def get(self, workflow_id: str) -> dict | None:
        """Retrieve workflow state."""
        try:
            if self.use_firestore:
                doc = self.collection.document(workflow_id).get()
                if doc.exists:
                    data = doc.to_dict()
                    data.pop("_updated_at", None)
                    data.pop("_workflow_id", None)
                    return data
            else:
                if workflow_id in self._workflows:
                    data = dict(self._workflows[workflow_id])
                    data.pop("_updated_at", None)
                    data.pop("_workflow_id", None)
                    return data

            logger.debug(f"Workflow {workflow_id} not found")
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve workflow {workflow_id}: {e}")
            return None

    def list(self) -> Dict[str, dict]:
        """List all workflows."""
        try:
            workflows = {}
            if self.use_firestore:
                docs = self.collection.stream()
                for doc in docs:
                    data = doc.to_dict()
                    data.pop("_updated_at", None)
                    data.pop("_workflow_id", None)
                    workflows[doc.id] = data
            else:
                for wid, data in self._workflows.items():
                    data_copy = dict(data)
                    data_copy.pop("_updated_at", None)
                    data_copy.pop("_workflow_id", None)
                    workflows[wid] = data_copy

            logger.debug(f"Retrieved {len(workflows)} workflows")
            return workflows
        except Exception as e:
            logger.error(f"Failed to list workflows: {e}")
            return {}

    def delete(self, workflow_id: str) -> None:
        """Delete a workflow."""
        try:
            if self.use_firestore:
                self.collection.document(workflow_id).delete()
            else:
                if workflow_id in self._workflows:
                    del self._workflows[workflow_id]

            logger.debug(f"Deleted workflow {workflow_id}")
        except Exception as e:
            logger.error(f"Failed to delete workflow {workflow_id}: {e}")

    @staticmethod
    def _is_serializable(obj) -> bool:
        """Check if object is JSON-serializable."""
        try:
            json.dumps(obj, default=str)
            return True
        except (TypeError, ValueError):
            return False


workflow_store = WorkflowStore()
