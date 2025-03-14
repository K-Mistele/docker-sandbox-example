import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any
from functools import wraps

from celery import shared_task
from celery.utils.log import get_task_logger

import docker
from .task_tracker import task_tracker
from .container_manager import container_manager

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
    Clone a git repository and install its dependencies using uv in a container.
    
    Args:
        correlation_id: Unique identifier for the task chain/user
        git_url: URL of the git repository
    """
    try:
        # Ensure we have a container for this correlation ID
        container_manager.ensure_container(correlation_id)

        # Mark that this correlation ID has a sandbox
        task_tracker.set_sandbox_state(correlation_id, True)
        repo_dir = git_url.split('/')[-1].split('.')[0]

        # Clone the repository in the container
        logger.info(f"Cloning repository from {git_url} for correlation_id={correlation_id}")
        clone_result = container_manager.exec_command(
            correlation_id, 
            f"git clone {git_url} {repo_dir}"
        )
        if not clone_result["success"]:
            raise Exception(f"Failed to clone repository: {clone_result['output']}")
        
        # Install package dependencies using uv
        logger.info(f"Installing package dependencies with uv for correlation_id={correlation_id}")
        install_result = container_manager.exec_command(
            correlation_id,
            f"cd {repo_dir} && uv sync"
        )
        if not install_result["success"]:
            raise Exception(f"Failed to install dependencies: {install_result['output']}")
        
        return {
            "status": "success",
            "correlation_id": correlation_id,
            "message": f"Successfully installed package from {git_url}",
            "package_dir": repo_dir,
            "container_id": task_tracker.get_container_id(correlation_id)
        }
            
    except Exception as e:
        logger.error(f"Failed to install package for correlation_id={correlation_id}: {str(e)}")
        raise

@shared_task(bind=True)
@track_task
def execute_module(self, correlation_id: str, module_name: str, *args) -> dict:
    """
    Execute a Python module in the container.
    
    Args:
        correlation_id: Unique identifier for the task chain/user
        module_name: Name of the module to execute
        args: Additional arguments to pass to the module
    """
    try:
        # Ensure we have a container for this correlation ID
        container = container_manager.ensure_container(correlation_id)
        
        # Build the command
        cmd = ["uv", "run", "python", "-m", module_name] + list(args)
        command = " ".join(cmd)
        
        logger.info(f"Executing module {module_name} with args: {args} for correlation_id={correlation_id}")
        result = container_manager.exec_command(correlation_id, command)
        
        if not result["success"]:
            logger.error(f"Module execution failed: {result['output']}")
            raise Exception(f"Module execution failed with exit code {result['exit_code']}: {result['output']}")
        
        return {
            "status": "success",
            "correlation_id": correlation_id,
            "output": result["output"],
            "module": module_name,
            "args": args,
            "container_id": container.id
        }
        
    except Exception as e:
        logger.error(f"Failed to execute module for correlation_id={correlation_id}: {str(e)}")
        raise

@shared_task(bind=True)
@track_task
def execute_command(self, correlation_id: str, command: str) -> dict:
    """
    Execute a shell command in the container.
    
    Args:
        correlation_id: Unique identifier for the task chain/user
        command: Shell command to execute
    """
    try:
        # Ensure we have a container for this correlation ID
        container_manager.ensure_container(correlation_id)
        
        logger.info(f"Executing command for correlation_id={correlation_id}: {command}")
        result = container_manager.exec_command(correlation_id, command)
        
        if not result["success"]:
            logger.error(f"Command execution failed: {result['output']}")
            raise Exception(f"Command execution failed with exit code {result['exit_code']}: {result['output']}")
        
        return {
            "status": "success",
            "correlation_id": correlation_id,
            "output": result["output"],
            "command": command,
            "container_id": result["container_id"]
        }
        
    except Exception as e:
        logger.error(f"Failed to execute command for correlation_id={correlation_id}: {str(e)}")
        raise 