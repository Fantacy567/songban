"""SQLite online backup, including committed WAL content; never copies a live file."""
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

root = Path(__file__).resolve().parent.parent
configured = os.environ.get("DATABASE_PATH")
if configured is None and (root / ".env").exists():
    for line in (root / ".env").read_text().splitlines():
        if "=" in line and line.split("=",1)[0].strip() == "DATABASE_PATH":
            configured = line.split("=",1)[1].strip().strip("\"'")
source = Path(configured or root / "data" / "collab.sqlite3")
if not source.is_absolute():
    source = root / source
if not source.exists():
    raise SystemExit("数据库尚不存在；请先启动项目。")
dest = root / "data" / "backups" / ("collab-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".sqlite3")
dest.parent.mkdir(parents=True, exist_ok=True)
with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(dest)) as target:
    src.backup(target)
    if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise SystemExit("备份完整性检查失败，保留文件供排查。")
print("已创建并检查一致性备份：", dest)
