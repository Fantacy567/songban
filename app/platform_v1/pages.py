"""Only installed, explicitly enabled platform pages receive the new shell."""
def platform_page(html, settings, *, learning=False):
    if settings is None or not settings.navigation_enabled:
        return html
    assets = '<meta name="songban-platform" content="1"><link rel="stylesheet" href="/static/platform-shell.css?v=20261104-u1">'
    if settings.creative_studio_enabled:
        assets += '<meta name="songban-creative-studio" content="1">'
    if not learning:
        assets += '<link rel="stylesheet" href="/static/platform/halls.css?v=20261102-h1"><script defer src="/static/platform/halls.js?v=20261102-h1"></script>'
        assets += '<link rel="stylesheet" href="/static/platform/companion.css?v=20261102-h3"><script defer src="/static/platform/companion.js?v=20261102-h3"></script><script defer src="/static/platform-native.js?v=20261102-h3"></script>'
    return html.replace('</head>', assets+'</head>', 1)
