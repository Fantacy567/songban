"""Local preview: persistent real accounts and an isolated /demo entrance."""
from .main import app as real_app
from .demo_server import Demo
from starlette.responses import RedirectResponse
class Preview:
    def __init__(self): self.demo=Demo('/demo')
    async def __call__(self,scope,receive,send):
        if scope['type']=='http' and scope['path']=='/demo':
            return await RedirectResponse('/demo/')(scope,receive,send)
        if scope['type']=='http' and scope['path'].startswith('/demo/'):
            scope={**scope,'path':scope['path'][5:],'raw_path':scope['raw_path'][5:]}
            return await self.demo(scope,receive,send)
        return await real_app(scope,receive,send)
app=Preview()
