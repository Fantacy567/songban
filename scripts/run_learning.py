"""Explicit local learning launcher. Configuration checks never open a database.

No .env discovery, identity provisioning, course publishing or model request is
performed by this launcher. Public deployment still requires separate review.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import importlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
from urllib.parse import urlsplit
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.learning_v2 import ReviewQueue, Settings
from app.learning_v2.models import ModelSettings, ReconciliationQueue
from scripts.learning_backup import snapshot

BOOL_FIELDS = frozenset(('enabled', 'course_enabled', 'mock_enabled', 'models_enabled',
    'reports_enabled', 'publication_enabled', 'navigation_enabled', 'studio_enabled', 'catalog_enabled'))
INT_FIELDS = frozenset(('session_seconds', 'browser_seconds'))
TEXT_FIELDS = frozenset(('consent_version', 'recommendation_rule_version'))
QUEUE_FIELDS = frozenset(('relationship_queue', 'learning_queue', 'support_queue', 'report_queue'))
QUEUE_KEYS = frozenset(('reviewer_id', 'display_name', 'due_seconds', 'support_contact_label'))
MODEL_TEXT = frozenset(('config_version', 'base_url', 'api_key_env', 'requested_model', 'pricing_version'))
MODEL_INT = frozenset(('input_unit_rate', 'output_unit_rate', 'max_input_tokens',
    'max_output_tokens', 'reservation_units', 'timeout_seconds', 'lease_seconds'))
MODEL_REQUIRED = MODEL_TEXT | (MODEL_INT - {'timeout_seconds', 'lease_seconds'}) | {'allowed_models', 'reconciliation_queue'}


class ConfigurationError(ValueError):
    """Messages identify schema fields, never values or credentials."""


def _object(value, allowed, label, required=()):
    if type(value) is not dict or set(value) - set(allowed) or set(required) - set(value):
        raise ConfigurationError(f'Invalid or unsupported fields in {label}')
    return value


def _text(value, label, limit=1000):
    if type(value) is not str or not value.strip() or value != value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ConfigurationError(f'Invalid text in {label}')
    return value


def _integer(value, label):
    if type(value) is not int or value <= 0:
        raise ConfigurationError(f'Expected a positive integer in {label}')
    return value


def _strings(value, label):
    if type(value) is not list or len(value) > 30:
        raise ConfigurationError(f'Expected a short string list in {label}')
    values = tuple(_text(v, label, 100) for v in value)
    if len(set(values)) != len(values):
        raise ConfigurationError(f'Duplicate entries in {label}')
    return values


def _queue(value, label, reconciliation=False):
    if value is None and not reconciliation:
        return None
    keys = QUEUE_KEYS | ({'escalation_actor_id'} if reconciliation else set())
    _object(value, keys, label, keys)
    fields = {k: _integer(v, label + '.' + k) if k == 'due_seconds' else _text(v, label + '.' + k) for k, v in value.items()}
    return (ReconciliationQueue if reconciliation else ReviewQueue)(**fields)


def _model(value, environ):
    if value is None:
        return None
    _object(value, MODEL_TEXT | MODEL_INT | {'allowed_models', 'reconciliation_queue'}, 'model_settings', MODEL_REQUIRED)
    fields = {}
    for key, item in value.items():
        if key in MODEL_TEXT:
            fields[key] = _text(item, 'model_settings.' + key)
        elif key in MODEL_INT:
            fields[key] = _integer(item, 'model_settings.' + key)
    variable = fields.pop('api_key_env')
    if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,99}', variable):
        raise ConfigurationError('Invalid model_settings.api_key_env name')
    credential = environ.get(variable)
    if type(credential) is not str or not credential.strip() or any(ord(c) < 32 for c in credential):
        raise ConfigurationError('The explicitly named model credential environment variable is missing or invalid')
    host = urlsplit(fields['base_url']).hostname
    if not host or host.lower() == 'localhost' or host.lower().endswith(('.localhost', '.local')):
        raise ConfigurationError('Model endpoint must name a public HTTPS service')
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ConfigurationError('Model endpoint must name a public HTTPS service')
    except ValueError as exc:
        if isinstance(exc, ConfigurationError):
            raise
        # No DNS or provider request during validation. Deployment must verify DNS.
    fields.update(api_key=credential, allowed_models=_strings(value['allowed_models'], 'allowed_models'),
                  reconciliation_queue=_queue(value['reconciliation_queue'], 'reconciliation_queue', True))
    try:
        return ModelSettings(**fields)
    except ValueError:
        raise ConfigurationError('Incomplete or unsafe model settings') from None


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigurationError('Duplicate JSON fields are not allowed')
        result[key] = value
    return result


def load_settings(config_path, origin, environ=None):
    """Read this one JSON file and the one optional named credential variable."""
    path = Path(config_path)
    if path.stat().st_size > 65536:
        raise ConfigurationError('Configuration is larger than 64 KiB')
    try:
        document = json.loads(path.read_text(encoding='utf-8-sig'), object_pairs_hook=_pairs,
                              parse_constant=lambda _: (_ for _ in ()).throw(ConfigurationError('Non-finite JSON values are not allowed')))
    except (json.JSONDecodeError, UnicodeError):
        raise ConfigurationError('Invalid JSON configuration') from None
    _object(document, {'schema_version', 'settings'}, 'configuration', {'schema_version', 'settings'})
    if type(document['schema_version']) is not int or document['schema_version'] != 1:
        raise ConfigurationError('Unsupported schema_version')
    raw = _object(document['settings'], BOOL_FIELDS | INT_FIELDS | TEXT_FIELDS | QUEUE_FIELDS | {'age_band_options', 'model_settings'}, 'settings')
    fields = {}
    for key, value in raw.items():
        if key in BOOL_FIELDS:
            if type(value) is not bool:
                raise ConfigurationError('Expected a boolean in settings.' + key)
            fields[key] = value
        elif key in INT_FIELDS:
            fields[key] = _integer(value, 'settings.' + key)
        elif key in TEXT_FIELDS:
            fields[key] = _text(value, 'settings.' + key)
        elif key in QUEUE_FIELDS:
            fields[key] = _queue(value, key)
        elif key == 'age_band_options':
            fields[key] = _strings(value, key)
        elif key == 'model_settings':
            fields[key] = _model(value, os.environ if environ is None else environ)
    _text(origin, 'origin')
    try:
        parsed = urlsplit(origin)
        port = parsed.port
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or (port is not None and not 1 <= port <= 65535):
            raise ValueError()
        settings = Settings(**fields, allowed_origins=(origin,), loopback_http=parsed.scheme == 'http')
    except ValueError:
        raise ConfigurationError('Invalid Settings or exact origin; HTTP is permitted only on loopback') from None
    if settings.model_settings is not None and not settings.models_enabled:
        raise ConfigurationError('model_settings requires models_enabled')
    return settings


def _database_path(value):
    path = Path(value)
    if not path.is_absolute() or path.name in ('', '.', '..'):
        raise ConfigurationError('An explicit absolute database file path is required')
    return path.resolve()


def bind_local(origin, host):
    """Reserve before any database or factory work; keep the socket until shutdown."""
    parsed = urlsplit(origin)
    if host not in ('127.0.0.1', '::1') or parsed.scheme != 'http' or parsed.hostname not in (host, 'localhost') or parsed.port is None or parsed.port < 1024:
        raise ConfigurationError('Running requires an explicit HTTP loopback origin with port >= 1024 and matching loopback host; public deployment is manual')
    listener = socket.socket(socket.AF_INET6 if host == '::1' else socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        listener.bind((host, parsed.port))
        listener.listen(2048)
        listener.setblocking(False)
        return listener
    except BaseException:
        listener.close()
        raise


def backup_before_start(database, backup_directory):
    if not database.exists():
        if not database.parent.is_dir():
            raise ConfigurationError('The explicit database parent directory must already exist')
        return None
    if not database.is_file():
        raise ConfigurationError('Database target is not a file')
    if backup_directory is None:
        raise ConfigurationError('An existing database requires an explicit backup-directory')
    destination = Path(backup_directory)
    if not destination.is_absolute():
        raise ConfigurationError('Backup directory must be absolute and outside the repository')
    destination = destination.resolve()
    if destination == ROOT or ROOT in destination.parents or not destination.is_dir():
        raise ConfigurationError('Backup directory must already exist outside the repository')
    target = destination / ('learning-before-start-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '-' + uuid.uuid4().hex[:8] + '.sqlite3')
    return snapshot(database, target)


def create_application(database, settings):
    # Disable implicit legacy provider discovery in this process, not the user's
    # parent shell. The explicit learning credential is already in ModelSettings.
    from app.environment import ENV_KEYS
    for key in tuple(os.environ):
        if key in ENV_KEYS or key.startswith(('SONGBAN_', 'SONGBAI_', 'SMTP_', 'ALIYUN_', 'DEEPSEEK_', 'DASHSCOPE_')):
            os.environ.pop(key, None)
    # main has a legacy module-level app. Import it against a disposable DB;
    # its factory closes each initialization connection before returning.
    with tempfile.TemporaryDirectory(prefix='songban-learning-import-') as folder:
        with patch.dict(os.environ, {'DATABASE_PATH': str(Path(folder) / 'import.sqlite3')}), patch('app.environment.load_env'):
            factory = importlib.import_module('app.main').create_app
    return factory(db_path=database, core_only=True, learning_settings=settings)


def serve(application, listener):
    import uvicorn
    config = uvicorn.Config(application, log_level='warning', access_log=False)
    uvicorn.Server(config).run(sockets=[listener])


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--config', required=True, type=Path)
    result.add_argument('--database', required=True)
    result.add_argument('--origin', required=True, help='Exact origin, including explicit port for local execution')
    result.add_argument('--host', default='127.0.0.1', choices=('127.0.0.1', '::1'))
    result.add_argument('--backup-directory', type=Path, help='Existing absolute directory outside the repository; required for an existing database')
    result.add_argument('--check', action='store_true', help='Validate only; no DB, factory, .env, bind, DNS, or provider access')
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        database = _database_path(args.database)
        settings = load_settings(args.config, args.origin)
        if args.check:
            print(json.dumps({'configuration': 'valid', 'database_opened': False, 'port_reserved': False,
                              'provider_contacted': False, 'business_readiness': 'not_verified',
                              'public_deployment': 'requires_separate_review',
                              'live_model_configured': settings.model_settings is not None}))
            return 0
        with closing(bind_local(args.origin, args.host)) as listener:
            backup = backup_before_start(database, args.backup_directory)
            application = create_application(database, settings)
            print(json.dumps({'origin': args.origin, 'database': str(database), 'backup': backup['destination'] if backup else None,
                              'learning_url': args.origin + '/learning-prep#/learn/first',
                              'business_readiness': 'not_verified', 'provisioned_by_launcher': False}, ensure_ascii=False), flush=True)
            serve(application, listener)
        return 0
    except ConfigurationError as exc:
        print('Configuration rejected: ' + str(exc), file=sys.stderr)
    except Exception as exc:
        # Library errors may include a URL or credential; never echo their values.
        print('Learning launch stopped (' + type(exc).__name__ + '). No configuration secrets are printed; verify explicit paths, port availability and backup integrity.', file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
