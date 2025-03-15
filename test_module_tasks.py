import logging 
import asyncio
from app.tasks import clone_and_install_package, execute_module
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# Import Celery app and tasks after environment is configured
from app.celery_app import app
from app.task_tracker import task_tracker

async def run_celery_task(task, correlation_id: str, *args, **kwargs):
    """Run a Celery task asynchronously using a thread pool."""
    loop = asyncio.get_running_loop()
    # Start the task
    result = task.delay(correlation_id, *args, **kwargs)
    # Wait for the result in a thread pool
    with ThreadPoolExecutor() as pool:
        return await loop.run_in_executor(pool, result.get)



correlation_id = "a78c2b54-b41e-4bff-9442-f25c4bf8b3bd"

async def test_install_module():
    result = await run_celery_task(clone_and_install_package, correlation_id, "https://github.com/k-mistele/example_python_package")
    logging.info(f"Result: {result}")

async def test_execute_module():
    result = await run_celery_task(execute_module, correlation_id, "example_python_package")
    logging.info(f"Result: {result}")

async def main():
    await test_install_module()
    await test_execute_module()

if __name__ == "__main__":
    asyncio.run(main())