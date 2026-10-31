"""Compatibility for the old 8886 link; all UI now comes from the unified preview."""
from starlette.responses import RedirectResponse
async def app(scope,receive,send):
    if scope['type']=='lifespan':
        while True:
            message=await receive()
            if message['type']=='lifespan.startup':await send({'type':'lifespan.startup.complete'})
            elif message['type']=='lifespan.shutdown':
                await send({'type':'lifespan.shutdown.complete'});return
    else:await RedirectResponse('http://127.0.0.1:8890/demo/')(scope,receive,send)
