from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, List
import json
import redis
import os

@dataclass
class TaskState:
    correlation_id: str
    first_seen: datetime
    last_seen: datetime
    has_sandbox: bool = False
    running_task_count: int = 0
    task_history: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert TaskState to a dictionary for Redis storage."""
        return {
            "correlation_id": self.correlation_id,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "has_sandbox": self.has_sandbox,
            "running_task_count": self.running_task_count,
            "task_history": self.task_history
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'TaskState':
        """Create TaskState from a dictionary from Redis."""
        return cls(
            correlation_id=data["correlation_id"],
            first_seen=datetime.fromisoformat(data["first_seen"]),
            last_seen=datetime.fromisoformat(data["last_seen"]),
            has_sandbox=data["has_sandbox"],
            running_task_count=data["running_task_count"],
            task_history=data["task_history"]
        )

class TaskTracker:
    def __init__(self):
        """Initialize Redis connection for task tracking."""
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', 6379))
        self.redis = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True  # Automatically decode responses to strings
        )
        self.key_prefix = "task_tracker:"
    
    def _get_key(self, correlation_id: str) -> str:
        """Get Redis key for a correlation ID."""
        return f"{self.key_prefix}{correlation_id}"
    
    def register_task(self, correlation_id: str, task_name: Optional[str] = None) -> TaskState:
        """Register a new task execution for a correlation ID."""
        if not correlation_id:
            raise ValueError("correlation_id cannot be empty")
        
        key = self._get_key(correlation_id)
        now = datetime.utcnow()
        
        # Use Redis WATCH/MULTI/EXEC for atomic updates
        with self.redis.pipeline() as pipe:
            while True:
                try:
                    # Watch the key for changes
                    pipe.watch(key)
                    
                    # Get current state
                    data = self.redis.get(key)
                    if data:
                        state = TaskState.from_dict(json.loads(data))
                        state.last_seen = now
                        state.running_task_count += 1
                        if task_name:
                            state.task_history.append(task_name)
                    else:
                        state = TaskState(
                            correlation_id=correlation_id,
                            first_seen=now,
                            last_seen=now,
                            running_task_count=1,
                            task_history=[task_name] if task_name else []
                        )
                    
                    # Start transaction
                    pipe.multi()
                    pipe.set(key, json.dumps(state.to_dict()))
                    pipe.execute()
                    return state
                    
                except redis.WatchError:
                    # Another client modified the key while we were working
                    continue

    def finish_task(self, correlation_id: str) -> Optional[TaskState]:
        """Mark a task as finished for a correlation ID."""
        if not correlation_id:
            return None
            
        key = self._get_key(correlation_id)
        now = datetime.utcnow()
        
        with self.redis.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(key)
                    data = self.redis.get(key)
                    if data:
                        state = TaskState.from_dict(json.loads(data))
                        state.running_task_count = max(0, state.running_task_count - 1)
                        state.last_seen = now
                        
                        pipe.multi()
                        pipe.set(key, json.dumps(state.to_dict()))
                        pipe.execute()
                        return state
                    return None
                except redis.WatchError:
                    continue

    def set_sandbox_state(self, correlation_id: str, has_sandbox: bool) -> Optional[TaskState]:
        """Update the sandbox state for a correlation ID."""
        if not correlation_id:
            return None
            
        key = self._get_key(correlation_id)
        
        with self.redis.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(key)
                    data = self.redis.get(key)
                    if data:
                        state = TaskState.from_dict(json.loads(data))
                        state.has_sandbox = has_sandbox
                        
                        pipe.multi()
                        pipe.set(key, json.dumps(state.to_dict()))
                        pipe.execute()
                        return state
                    return None
                except redis.WatchError:
                    continue

    def get_state(self, correlation_id: str) -> Optional[TaskState]:
        """Get the current state for a correlation ID."""
        if not correlation_id:
            return None
            
        data = self.redis.get(self._get_key(correlation_id))
        if data:
            return TaskState.from_dict(json.loads(data))
        return None

    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """Remove task states older than max_age_hours with no running tasks."""
        now = datetime.utcnow()
        pattern = f"{self.key_prefix}*"
        
        for key in self.redis.scan_iter(pattern):
            data = self.redis.get(key)
            if data:
                state = TaskState.from_dict(json.loads(data))
                if ((now - state.last_seen).total_seconds() > max_age_hours * 3600
                    and state.running_task_count == 0
                    and not state.has_sandbox):
                    self.redis.delete(key)

# Global task tracker instance
task_tracker = TaskTracker() 