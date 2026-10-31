"""Process launch regression; the fake loader never loads a model or user config."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from app.plugin_host import check


@unittest.skipUnless(os.name == 'nt', 'Windows PATH/PATHEXT launch behavior')
class PluginHostLaunchTests(unittest.TestCase):
    def test_default_cli_finds_cmd_shim_in_path_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix='songban host path ') as folder:
            root = Path(folder)
            bin_dir = root / 'npm bin'
            bin_dir.mkdir()
            (bin_dir / 'codex.cmd').write_text(
                '@echo off\n"' + sys.executable + '" "%~dp0host_fixture.py" %*\n',
                encoding='utf-8',
            )
            (bin_dir / 'host_fixture.py').write_text(
                'import json, sys\n'
                'for line in sys.stdin:\n'
                '    request = json.loads(line)\n'
                '    if "id" not in request: continue\n'
                '    result = {}\n'
                '    if request["method"] == "mcpServerStatus/list":\n'
                '        result = {"data": [{"name": "songban-fixture", "tools": {"songban_sync_selected_turn": {}}}]}\n'
                '    print(json.dumps({"id": request["id"], "result": result}), flush=True)\n',
                encoding='utf-8',
            )
            # Exclude any globally installed codex.exe so it cannot mask a
            # failure to resolve the npm .cmd entry point, as in Windows CI.
            with patch.dict(os.environ, {'PATH': str(bin_dir), 'PATHEXT': '.COM;.EXE;.BAT;.CMD'}):
                result = check(root, root)
            self.assertTrue(result['upload_tool_loaded'])
            self.assertEqual(result['servers'], ['songban-fixture'])
            self.assertEqual(result['loader_errors'], [])


if __name__ == '__main__':
    unittest.main()
