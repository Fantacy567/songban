"""Opt-in platform layer; existing learning and competition remain authoritative."""
from .service import PlatformSettings, PlatformService
from .routes import register_platform

__all__ = ['PlatformSettings', 'PlatformService', 'register_platform']
