import logging
import asyncio
import uuid
from app.container_manager import container_manager
from app.task_tracker import task_tracker

logging.basicConfig(level=logging.INFO)

async def test_container_management():
    # Generate a unique correlation ID for testing
    correlation_id = "a78c2b54-b41e-4bff-9442-f25c4bf8b3b4"
    logging.info(f"Testing with correlation_id: {correlation_id}")
    
    try:
        # Create a container for the correlation ID
        logging.info("Creating container...")
        container_id = container_manager.create_container(correlation_id)
        logging.info(f"Container created with ID: {container_id}")
        
        # Verify the container ID is stored in the task tracker
        stored_container_id = task_tracker.get_container_id(correlation_id)
        logging.info(f"Container ID from task tracker: {stored_container_id}")
        assert stored_container_id == container_id, "Container ID mismatch"
        
        # Execute a command in the container
        logging.info("Executing command in container...")
        result = container_manager.exec_command(correlation_id, "echo 'Hello from container'")
        logging.info(f"Command result: {result}")
        assert result["success"], "Command execution failed"
        assert "Hello from container" in result["output"], "Unexpected command output"
        
        # Execute another command to verify container reuse
        logging.info("Executing another command in the same container...")
        result = container_manager.exec_command(correlation_id, "uname -a")
        logging.info(f"Command result: {result}")
        assert result["success"], "Command execution failed"
        
        # Test git command
        logging.info("Testing git command...")
        result = container_manager.exec_command(correlation_id, "git --version")
        logging.info(f"Git version: {result['output']}")
        assert result["success"], "Git command failed"
        
        # Test Python command
        logging.info("Testing Python command...")
        result = container_manager.exec_command(correlation_id, "python --version")
        logging.info(f"Python version: {result['output']}")
        assert result["success"], "Python command failed"
        
        # Stop the container
        logging.info("Stopping container...")
        stopped = container_manager.stop_container(correlation_id)
        assert stopped, "Failed to stop container"
        
        # Remove the container
        logging.info("Removing container...")
        #removed = container_manager.remove_container(correlation_id)
        #assert removed, "Failed to remove container"
        
        logging.info("All tests passed!")
        
    except Exception as e:
        logging.error(f"Test failed: {str(e)}")
        # Cleanup in case of failure
        container_manager.remove_container(correlation_id)
        raise

if __name__ == "__main__":
    asyncio.run(test_container_management()) 