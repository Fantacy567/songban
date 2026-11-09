"""Temporary learning-entry HTTP fixture; never load private env or call providers."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8903)
    parser.add_argument('--mode', choices=('demo', 'account'), required=True)
    parser.add_argument('--legacy-course', action='store_true')
    parser.add_argument('--metadata-output', type=Path)
    args = parser.parse_args()
    if args.port in (8894, 8895) or not 1024 <= args.port <= 65535:
        parser.error('Use a temporary unprivileged port, never 8894/8895')
    import uvicorn
    from app.platform_v1 import PlatformSettings
    from app.server_admin import AdminSettings, register_server_admin
    from tests.test_unified_demo import UnifiedDemoTests
    from tests.test_platform_http import PlatformHttpTests
    fixture = UnifiedDemoTests('runTest') if args.mode == 'demo' else PlatformHttpTests('runTest')
    try:
        fixture.setUp()
        origin = 'http://127.0.0.1:' + str(args.port)
        if args.mode == 'demo':
            from scripts.unify_demo import assemble
            from scripts.run_demo import build_demo
            from scripts.serve_learning_preview import _settings
            report = assemble(fixture.receipt, fixture.learning, fixture.target, args.port)
            receipt = json.loads((fixture.target/'resume.json').read_text(encoding='utf-8'))
            from app.platform_v1.images import ImageSettings
            images = ImageSettings(storage_dir=fixture.folder/'sample-assets',
                sample_enabled=True, sample_path=ROOT/'static/design/pine-mascot.png',
                sample_limit=100, live_enabled=False, image_limit=0)
            app = build_demo(report['database'], resume=receipt['bootstrap'],
                learning_settings=_settings(origin), learning_demo=receipt['learning'],
                platform_settings=PlatformSettings(enabled=True, navigation_enabled=True,
                    demo_mode=True, creative_studio_enabled=not args.legacy_course, image_settings=images))
            if args.metadata_output:
                args.metadata_output.parent.mkdir(parents=True, exist_ok=True)
                args.metadata_output.write_text(json.dumps(receipt['learning']), encoding='utf-8')
            register_server_admin(app, app.state.learning_v2, AdminSettings(
                allowed_emails=('nobody@example.test',), secret_dir=fixture.folder/'admin-private'))
            boundary = app.state.learning_v2.legacy_boundary
            boundary.managed_prefixes = (*boundary.managed_prefixes, '/api/server-admin/v1')
        else:
            settings = replace(fixture.settings, allowed_origins=(origin,), loopback_http=True,
                navigation_enabled=True, studio_enabled=True, catalog_enabled=True,
                course_enabled=True, mock_enabled=True)
            app = fixture.factory(fixture.path, core_only=True, enforce_journey=False,
                learning_settings=settings, platform_settings=replace(fixture.platform_settings,
                    navigation_enabled=True, demo_mode=False, creative_studio_enabled=True),
                server_admin_settings=AdminSettings(allowed_emails=('parent-a@example.test',),
                    secret_dir=Path(fixture.tmp.name)/'admin-private'))
            app.state.learning_v2.clock = lambda: fixture.now[0]
        print('Synthetic entry QA (' + args.mode + '): ' + origin, flush=True)
        uvicorn.run(app, host='127.0.0.1', port=args.port, log_level='warning')
    finally:
        fixture.doCleanups()


if __name__ == '__main__':
    main()
