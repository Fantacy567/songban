"""Loopback only, dedicated SQLite and explicit model fixture. No real SMS/model calls."""
import io
import sqlite3
import sys
import uuid
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from app.main import create_app, digest, now
from app.studio import hash_password
from tests.test_materials import fixture_model
from tests.test_team_core import plan_for


def fixtures(folder):
    from PIL import Image, ImageDraw, ImageFont
    from docx import Document
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
    font_path = Path('C:/Windows/Fonts/msyh.ttc')
    font = ImageFont.truetype(str(font_path), 40) if font_path.exists() else ImageFont.load_default(size=40)
    image = Image.new('RGB', (1100, 260), 'white')
    ImageDraw.Draw(image).text((40, 70), '提交作品链接，完成3分钟展示', fill='black', font=font)
    image.save(folder/'screenshot.png');image.save(folder/'photo.jpg')
    out=io.BytesIO();c=canvas.Canvas(out);c.drawImage(ImageReader(image),40,500,width=500,height=120);c.save();(folder/'scan.pdf').write_bytes(out.getvalue())
    out=io.BytesIO();c=canvas.Canvas(out);c.drawString(40,700,'Deliver a working project link.');c.save();(folder/'rules.pdf').write_bytes(out.getvalue())
    doc=Document();doc.add_paragraph('小林愿意做演示，具体分工待确认。');doc.save(folder/'chat.docx')
    (folder/'notes.txt').write_text('想法：做一个校园知识小助手。',encoding='utf-8')
    (folder/'unreadable.pdf').write_bytes(b'not a pdf - synthetic failure fixture')


if __name__ == '__main__':
    import uvicorn
    folder=ROOT/'.browser-cache'/'materials';folder.mkdir(parents=True,exist_ok=True)
    fixtures(folder)
    path=folder/('qa-'+uuid.uuid4().hex[:8]+'.sqlite3')
    app=create_app(path,core_only=True,materials_model_runner=fixture_model,core_model_runner=plan_for)
    with closing(sqlite3.connect(path)) as con:
        for ident,phone,name in [('qa-materials','18800008893','资料测试同伴'),('qa-materials-b','18800008894','资料测试队友')]:
            con.execute('INSERT INTO people(id,phone,name,profile,skills,token_hash,created_at,password_hash) VALUES(?,?,?,?,?,?,?,?)',(ident,phone,name,'仅本机合成测试','资料整理',digest('test-'+ident),now(),hash_password('materials-test-password')))
        con.commit()
    with TestClient(app) as client:
        team=client.post('/api/core/teams',headers={'Authorization':'Bearer test-qa-materials'},json={'name':'资料入口验证小队'}).json()
        client.post('/api/core/join',headers={'Authorization':'Bearer test-qa-materials-b'},json={'code':team['code']})
    uvicorn.run(app,host='127.0.0.1',port=8893,log_level='warning')
