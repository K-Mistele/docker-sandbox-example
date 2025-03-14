import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
from functools import wraps

from celery import shared_task
from celery.utils.log import get_task_logger

import docker
from .task_tracker import task_tracker

logger = get_task_logger(__name__)

def track_task(task_func):
    """Decorator to track task execution with correlation ID."""
    @wraps(task_func)  # Preserve the original function's metadata
    def wrapper(self, correlation_id: str, *args, **kwargs):
        if not correlation_id:
            raise ValueError("correlation_id is required")
        
        # Register task start
        state = task_tracker.register_task(correlation_id, task_func.__name__)
        logger.info(f"Task {task_func.__name__} started for correlation_id={correlation_id} (seen {state.running_task_count} times)")
        
        try:
            result = task_func(self, correlation_id, *args, **kwargs)
            return result
        finally:
            # Register task completion
            task_tracker.finish_task(correlation_id)
            logger.info(f"Task {task_func.__name__} completed for correlation_id={correlation_id}")
    
    return wrapper

@shared_task(bind=True)
@track_task
def debug_task(self, correlation_id: str, message: str = "Debug message", level: str = "info") -> dict:
    """
    Task for debugging and testing Celery configuration.
    
    Args:
        correlation_id: Unique identifier for the task chain/user
        message: Message to log
        level: Log level (debug, info, warning, error)
    """
    log_func = getattr(logger, level.lower(), logger.info)
    log_func(f"Task ID: {self.request.id}")
    log_func(f"Correlation ID: {correlation_id}")
    log_func(f"Message: {message}")
    
    state = task_tracker.get_state(correlation_id)
    
    return {
        "status": "success",
        "task_id": self.request.id,
        "correlation_id": correlation_id,
        "message": message,
        "level": level,
        "task_history": {
            "first_seen": state.first_seen.isoformat() if state else None,
            "total_tasks": len(state.task_history) if state else 1,
            "has_sandbox": state.has_sandbox if state else False
        }
    }

@shared_task(bind=True)
@track_task
def clone_and_install_package(self, correlation_id: str, git_url: str) -> dict:
    """
    Clone a git repository and install its dependencies using uv.
    
    Args:
        correlation_id: Unique identifier for the task chain/user
        git_url: URL of the git repository
    """
    try:
        # Create a temporary directory for cloning
        with tempfile.TemporaryDirectory() as temp_dir:
            logger.info(f"Cloning repository from {git_url} for correlation_id={correlation_id}")
            subprocess.run(
                ["git", "clone", git_url, temp_dir],
                check=True,
                capture_output=True,
                text=True
            )
            
            # Install package dependencies using uv
            logger.info(f"Installing package dependencies with uv for correlation_id={correlation_id}")
            subprocess.run(
                ["uv", "sync"],
                cwd=temp_dir,
                check=True,
                capture_output=True,
                text=True
            )
            
            # Mark that this correlation ID has a sandbox
            task_tracker.set_sandbox_state(correlation_id, True)
            
            return {
                "status": "success",
                "correlation_id": correlation_id,
                "message": f"Successfully installed package from {git_url}",
                "package_dir": temp_dir
            }
            
    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed for correlation_id={correlation_id}: {e.cmd}")
        logger.error(f"Output: {e.output}")
        raise
    except Exception as e:
        logger.error(f"Failed to install package for correlation_id={correlation_id}: {str(e)}")
        raise

@shared_task(bind=True)
@track_task
def execute_module(self, correlation_id: str, module_name: str, *args) -> dict:
    """
    Execute a Python module using the current Python environment.
    
    Args:
        correlation_id: Unique identifier for the task chain/user
        module_name: Name of the module to execute
        args: Additional arguments to pass to the module
    """
    try:
        logger.info(f"Executing module {module_name} with args: {args} for correlation_id={correlation_id}")
        cmd = ["python", "-m", module_name] + list(args)
        
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True
        )
        
        return {
            "status": "success",
            "correlation_id": correlation_id,
            "output": result.stdout,
            "module": module_name,
            "args": args
        }
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Module execution failed for correlation_id={correlation_id}: {e.cmd}")
        logger.error(f"Output: {e.output}")
        raise
    except Exception as e:
        logger.error(f"Failed to execute module for correlation_id={correlation_id}: {str(e)}")
        raise 