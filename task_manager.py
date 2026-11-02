"""
task_manager.py
Handles task queuing, state tracking, and duplicate result suppression.
Role 2: Server Task Queue & Duplicate Suppression
"""

import time
from enum import Enum
from typing import Optional, Tuple, Dict, Set


class TaskStatus(Enum):
    PENDING = "PENDING"
    IN_FLIGHT = "IN_FLIGHT"
    COMPLETED = "COMPLETED"


class Task:
    def __init__(self, task_id: int, payload: bytes):
        self.task_id = task_id
        self.payload = payload
        self.status = TaskStatus.PENDING
        self.assigned_worker: Optional[int] = None
        self.dispatch_time: Optional[float] = None
        self.result: Optional[bytes] = None


class TaskManager:
    def __init__(self):
        self.tasks: Dict[int, Task] = {}
        self.completed_task_ids: Set[int] = set()

    def add_task(self, task_id: int, payload: bytes) -> None:
        """Register a new task in the queue."""
        self.tasks[task_id] = Task(task_id, payload)

    def load_dummy_tasks(self, count: int = 5) -> None:
        """Helper to quickly seed tasks for Phase 1 testing."""
        for i in range(1, count + 1):
            self.add_task(i, f"dummy_payload_for_task_{i}".encode("utf-8"))

    def get_next_pending_task(self, worker_id: int) -> Optional[Tuple[int, bytes]]:
        """
        Fetches the next available task and marks it IN_FLIGHT.
        Returns (task_id, payload) or None if no tasks are pending.
        """
        for task in self.tasks.values():
            if task.status == TaskStatus.PENDING:
                task.status = TaskStatus.IN_FLIGHT
                task.assigned_worker = worker_id
                task.dispatch_time = time.time()
                return task.task_id, task.payload
        return None

    def process_result(self, task_id: int, result_payload: bytes) -> bool:
        """
        Records the result of a task.

        Duplicate Suppression:
        - If task_id is already in completed_task_ids, return False (duplicate detected).
        - If new, record result, mark COMPLETED, and return True.
        """
        if task_id in self.completed_task_ids:
            # Duplicate result received (e.g. retransmitted by worker)
            return False

        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.status = TaskStatus.COMPLETED
            task.result = result_payload
            self.completed_task_ids.add(task_id)
            return True

        # Unknown task
        return False

    def all_completed(self) -> bool:
        """Returns True if every loaded task has been completed."""
        return len(self.completed_task_ids) == len(self.tasks) and len(self.tasks) > 0