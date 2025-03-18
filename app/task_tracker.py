from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional, List
import json
import redis
import os
import logging

logger = logging.getLogger(__name__)

redis_host = os.getenv('REDIS_HOST', 'localhost')
redis_port = int(os.getenv('REDIS_PORT', 6379))

@dataclass
class TaskState:
    correlation_id: str
    first_seen: datetime
    last_seen: datetime
    has_sandbox: bool = False
    running_task_count: int = 0
    task_history: List[str] = field(default_factory=list)
    container_id: Optional[str] = None
    container_created_at: Optional[datetime] = None
    last_task_completed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert TaskState to a dictionary for Redis storage."""
        return {
            "correlation_id": self.correlation_id,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "has_sandbox": self.has_sandbox,
            "running_task_count": self.running_task_count,
            "task_history": self.task_history,
            "container_id": self.container_id,
            "container_created_at": self.container_created_at.isoformat() if self.container_created_at else None,
            "last_task_completed_at": self.last_task_completed_at.isoformat() if self.last_task_completed_at else None
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
            task_history=data["task_history"],
            container_id=data.get("container_id"),
            container_created_at=datetime.fromisoformat(data["container_created_at"]) if data.get("container_created_at") else None,
            last_task_completed_at=datetime.fromisoformat(data["last_task_completed_at"]) if data.get("last_task_completed_at") else None
        )

class TaskTracker:
    def __init__(self):
        """Initialize Redis connection for task tracking."""

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
                            task_history=[task_name] if task_name else [],
                            container_id=None,
                            container_created_at=None
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
                        state.last_task_completed_at = now
                        
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
            logger.warning("get_state called with empty correlation_id")
            return None
            
        key = self._get_key(correlation_id)
        logger.info(f"Attempting to get state for key={key}")
        try:
            data = self.redis.get(key)
            if data:
                logger.info(f"Found data in Redis for key={key}: {data[:100]}...")
                return TaskState.from_dict(json.loads(data))
            logger.warning(f"No data found in Redis for key={key}")
            return None
        except Exception as e:
            logger.error(f"Error getting state from Redis for key={key}: {str(e)}")
            return None

    def set_container_id(self, correlation_id: str, container_id: str) -> Optional[TaskState]:
        """Set the container ID for a correlation ID."""
        if not correlation_id or not container_id:
            logger.warning(f"set_container_id called with invalid parameters: correlation_id={correlation_id}, container_id={container_id}")
            return None
            
        key = self._get_key(correlation_id)
        now = datetime.utcnow()
        
        try:
            with self.redis.pipeline() as pipe:
                while True:
                    try:
                        pipe.watch(key)
                        data = self.redis.get(key)
                        if data:
                            state = TaskState.from_dict(json.loads(data))
                            state.container_id = container_id
                            state.container_created_at = now
                            
                            pipe.multi()
                            pipe.set(key, json.dumps(state.to_dict()))
                            pipe.execute()
                            logger.info(f"Successfully set container_id={container_id} for correlation_id={correlation_id}")
                            return state
                        logger.warning(f"No existing state found for correlation_id={correlation_id} when setting container_id")
                        
                        # Create a new state if one doesn't exist
                        state = TaskState(
                            correlation_id=correlation_id,
                            first_seen=now,
                            last_seen=now,
                            container_id=container_id,
                            container_created_at=now
                        )
                        pipe.multi()
                        pipe.set(key, json.dumps(state.to_dict()))
                        pipe.execute()
                        logger.info(f"Created new state with container_id={container_id} for correlation_id={correlation_id}")
                        return state
                    except redis.WatchError:
                        continue
        except Exception as e:
            logger.error(f"Error setting container_id for correlation_id={correlation_id}: {str(e)}")
            return None
    
    def get_container_id(self, correlation_id: str) -> Optional[str]:
        """Get the container ID for a correlation ID."""
        if not correlation_id:
            logger.warning("get_container_id called with empty correlation_id")
            return None
        
        try:    
            state = self.get_state(correlation_id)
            container_id = state.container_id if state else None
            logger.info(f"Retrieved container_id={container_id} for correlation_id={correlation_id}")
            return container_id
        except Exception as e:
            logger.error(f"Error getting container_id for correlation_id={correlation_id}: {str(e)}")
            return None
    
    def has_container(self, correlation_id: str) -> bool:
        """Check if a correlation ID has an associated container."""
        return self.get_container_id(correlation_id) is not None

    def cleanup_old_tasks(self, max_age_hours: int = 24):
        """Remove task states older than max_age_hours with no running tasks."""
        now = datetime.utcnow()
        pattern = f"{self.key_prefix}*"
        
        # Import here to avoid circular imports
        from .container_manager import container_manager
        
        for key in self.redis.scan_iter(pattern):
            data = self.redis.get(key)
            if data:
                state = TaskState.from_dict(json.loads(data))
                # Check if the task has no running tasks and the last task completed more than max_age_hours ago
                # If last_task_completed_at is None, fall back to last_seen
                last_activity = state.last_task_completed_at or state.last_seen
                if ((now - last_activity).total_seconds() > max_age_hours * 3600
                    and state.running_task_count == 0):
                    
                    # If there's a container associated with this correlation ID, remove it
                    if state.container_id:
                        try:
                            container_manager.remove_container(state.correlation_id)
                        except Exception as e:
                            logger.warning(f"Failed to remove container for {state.correlation_id}: {str(e)}")
                    
                    # Delete the task state
                    self.redis.delete(key)
                    logger.info(f"Cleaned up task state for correlation_id={state.correlation_id}")
                    
    def cleanup_inactive_containers(self, inactivity_hours: float = 1.0):
        """Stop and remove containers that have been inactive for more than the specified hours."""
        now = datetime.utcnow()
        pattern = f"{self.key_prefix}*"
        inactivity_seconds = int(inactivity_hours * 3600)
        
        # Import here to avoid circular imports
        from .container_manager import container_manager
        
        inactive_containers = []
        
        for key in self.redis.scan_iter(pattern):
            data = self.redis.get(key)
            if data:
                state = TaskState.from_dict(json.loads(data))
                # Only process states with containers and no running tasks
                if state.container_id and state.running_task_count == 0:
                    # If last_task_completed_at is None, fall back to last_seen
                    last_activity = state.last_task_completed_at or state.last_seen
                    inactive_seconds = (now - last_activity).total_seconds()
                    
                    if inactive_seconds > inactivity_seconds:
                        correlation_id = state.correlation_id
                        logger.info(f"Container for correlation_id={correlation_id} has been inactive for {inactive_seconds/3600:.2f} hours, stopping and removing")
                        
                        try:
                            # First stop the container
                            container_manager.stop_container(correlation_id)
                            # Then remove it
                            container_manager.remove_container(correlation_id)
                            inactive_containers.append(correlation_id)
                        except Exception as e:
                            logger.error(f"Failed to stop/remove container for correlation_id={correlation_id}: {str(e)}")
        
        return inactive_containers

# Global task tracker instance
task_tracker = TaskTracker() 