"""Explicitly installed server administration; importing does not read secrets."""
from .service import AdminSettings, AdminService
from .routes import register_server_admin

__all__ = ['AdminSettings', 'AdminService', 'register_server_admin']
