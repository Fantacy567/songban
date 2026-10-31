# 本地完整服务与临时公网演示

完整服务保留 Python API、SQLite 持久化、真实手机号账号及独立 /demo/ 入口。

```sh
DATABASE_PATH=/absolute/path/songban.sqlite3 PUBLIC_BASE_URL=https://YOUR-TUNNEL.trycloudflare.com SONGBAN_DEMO_PUBLIC_ORIGIN=https://YOUR-TUNNEL.trycloudflare.com python -m uvicorn app.preview_server:app --host 0.0.0.0 --port 8890 --workers 1
cloudflared tunnel --url http://127.0.0.1:8890 --protocol http2 --edge-ip-version 4 --no-autoupdate
```

先从隧道日志取得真实域名，再将 PUBLIC_BASE_URL 设成该域名并重启应用，供家长二维码生成公网链接。模型与短信配置只通过服务端环境变量提供，禁止提交 .env、密钥、账号数据库或真实对话。公网首页为 /，独立虚构演示为 /demo/。

临时域名要求本机和隧道保持运行，重启隧道可能更换地址。它不是永久服务器部署；无需同一 Wi-Fi。

## 本次设计接入

以用户给定参考站为视觉依据：暖白底、大标题、黑色首页操作、扇形作品封面、绿色松树、紫色登录和流程控件、窄侧栏。static/songban-reference.css 独立覆盖视觉；图片在 static/design/，业务模块和阶段校验保持原实现。封面和松树来自用户提供的设计，仅作方向示意。

回归命令（与 CI 相同；严格流程测试显式开启门槛，生产默认开启）：

```sh
SONGBAN_ENFORCE_JOURNEY=0 SONGBAN_CORE_ONLY=0 python -m unittest discover -s tests -q
python scripts/browser_unified_flow.py
```

演示默认仅本机开放；显式设置 SONGBAN_DEMO_PUBLIC_ORIGIN 后仅开放匹配该 HTTPS 域名的演示入口，其他域名仍拒绝。
