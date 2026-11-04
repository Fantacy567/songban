# Copyright (c) 2026 2292576833. Upstream retains its MIT license.
"""Read-only Harness deployment diagnosis; never installs or runs an agent.

Exit 0 means a Linux engine and matching image were found, NOT runtime validation.
Exit 2 means prerequisites are missing. Run verify_harness_container.py separately.
Only selected metadata is reported; no Docker inspect environment or credentials.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.creative_studio.harness import CONTRACT, IMAGE, REVISION


def probe(argv, *, cwd=None):
    try:
        result = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=8,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        raw = result.stdout or result.stderr
        encoding = 'utf-16-le' if b'\x00' in raw else 'utf-8'
        return result.returncode, raw.decode(encoding, errors='replace').strip()
    except (OSError, subprocess.SubprocessError):
        return None, ''


def inspect_engine(executable):
    report = {'executable': executable, 'reachable': False, 'linux': False, 'image_ready': False}
    if not executable:
        return report
    code, output = probe([executable, 'info', '--format', '{{.OSType}}'])
    report.update(reachable=code == 0, linux=code == 0 and output.lower() == 'linux')
    if not report['linux']:
        # Podman exposes Host.OS, while Docker exposes OSType.
        code, output = probe([executable, 'info', '--format', '{{.Host.OS}}'])
        report.update(reachable=report['reachable'] or code == 0, linux=code == 0 and output.lower() == 'linux')
    if not report['linux']:
        return report
    fmt = '{{.Id}}|{{.Os}}|{{index .Config.Labels "org.opencontainers.image.revision"}}|{{index .Config.Labels "org.songban.harness.contract"}}'
    code, output = probe([executable, 'image', 'inspect', IMAGE, '--format', fmt])
    fields = output.split('|')
    report['image_present'] = code == 0
    if code == 0 and len(fields) == 4:
        # Only hashes and known labels; do not expose arbitrary image metadata.
        report.update(image_id=fields[0] if fields[0].startswith('sha256:') else None,
                      image_linux=fields[1] == 'linux', revision_matches=fields[2] == REVISION,
                      contract_matches=fields[3] == CONTRACT)
        report['image_ready'] = all(report[k] for k in ('image_linux', 'revision_matches', 'contract_matches'))
    return report


def inspect_source(source):
    if source is None:
        return {'provided': False}
    source = source.resolve()
    report = {'provided': True, 'path': str(source), 'exists': source.is_dir()}
    if not report['exists']:
        return report
    code, head = probe(['git', 'rev-parse', 'HEAD'], cwd=source)
    report['revision_matches'] = code == 0 and head == REVISION
    code, dirty = probe(['git', 'status', '--porcelain'], cwd=source)
    report['clean_checkout'] = code == 0 and not dirty
    try:
        package = json.loads((source/'package.json').read_text(encoding='utf-8'))
        report.update(node_required=package.get('engines', {}).get('node'), package_manager=package.get('packageManager'))
    except (OSError, ValueError):
        report['manifest_readable'] = False
    report['paths'] = {name: (source/name).exists() for name in (
        'pnpm-lock.yaml', 'node_modules', 'apps/cli/lib/bin.js', 'packages/sdk/client/lib/index.js', 'LICENSE')}
    return report


def diagnose(source=None):
    report = {'checked_at': datetime.now(timezone.utc).isoformat(), 'revision': REVISION, 'contract': CONTRACT,
              'image': IMAGE, 'kind': 'read-only-deployment-prerequisites', 'real_container': False,
              'real_agent_runtime': False, 'real_model_calls': 0, 'build_run': False}
    engines = {name: shutil.which(name) for name in ('docker', 'podman')}
    if os.name == 'nt':
        candidates = {'docker': Path('C:/Program Files/Docker/Docker/resources/bin/docker.exe'),
                      'podman': Path('C:/Program Files/RedHat/Podman/podman.exe')}
        for name, path in candidates.items():
            if not engines[name] and path.is_file():
                engines[name] = str(path)
        wsl = shutil.which('wsl')
        report['wsl'] = {'executable': wsl}
        if wsl:
            status, message = probe([wsl, '--status'])
            listing, _ = probe([wsl, '--list', '--quiet'])
            report['wsl'].update(status_exit=status, list_exit=listing,
                                 available=status == 0 and listing == 0,
                                 installation_prompt='wsl.exe --install' in message)
    report['engines'] = {name: inspect_engine(executable) for name, executable in engines.items()}
    report['source'] = inspect_source(source)
    node = shutil.which('node')
    code, version = probe([node, '--version']) if node else (None, '')
    report['node'] = {'executable': node, 'version': version if code == 0 else None}
    # Do not invoke a Corepack/pnpm shim: --version can download a package manager.
    report['pnpm_executable'] = shutil.which('pnpm')
    report['ready_for_container_test'] = any(item['image_ready'] for item in report['engines'].values())
    report['blockers'] = []
    if not any(item['linux'] for item in report['engines'].values()):
        report['blockers'].append('No reachable Linux Docker/Podman engine. Supply an isolated build host; no host fallback.')
    elif not report['ready_for_container_test']:
        report['blockers'].append('Build the pinned image with the current worker contract on the Linux engine.')
    report['next_step'] = ('Run verify_harness_container.py with the selected engine; readiness is not execution proof.'
                           if report['ready_for_container_test'] else 'Resolve blockers and rerun this read-only diagnosis.')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='Optional existing pinned checkout; never modified')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = diagnose(args.source)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['ready_for_container_test'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
