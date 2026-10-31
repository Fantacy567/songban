"""CLI for the actual Codex loader check used by the native installer."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.plugin_host import check

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--home',required=True)
    ap.add_argument('--cwd',default=str(Path.cwd()))
    args=ap.parse_args()
    result=check(args.home,args.cwd)
    print(json.dumps(result,ensure_ascii=False))
    raise SystemExit(0 if result['upload_tool_loaded'] else 1)
