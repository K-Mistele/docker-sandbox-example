from pathlib import Path
from dotenv import load_dotenv
import asyncio
from functools import partial
from concurrent.futures import ThreadPoolExecutor
import uuid

load_dotenv()

# Import Celery app and tasks after environment is configured
from app.celery_app import app
from app.tasks import debug_task, clone_and_install_package, execute_module
from app.task_tracker import task_tracker

async def run_celery_task(task, correlation_id: str, *args, **kwargs):
    """Run a Celery task asynchronously using a thread pool."""
    loop = asyncio.get_running_loop()
    # Start the task
    result = task.delay(correlation_id, *args, **kwargs)
    # Wait for the result in a thread pool
    with ThreadPoolExecutor() as pool:
        return await loop.run_in_executor(pool, result.get)

correlation_id = '5d1eaf52-3f5c-4971-ba5d-096668be9ab5'

async def main():
    # Generate a unique correlation ID for this process
    print(f"Starting process with correlation_id={correlation_id}")
    
    # Run a debug task
    print("Submitting debug task...")
    result = await run_celery_task(debug_task, correlation_id, "Testing RabbitMQ configuration")
    print("Task completed:", result)
    
    # Check the task state
    state = task_tracker.get_state(correlation_id)
    if state:
        print(f"Task history: first seen at {state.first_seen}, total tasks: {len(state.task_history)}")

if __name__ == "__main__":
    asyncio.run(main())
