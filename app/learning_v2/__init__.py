"""Opt-in learning identity module. Importing this package does no I/O."""

from .service import LearningV2, Settings, ReviewQueue
from .routes import register_learning_v2

__all__ = ["LearningV2", "Settings", "ReviewQueue", "register_learning_v2"]
