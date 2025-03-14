import docker
import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any, List

from .task_tracker import task_tracker

logger = logging.getLogger(__name__)

class ContainerManager:
    """Manages Docker containers for task execution."""
    
    def __init__(self):
        """Initialize Docker client."""
        try:
            # Try to connect to Docker daemon
            self.client = docker.from_env()
            self._docker_available = True
            logger.info("Successfully connected to Docker daemon")
        except Exception as e:
            self._docker_available = False
            logger.error(f"Failed to connect to Docker daemon: {str(e)}")
            logger.error("Container functionality will be disabled")
            
        self.image_tag = "sandbox"
        self.dockerfile = "Dockerfile.sandbox"
    
    def _check_docker_available(self):
        """Check if Docker is available and raise an exception if not."""
        if not self._docker_available:
            raise RuntimeError("Docker is not available. Container functionality is disabled.")
    
    def build_image(self) -> None:
        """Build the sandbox Docker image."""
        self._check_docker_available()
        logger.info(f"Building image {self.image_tag} from {self.dockerfile}")
        try:
            self.client.images.build(
                path=".", 
                tag=self.image_tag, 
                dockerfile=self.dockerfile
            )
            logger.info(f"Successfully built image {self.image_tag}")
        except Exception as e:
            logger.error(f"Failed to build image {self.image_tag}: {str(e)}")
            raise
    
    def create_container(self, correlation_id: str) -> str:
        """
        Create a new container for the given correlation ID.
        
        Args:
            correlation_id: Unique identifier for the task chain/user
            
        Returns:
            Container ID
        """
        self._check_docker_available()
        
        # Check if we already have a container for this correlation ID
        existing_container_id = task_tracker.get_container_id(correlation_id)
        if existing_container_id:
            try:
                # Check if the container exists and is running
                container = self.client.containers.get(existing_container_id)
                if container.status == "running":
                    logger.info(f"Reusing existing container {existing_container_id} for correlation_id={correlation_id}")
                    return existing_container_id
                else:
                    logger.info(f"Container {existing_container_id} exists but is not running. Starting it...")
                    container.start()
                    return existing_container_id
            except docker.errors.NotFound:
                logger.warning(f"Container {existing_container_id} not found for correlation_id={correlation_id}. Creating a new one.")
                # Container doesn't exist anymore, create a new one
                pass
            except Exception as e:
                logger.error(f"Error checking container {existing_container_id}: {str(e)}")
                raise
        
        # Ensure the image exists
        try:
            self.client.images.get(self.image_tag)
        except docker.errors.ImageNotFound:
            self.build_image()
        except Exception as e:
            logger.error(f"Error checking image {self.image_tag}: {str(e)}")
            raise
        
        # Create a new container
        try:
            logger.info(f"Creating new container for correlation_id={correlation_id}")
            container = self.client.containers.run(
                self.image_tag,
                entrypoint="",
                tty=True,  # allocating a pseudo-TTY to keep the container alive
                detach=True,
                # Resource constraints
                mem_limit="4g",
                cpu_period=100_000,
                cpu_quota=200_000,
                cpu_shares=512
            )
            
            # Store the container ID
            task_tracker.set_container_id(correlation_id, container.id)
            logger.info(f"Created container {container.id} for correlation_id={correlation_id}")
            
            return container.id
        except Exception as e:
            logger.error(f"Failed to create container for correlation_id={correlation_id}: {str(e)}")
            raise
    
    def get_container(self, correlation_id: str) -> Optional[docker.models.containers.Container]:
        """
        Get the container for the given correlation ID.
        
        Args:
            correlation_id: Unique identifier for the task chain/user
            
        Returns:
            Container object or None if not found
        """
        self._check_docker_available()
        
        container_id = task_tracker.get_container_id(correlation_id)
        if not container_id:
            return None
        
        try:
            return self.client.containers.get(container_id)
        except docker.errors.NotFound:
            logger.warning(f"Container {container_id} not found for correlation_id={correlation_id}")
            return None
        except Exception as e:
            logger.error(f"Error getting container {container_id}: {str(e)}")
            raise
    
    def ensure_container(self, correlation_id: str) -> docker.models.containers.Container:
        """
        Ensure a container exists for the given correlation ID.
        If it doesn't exist, create it.
        
        Args:
            correlation_id: Unique identifier for the task chain/user
            
        Returns:
            Container object
        """
        self._check_docker_available()
        
        container = self.get_container(correlation_id)
        if container:
            # Check if the container is running
            if container.status != "running":
                logger.info(f"Starting container {container.id} for correlation_id={correlation_id}")
                try:
                    container.start()
                except Exception as e:
                    logger.error(f"Failed to start container {container.id}: {str(e)}")
                    # If we can't start the container, create a new one
                    container_id = self.create_container(correlation_id)
                    return self.client.containers.get(container_id)
            return container
        
        # Create a new container
        container_id = self.create_container(correlation_id)
        return self.client.containers.get(container_id)
    
    def exec_command(self, correlation_id: str, command: str) -> Dict[str, Any]:
        """
        Execute a command in the container for the given correlation ID.
        
        Args:
            correlation_id: Unique identifier for the task chain/user
            command: Command to execute
            
        Returns:
            Dictionary with command output
        """
        self._check_docker_available()
        
        container = self.ensure_container(correlation_id)
        
        logger.info(f"Executing command in container {container.id} for correlation_id={correlation_id}: {command}")
        try:
            result = container.exec_run(command)
            
            return {
                "exit_code": result.exit_code,
                "output": result.output.decode('utf-8') if result.output else "",
                "container_id": container.id,
                "correlation_id": correlation_id,
                "command": command,
                "success": result.exit_code == 0
            }
        except Exception as e:
            logger.error(f"Failed to execute command in container {container.id}: {str(e)}")
            return {
                "exit_code": 1,
                "output": f"Error executing command: {str(e)}",
                "container_id": container.id,
                "correlation_id": correlation_id,
                "command": command,
                "success": False
            }
    
    def stop_container(self, correlation_id: str) -> bool:
        """
        Stop the container for the given correlation ID.
        
        Args:
            correlation_id: Unique identifier for the task chain/user
            
        Returns:
            True if the container was stopped, False otherwise
        """
        self._check_docker_available()
        
        container = self.get_container(correlation_id)
        if not container:
            return False
        
        logger.info(f"Stopping container {container.id} for correlation_id={correlation_id}")
        try:
            container.stop()
            return True
        except Exception as e:
            logger.error(f"Failed to stop container {container.id}: {str(e)}")
            return False
    
    def remove_container(self, correlation_id: str) -> bool:
        """
        Remove the container for the given correlation ID.
        
        Args:
            correlation_id: Unique identifier for the task chain/user
            
        Returns:
            True if the container was removed, False otherwise
        """
        self._check_docker_available()
        
        container = self.get_container(correlation_id)
        if not container:
            return False
        
        logger.info(f"Removing container {container.id} for correlation_id={correlation_id}")
        try:
            container.remove(force=True)
            return True
        except Exception as e:
            logger.error(f"Failed to remove container {container.id}: {str(e)}")
            return False

# Global container manager instance
container_manager = ContainerManager()