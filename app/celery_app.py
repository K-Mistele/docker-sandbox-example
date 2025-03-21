from celery import Celery
import os
from pathlib import Path
from dotenv import load_dotenv
import docker
from datetime import timedelta

client = docker.from_env()
client.images.build(path='.', tag='sandbox', dockerfile='Dockerfile.sandbox') # make sure the sandbox image is available

# Load environment variables from .env file in project root
load_dotenv()

# Get RabbitMQ credentials from environment
RABBITMQ_USER = os.getenv('RABBITMQ_DEFAULT_USER')
RABBITMQ_PASS = os.getenv('RABBITMQ_DEFAULT_PASS')
RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')

# Configure the Celery instance with RabbitMQ broker and RPC backend
app = Celery(
    'tasks',
    # RabbitMQ broker URL with credentials
    broker=f'amqp://{RABBITMQ_USER}:{RABBITMQ_PASS}@{RABBITMQ_HOST}:5672/',
    # Use RPC backend (which uses AMQP/RabbitMQ)
    backend=f'rpc://{RABBITMQ_USER}:{RABBITMQ_PASS}@{RABBITMQ_HOST}:5672/',
)

# Optional configurations
app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    # RPC backend specific settings
    result_expires=3600,  # Results expire in 1 hour
)

# Configure the Celery beat schedule
app.conf.beat_schedule = {
    'cleanup-inactive-containers': {
        'task': 'app.tasks.cleanup_inactive_containers',
        'schedule': timedelta(minutes=15),  # Run every 15 minutes
        'kwargs': {'inactivity_hours': 0.5},  # 30 minutes inactivity threshold
    },
}

# Import tasks so they are registered with Celery
from app.tasks import *  # noqa 