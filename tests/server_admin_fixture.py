"""Disposable localhost:8904 fixture. Synthetic users/keys, mocked image transport."""
from dataclasses import replace
from pathlib import Path
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    # Check before creating any temporary state or starting a service.
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 8904))
    from tests.test_server_admin_unknown import AdminUnknownTests
    from app.server_admin import AdminSettings
    import uvicorn
    fixture = AdminUnknownTests('runTest')
    try:
        fixture.setUp()
        origin = 'http://127.0.0.1:8904'
        learning = replace(fixture.settings, allowed_origins=(origin,), loopback_http=True,
                           navigation_enabled=True, studio_enabled=True, catalog_enabled=True,
                           course_enabled=True, mock_enabled=True)
        platform = replace(fixture.platform_settings, navigation_enabled=True, creative_studio_enabled=True)
        def never_call(payload):
            raise AssertionError('This HTTP fixture must not call a text model')
        app = fixture.factory(fixture.path, core_only=True, enforce_journey=False,
            learning_settings=learning, platform_settings=platform,
            server_admin_settings=AdminSettings(allowed_emails=('parent-a@example.test',),
                                                secret_dir=Path(fixture.tmp.name)/'admin-private'),
            studio_runner=never_call)
        app.state.learning_v2.clock = lambda: fixture.now[0]
        print('Synthetic administrator fixture ready on '+origin, flush=True)
        uvicorn.run(app, host='127.0.0.1', port=8904, log_level='warning')
    finally:
        fixture.doCleanups()


if __name__ == '__main__':
    main()
