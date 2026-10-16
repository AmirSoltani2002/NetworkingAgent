import asyncio,hmac,json,logging,time
from contextlib import asynccontextmanager
from uuid import uuid4
from fastapi import FastAPI, Query
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from fastapi.responses import JSONResponse
from typing import Annotated
from starlette.concurrency import run_in_threadpool
from sqlalchemy import text
from .config import Settings
from .db import database,initialize
from .service import Service
from .forecast import Forecast
from .schemas import AddInput, TrainInput, BatchInput, PredictInput, Filters, RollbackInput
from .errors import ServiceError
from .auth import admin,require_admin
from .mcp_server import build

logger=logging.getLogger('zsk')
class Protection:
    def __init__(self,app,settings):self.app,self.settings=app,settings
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        authorization=dict(scope.get('headers',[])).get(b'authorization',b'')
        is_admin=hmac.compare_digest(authorization,('Bearer '+self.settings.admin_api_key.get_secret_value()).encode())
        allowed=is_admin or hmac.compare_digest(authorization,('Bearer '+self.settings.api_key.get_secret_value()).encode())
        if scope['path'] not in ('/health','/ready') and not allowed:return await JSONResponse({'code':'UNAUTHORIZED','message':'A configured bearer credential is required'},status_code=401)(scope,receive,send)
        token=admin.set(is_admin);started=time.monotonic();request_id=str(uuid4());size=0;response_started=False
        async def bounded():
            nonlocal size
            message=await receive();size+=len(message.get('body',b''))
            if size>1048576:raise ServiceError('REQUEST_TOO_LARGE','Requests are limited to 1 MiB',413)
            return message
        async def outgoing(message):
            nonlocal response_started
            if message['type']=='http.response.start':
                response_started=True;message.setdefault('headers',[]).append((b'x-request-id',request_id.encode()))
            await send(message)
        try:
            async with asyncio.timeout(self.settings.request_timeout):await self.app(scope,bounded,outgoing)
        except TimeoutError:
            if not response_started:await JSONResponse({'code':'TIMEOUT','message':'Inspect job status; retry writes only with the original idempotency key'},status_code=504)(scope,receive,send)
        except ServiceError as error:
            if not response_started:await JSONResponse({'code':error.code,'message':error.message},status_code=error.status)(scope,receive,send)
        finally:
            admin.reset(token)
            logger.info(json.dumps({'event':'request','request_id':request_id,'method':scope['method'],'duration_ms':int((time.monotonic()-started)*1000)}))
def create_app(settings=None):
    settings=settings or Settings();engine=database(settings);service=Service(engine,settings);service.forecast=Forecast(engine,settings)
    @asynccontextmanager
    async def lifespan(app):
        await run_in_threadpool(initialize,engine,settings);await run_in_threadpool(service.forecast.bootstrap);service.start()
        async with mcp.session_manager.run():yield
        await run_in_threadpool(service.stop);engine.dispose()
    app=FastAPI(title='ZSK Synthetic Condition Monitoring',lifespan=lifespan)
    app.state.service=service;app.state.engine=engine
    mcp=build(service,settings);mcp_app=mcp.streamable_http_app()
    app.add_middleware(Protection,settings=settings)
    @app.exception_handler(ServiceError)
    async def service_error(request,error):return JSONResponse({'code':error.code,'message':error.message},status_code=error.status)
    @app.exception_handler(ValidationError)
    @app.exception_handler(RequestValidationError)
    async def invalid(request,error):return JSONResponse({'code':'INVALID_INPUT','message':'Check required fields, units and limits','fields':[{'field':'.'.join(map(str,e['loc'])),'message':e['msg']} for e in error.errors()]},status_code=422)
    @app.exception_handler(Exception)
    async def unexpected(request,error):
        logger.error(json.dumps({'event':'service_error','type':type(error).__name__}))
        return JSONResponse({'code':'SERVICE_ERROR','message':'Check service health; credentials and internal traces are withheld'},status_code=500)
    @app.get('/health')
    def health():return {'status':'alive','service':'zsk-ml'}
    @app.get('/ready')
    def ready():
        try:
            with engine.connect() as conn:conn.execute(text('SELECT 1'))
            if not service._thread or not service._thread.is_alive():raise ValueError()
            service.loaded(str(service.active()['version']))
            return {'status':'ready','service':'zsk-ml'}
        except Exception:raise ServiceError('NOT_READY','Database, worker or initial trained model is not ready',503) from None
    @app.get('/api/forecast/metrics')
    def forecast_metrics():return service.forecast.metrics()
    @app.post('/api/forecast/predict')
    def forecast_predict(request:PredictInput):
        if request.measurement is None or request.recent_history is None:raise ServiceError('INVALID_INPUT','Supply target and preceding history')
        return service.forecast.predict([r.row() for r in request.recent_history]+[request.measurement.row()])
    @app.get('/api/model/status')
    def status():return service.status()
    @app.get('/api/model/metrics')
    def metrics(model_version:str|None=None):return service.metrics(model_version)
    @app.post('/api/model/train',status_code=202)
    def train(request:TrainInput):require_admin();return service.queue(request,'train')
    @app.post('/api/model/rollback')
    def rollback(request:RollbackInput):require_admin();return service.rollback(request)
    @app.post('/api/model/predict')
    def predict(request:PredictInput):return service.predict(request)
    @app.get('/api/measurements')
    def measurements(machine_id:str|None=None,start_time:str|None=None,end_time:str|None=None,page:int=1,page_size:int=50,labeled:bool=False):return service.records(Filters(machine_id=machine_id,start_time=start_time,end_time=end_time,page=page,page_size=page_size),labeled)
    @app.post('/api/measurements',status_code=201)
    def add(request:AddInput):require_admin();return service.add(request)
    @app.post('/api/batch-predictions',status_code=202)
    def batch(request:BatchInput):require_admin();return service.queue(request,'batch')
    @app.get('/api/jobs/{job_id}')
    def job(job_id:str):return service.job(job_id)
    @app.get('/api/predictions')
    def predictions(machine_id:str|None=None,page:int=1,page_size:int=50,job_id:str|None=None,model_version:str|None=None):return service.predictions(Filters(machine_id=machine_id,page=page,page_size=page_size),job_id,model_version)
    app.mount('/',mcp_app)
    return app
