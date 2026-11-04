"""Explicit local server for creation and administration; no automatic grants/calls."""
import argparse
from contextlib import closing
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_learning import (ConfigurationError, _database_path, _pairs, bind_local,
                                  backup_before_start, load_settings, serve)
from app.server_admin import AdminSettings
from app.platform_v1 import PlatformSettings


def load_admin(path):
    value = json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=_pairs)
    if (type(value) is not dict or set(value) != {'allowed_emails','secret_dir','enabled'} or
        type(value['enabled']) is not bool or type(value['allowed_emails']) is not list or
        len(value['allowed_emails']) > 20 or type(value['secret_dir']) is not str):
        raise ConfigurationError('Invalid administrator configuration fields')
    from app.email_delivery import normalize_email
    emails = []
    for email in value['allowed_emails']:
        if not isinstance(email, str):
            raise ConfigurationError('Invalid administrator email')
        try:
            normalized = normalize_email(email)
        except (ValueError, TypeError):
            raise ConfigurationError('Invalid administrator email') from None
        if not normalized or normalized in emails:
            raise ConfigurationError('Invalid or duplicate administrator email')
        emails.append(normalized)
    directory = Path(value['secret_dir'])
    if not directory.is_absolute() or directory.resolve() == ROOT or ROOT in directory.resolve().parents:
        raise ConfigurationError('Administrator secret storage must be absolute and outside the repository')
    return AdminSettings(allowed_emails=tuple(emails), secret_dir=directory.resolve(), enabled=value['enabled'])


def application(database, learning, admin, legacy_env=None):
    # Loading existing mail/model settings is an explicit operator choice. This
    # does not import them into the new admin provider store or grant a budget.
    from app.environment import load_env
    if legacy_env is not None:
        load_env(Path(legacy_env).resolve(strict=True))
    with tempfile.TemporaryDirectory(prefix='songban-studio-import-') as folder:
        with patch.dict(os.environ, {'DATABASE_PATH':str(Path(folder)/'import.sqlite3')}), patch('app.environment.load_env'):
            factory = importlib.import_module('app.main').create_app
    return factory(database, core_only=True, learning_settings=learning,
        platform_settings=PlatformSettings(enabled=True, navigation_enabled=True, creative_studio_enabled=True),
        server_admin_settings=admin)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--learning-config', type=Path, required=True)
    parser.add_argument('--admin-config', type=Path, required=True)
    parser.add_argument('--database', required=True)
    parser.add_argument('--origin', required=True)
    parser.add_argument('--backup-directory', type=Path)
    parser.add_argument('--legacy-env', type=Path, help='Explicit existing mail/legacy config file; never printed')
    parser.add_argument('--check', action='store_true', help='Check configuration without opening a DB or contacting a provider')
    args = parser.parse_args(argv)
    try:
        database = _database_path(args.database)
        learning = load_settings(args.learning_config, args.origin)
        admin = load_admin(args.admin_config)
        if args.check:
            print(json.dumps({'configuration':'valid','database_opened':False,'provider_contacted':False,
                              'administrator_count':len(admin.allowed_emails)}))
            return 0
        with closing(bind_local(args.origin, '127.0.0.1')) as listener:
            backup = backup_before_start(database, args.backup_directory)
            app = application(database, learning, admin, args.legacy_env)
            print(json.dumps({'origin':args.origin,'admin_url':args.origin+'/server-admin',
                              'backup':backup['destination'] if backup else None,
                              'model_verification':'not_run','provisioned_accounts':False}), flush=True)
            serve(app, listener)
        return 0
    except Exception as error:
        print('Studio launch stopped ('+type(error).__name__+'). Check explicit configuration, database and port; secrets are not printed.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
