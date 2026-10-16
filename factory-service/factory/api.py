import asyncio,hmac,logging
from contextlib import asynccontextmanager
from datetime import datetime
from uuid import uuid4
from fastapi import FastAPI,Request,WebSocket,WebSocketDisconnect,Query
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool
from .config import Settings
from .domain import Denied,InvalidAction
from .store import Store
from .worker import Worker
from .mcp_server import build,operation_key

logger=logging.getLogger('factory')
class Protection:
    def __init__(self,app,settings):self.app,self.settings=app,settings
    async def __call__(self,scope,receive,send):
        if scope['type'] not in ('http','websocket'):return await self.app(scope,receive,send)
        headers=dict(scope.get('headers',[]));credential=headers.get(b'authorization',b'')
        key=self.settings.mcp_auth_token if scope['path'].startswith('/mcp') else self.settings.api_token
        if scope['path']!='/health' and not hmac.compare_digest(credential,('Bearer '+key.get_secret_value()).encode()):
            if scope['type']=='websocket':return await send({'type':'websocket.close','code':4401})
            return await JSONResponse({'code':'UNAUTHORIZED','message':'Authenticated factory connection required'},status_code=401)(scope,receive,send)
        token=operation_key.set(headers.get(b'idempotency-key',b'').decode() or None)
        size=0
        async def bounded():
            nonlocal size
            m=await receive();size+=len(m.get('body',b''))
            if size>65536:raise InvalidAction('Request too large')
            return m
        try:await self.app(scope,bounded,send)
        finally:operation_key.reset(token)

class ActionInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind:str=Field(min_length=1,max_length=40)
    arguments:dict=Field(default_factory=dict)
    idempotency_key:str=Field(min_length=8,max_length=160)

def create_app(settings=None):
    settings=settings or Settings();store=Store(settings);worker=Worker(store)
    @asynccontextmanager
    async def lifespan(app):
        await run_in_threadpool(store.initialize);worker.start()
        async with mcp.session_manager.run():yield
        await run_in_threadpool(worker.stop);store.engine.dispose()
    app=FastAPI(title='Simulation-only Factory',lifespan=lifespan)
    app.state.store=store;app.state.worker=worker;mcp=build(store);app.add_middleware(Protection,settings=settings)
    @app.exception_handler(Denied)
    async def denied(request,error):return JSONResponse({'success':False,'code':'PERMISSION_DENIED','error':'Simulation policy rejects this action'},status_code=403)
    @app.exception_handler(InvalidAction)
    @app.exception_handler(ValueError)
    @app.exception_handler(RequestValidationError)
    async def invalid(request,error):return JSONResponse({'success':False,'code':'INVALID_ACTION','error':'Check identifiers, state and input limits'},status_code=422)
    @app.exception_handler(Exception)
    async def failed(request,error):
        logger.error('factory_request_failed type=%s',type(error).__name__)
        return JSONResponse({'success':False,'code':'FACTORY_UNAVAILABLE','error':'Inspect saved state before retrying; reuse idempotency key'},status_code=503)
    @app.get('/health')
    def health():
        with store.engine.connect() as c:c.execute(text('SELECT 1'))
        return {'status':'ready','service':'factory','simulation_only':True}
    @app.get('/api/state')
    def state():return store.state()
    @app.get('/api/measurements')
    def measurements(start_time:datetime|None=None,end_time:datetime|None=None,limit:int=Query(default=50,ge=1,le=100)):return store.measurements(settings.machine_id,start_time,end_time,limit)
    @app.post('/api/actions')
    def action(body:ActionInput):
        # Dedicated operator credential is never exposed to browser or MCP callers.
        return store.action(body.kind,body.arguments,body.idempotency_key,operator=True)
    @app.get('/api/actions/{identifier}')
    def action_status(identifier:str):return store.action_status(identifier)
    @app.websocket('/ws')
    async def websocket(socket:WebSocket):
        await socket.accept();last=-1
        try:
            while True:
                s=await run_in_threadpool(store.state)
                if s['version']!=last:
                    last=s['version'];await socket.send_json({'type':'factory.snapshot','version':last,'sequence':s['sequence'],'state':s})
                await asyncio.sleep(.5)
        except (WebSocketDisconnect,RuntimeError):pass
    app.mount('/',mcp.streamable_http_app())
    return app
