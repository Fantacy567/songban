# Copyright (c) 2026 2292576833, Fantacy567, andorwu5-dev. See COPYRIGHT.md.
"""Private course conversations and evidence records; importing performs no I/O."""
from .routes import register_workbench
from .service import WorkbenchService

__all__ = ['register_workbench', 'WorkbenchService']
