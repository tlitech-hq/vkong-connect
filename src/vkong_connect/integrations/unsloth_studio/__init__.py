"""Unsloth Studio integration: the "Train on VKong" service and its routes.

Importing this package does not import FastAPI; ``create_router`` does.
"""

from .router import create_router
from .service import RemoteTrainingService, portable_worker_config

__all__ = ["RemoteTrainingService", "create_router", "portable_worker_config"]
