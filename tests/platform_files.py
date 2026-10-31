"""Exercise actual file protection and redirect boundaries on each platform."""
import json
import os
from pathlib import Path
import subprocess


def assert_private(case, path):
    path = Path(path)
    if os.name != 'nt':
        case.assertEqual(path.stat().st_mode & 0o777, 0o600)
        return
    # Independent OS ACL inspection, not the installer helper's return value.
    script = "$ErrorActionPreference='Stop'; $a=Get-Acl -LiteralPath $env:SONGBAN_TEST_ACL_PATH; $sid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value; @{protected=$a.AreAccessRulesProtected; user=$sid; rules=@($a.Access | ForEach-Object { @{sid=$_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value; type=$_.AccessControlType.ToString(); inherited=$_.IsInherited; rights=$_.FileSystemRights.ToString()} })} | ConvertTo-Json -Depth 4 -Compress"
    env = dict(os.environ, SONGBAN_TEST_ACL_PATH=str(path))
    # Do not feed PowerShell 7's modules into the Windows PowerShell 5.1 process.
    env = {k: v for k, v in env.items() if k.upper() != 'PSMODULEPATH'}
    run = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], env=env, capture_output=True, text=True, check=True, timeout=15)
    acl = json.loads(run.stdout)
    case.assertTrue(acl['protected'])
    case.assertEqual({r['sid'] for r in acl['rules']}, {acl['user'], 'S-1-5-18'})
    for rule in acl['rules']:
        case.assertEqual(rule['type'], 'Allow')
        case.assertFalse(rule['inherited'])
        case.assertEqual(rule['rights'], 'FullControl')


def directory_link(link, target):
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as error:
        if os.name != 'nt' or error.winerror != 1314:
            raise
        # Junctions need no developer-mode privilege and exercise real resolution
        # outside the project just like directory symlinks; no skipped assertions.
        subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(link), str(target)], capture_output=True, check=True, timeout=10)
        assert link.is_junction() and link.resolve() == Path(target).resolve()
