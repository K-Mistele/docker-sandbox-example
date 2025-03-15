# Docker Sandbox Example

A containerized sandbox environment for safely executing code with automatic resource management. This system provides isolated Docker containers for running tasks, with automatic cleanup of inactive containers.

## Overview

This repository demonstrates a pattern for creating isolated sandbox environments using Docker containers. Each sandbox is:

- **Isolated**: Code runs in a separate Docker container for each `correlation_id` (recommended to use a user ID)
- **Resource-constrained**: Containers have CPU and memory limits
- **Automatically managed**: Inactive containers are cleaned up after 1 hour
- **Task-tracked**: All operations are tracked with correlation IDs

## Key Features

- 🔒 Secure execution of untrusted code in isolated containers
- 🔄 Automatic container lifecycle management
- 📊 Task tracking and correlation
- 🧵 Asynchronous task execution with Celery
- 🧹 Automatic cleanup of inactive containers
- 📦 Git repository cloning and dependency installation

## Architecture

The system consists of the following components:

- **Container Manager**: Manages Docker container lifecycle
- **Task Tracker**: Tracks task execution and container state
- **Celery Tasks**: Asynchronous task execution
- **Celery Beat**: Scheduled tasks for container cleanup

## Prerequisites

- Docker and Docker Compose
- Python 3.12+
- RabbitMQ
- Redis

## Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/docker-sandbox-example.git
   cd docker-sandbox-example
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   uv sync
   ```

3. Create a `.env` file with the following variables:
   ```
   RABBITMQ_DEFAULT_USER=your_rabbitmq_user
   RABBITMQ_DEFAULT_PASS=your_rabbitmq_password
   ```

4. Start the required services (redis, RMQ):
   ```bash
   docker-compose up
   ```

## Running the Application

### Start the Celery Worker and Beat Scheduler

To run both the Celery worker and beat scheduler (for scheduled tasks):

```bash
# Terminal 1: Run the worker
celery -A app.celery_app worker --loglevel=info

# Terminal 2: Run the beat scheduler
celery -A app.celery_app beat --loglevel=info
```

Alternatively, for development, you can run both in a single process:

```bash
celery -A app.celery_app worker -B --loglevel=info
```

Run it with hot-reloading

```shell
watchmedo auto-restart --directory ./app --pattern="*.py" --recursive -- celery -A app.celery_app worker -B --loglevel=debug
```

### Run the Example

```bash
python main.py
```

## Usage Examples

### Expected module structure
This application expects python modules to be structured like Naptha modules. 

For example, for a repo `https://github.com/k-mistele/example_python_module` you should have the following repo structure:

```
- pyproject.toml
- uv.lock
- example_python_module/
  |- __init__.py
  |- run.py 
```

`run.py` Should be the module's entrypoint, and should run project (e.g. `if __name__ == "__main__":` )

### Clone and Install a Git Repository

```python
from app.tasks import clone_and_install_package
import uuid

correlation_id = str(uuid.uuid4())
result = clone_and_install_package.delay(correlation_id, "https://github.com/example/repo.git")
print(result.get())
```

### Execute a Module in the Sandbox

```python
from app.tasks import execute_module
import uuid

correlation_id = str(uuid.uuid4())
result = execute_module.delay(correlation_id, "module_name", "arg1", "arg2")
print(result.get())
```

### Execute a Command in the Sandbox

```python
from app.tasks import execute_command
import uuid

correlation_id = str(uuid.uuid4())
result = execute_command.delay(correlation_id, "ls -la")
print(result.get())
```

## Container Lifecycle

Containers are automatically managed:

1. Created when needed for a task
2. Reused for subsequent tasks with the same correlation ID
3. Automatically stopped and removed after 1 hour of inactivity
4. Cleaned up when the correlation ID is no longer needed

## Testing

Run the tests with:

```shell
uv run test_module_tasks.py
```

## License

This project is licensed under the terms of the license included in the repository.