"""Temporary, synthetic-only integration server. No email/provider calls allowed."""
import argparse
from dataclasses import replace
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8902)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Use a local unprivileged port')
    from tests.test_platform_http import PlatformHttpTests
    from app.server_admin import AdminSettings
    from app.creative_studio.harness import HarnessRunner
    import uvicorn
    fixture = PlatformHttpTests('runTest')
    try:
        fixture.setUp()
        origin = 'http://127.0.0.1:' + str(args.port)
        learning = replace(fixture.settings, allowed_origins=(origin,), loopback_http=True,
                           navigation_enabled=True, studio_enabled=True, catalog_enabled=True,
                           course_enabled=True, mock_enabled=True)
        platform = replace(fixture.platform_settings, navigation_enabled=True, creative_studio_enabled=True)
        app = fixture.factory(fixture.path, core_only=True, enforce_journey=False,
                              learning_settings=learning, platform_settings=platform,
                              server_admin_settings=AdminSettings(allowed_emails=('parent-a@example.test',),
                                  secret_dir=Path(fixture.tmp.name)/'admin-private'),
                              studio_runner=HarnessRunner())
        app.state.learning_v2.clock = lambda: fixture.now[0]
        print('Synthetic creative QA: '+origin+'/#/learn/create', flush=True)
        uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')
    finally:
        fixture.doCleanups()


if __name__ == '__main__':
    main()
