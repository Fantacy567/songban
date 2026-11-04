# Copyright (c) 2026 2292576833. Joint project ownership: COPYRIGHT.md.
"""Opaque-origin offline browser document; callers MUST sandbox without same-origin."""
import base64
import html
import re

CSP = "default-src 'none'; script-src 'unsafe-inline' data:; style-src 'unsafe-inline'; img-src data:; font-src 'none'; connect-src 'none'; frame-src 'none'; worker-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"

def document(files):
    values = {f['path']: f['content'] for f in files}
    # Source can contain hostile tags; first CSP is immutable and subsequent CSP
    # policies can only further restrict it. iframe sandbox supplies opaque origin.
    source = values.get('index.html', '')
    source = re.sub(r'<link\b[^>]*\bhref=[\"\'](?:\./)?style\.css[\"\'][^>]*>', '', source, flags=re.I)
    source = re.sub(r'<script\b[^>]*\bsrc=[\"\'](?:\./)?script\.js[\"\'][^>]*>\s*</script\s*>', '', source, flags=re.I)
    css = values.get('style.css', '').replace('</style', '<\\/style')
    js = base64.b64encode(values.get('script.js', '').encode()).decode()
    return '<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="'+html.escape(CSP, quote=True)+'"><style>'+css+'</style>'+source+'<script src="data:text/javascript;base64,'+js+'"></script>'
