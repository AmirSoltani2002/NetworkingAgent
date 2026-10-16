from typing import Annotated, Any, Literal
from fastapi.encoders import jsonable_encoder
from datetime import datetime
from pydantic import Field, ValidationError
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from jsonschema import Draft202012Validator
from starlette.concurrency import run_in_threadpool
from .schemas import Filters, Reading, Measurement, AddInput, TrainInput, EvaluationConfig, PredictInput, BatchInput
from .auth import require_admin
from .errors import ServiceError

class StrictMCP(FastMCP):
    async def list_tools(self):
        tools=await super().list_tools()
        for tool in tools:tool.inputSchema={**tool.inputSchema,'additionalProperties':False}
        return tools
    async def call_tool(self,name,arguments):
        tool=next((t for t in await self.list_tools() if t.name==name),None)
        if not tool or not Draft202012Validator(tool.inputSchema).is_valid(arguments):raise ToolError('INVALID_ARGUMENTS: Follow the discovered input schema')
        return await super().call_tool(name,arguments)

def build(service,settings):
    hosts=settings.mcp_allowed_hosts.split(',')
    server=StrictMCP('ZSK Synthetic Condition Monitoring',stateless_http=True,json_response=True,streamable_http_path='/mcp',max_request_body_size=65536,transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,allowed_hosts=hosts,allowed_origins=['http://'+h for h in hosts]))
    ro=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False)
    write=ToolAnnotations(readOnlyHint=False,destructiveHint=False,idempotentHint=True,openWorldHint=False)
    async def invoke(fn,*args,writing=False):
        try:
            if writing:require_admin()
            return jsonable_encoder(await run_in_threadpool(fn,*args))
        except ServiceError as e:raise ToolError(f'{e.code}: {e.message}') from None
        except (ValueError,ValidationError):raise ToolError('INVALID_INPUT: Check measurements, chronological history and documented limits') from None
        except Exception:raise ToolError('SERVICE_ERROR: Check service health; do not blindly repeat writes with a new idempotency key') from None
    @server.tool(annotations=ro)
    async def get_zsk_measurements(machine_id:str|None=None,start_time:datetime|None=None,end_time:datetime|None=None,labeled:bool=False,page:Annotated[int,Field(ge=1,le=100000)]=1,page_size:Annotated[int,Field(ge=1,le=100)]=50)->dict[str,Any]:
        """Read paginated synthetic ZSK signals with timestamps, units and provenance. After initial training only unlabeled readings remain. 0=Faulty,1=Healthy applies only to genuine labels/predictions, never infer ground truth."""
        return await invoke(service.records,Filters(machine_id=machine_id,start_time=start_time,end_time=end_time,page=page,page_size=page_size),labeled)
    @server.tool(annotations=write)
    async def add_zsk_measurements(readings:Annotated[list[Reading],Field(min_length=1,max_length=100)],idempotency_key:Annotated[str,Field(min_length=8,max_length=120)])->dict[str,Any]:
        """STATE CHANGE requiring operator permission and admin credential. Append validated readings with exact units; labels require verified_operator_label provenance. Reuse the same idempotency key after a timeout; never label from predictions."""
        return await invoke(service.add,AddInput(readings=readings,idempotency_key=idempotency_key),writing=True)
    @server.tool(annotations=write)
    async def train_zsk_health_model(idempotency_key:Annotated[str,Field(min_length=8,max_length=120)],evaluation_config:EvaluationConfig|None=None)->dict[str,Any]:
        """STATE CHANGE: full RandomForest retraining, not incremental fine-tuning. Requires admin authorization and at least 100 verified labeled rows with both classes. Returns durable job_id immediately; poll status. Training labels are purged after successful activation as requested. Existing unlabeled readings cannot train the model."""
        return await invoke(service.queue,TrainInput(idempotency_key=idempotency_key,evaluation_config=evaluation_config or EvaluationConfig()),'train',writing=True)
    @server.tool(annotations=ro)
    async def get_zsk_training_status(job_id:str)->dict[str,Any]:
        """Inspect queued/running/completed/failed durable training or batch job, actual progress, result and error. Completed is required before claiming success."""
        return await invoke(service.job,job_id)
    @server.tool(annotations=ro)
    async def get_zsk_model_metrics(model_version:str|None=None)->dict[str,Any]:
        """Return versioned chronological holdout metrics and class counts for the evaluation candidate; deployed final model uses all labeled rows. Synthetic-only evaluation is not real industrial validation."""
        return await invoke(service.metrics,model_version)
    @server.tool(annotations=ro)
    async def predict_zsk_health(measurement:Measurement|None=None,measurement_id:Annotated[int,Field(ge=1)]|None=None,recent_history:Annotated[list[Measurement],Field(max_length=2)]|None=None,source:Literal['unlabeled','labeled']='unlabeled')->dict[str,Any]:
        """Infer one supplied reading or stored measurement_id using same-machine chronological preceding two readings. New readings need history; early stored rows report warmup windows. Returns actual fault probability, 0=Faulty/1=Healthy, model version. No equipment control."""
        return await invoke(service.predict,PredictInput(measurement=measurement,measurement_id=measurement_id,recent_history=recent_history,source=source))
    @server.tool(annotations=write)
    async def batch_predict_zsk_health(machine_id:str|None=None,start_time:datetime|None=None,end_time:datetime|None=None,source:Literal['unlabeled','labeled']='unlabeled',page_size:Annotated[int,Field(ge=1,le=100)]=50,job_id:str|None=None,idempotency_key:Annotated[str,Field(min_length=8,max_length=120)]|None=None)->dict[str,Any]:
        """STATE CHANGE: queue durable batch inference and store predictions separately from ground truth. Admin permission required to start; idempotency_key required. Includes preceding history at every page boundary. If job_id is supplied, only inspect existing status; retrieve paginated outputs with get_zsk_predictions."""
        if job_id:return await invoke(service.job,job_id)
        if not idempotency_key:raise ToolError('IDEMPOTENCY_KEY_REQUIRED: Supply a stable key when starting a batch')
        return await invoke(service.queue,BatchInput(machine_id=machine_id,start_time=start_time,end_time=end_time,source=source,page_size=page_size,idempotency_key=idempotency_key),'batch',writing=True)
    @server.tool(annotations=ro)
    async def get_zsk_predictions(job_id:str|None=None,model_version:str|None=None,machine_id:str|None=None,page:Annotated[int,Field(ge=1,le=100000)]=1,page_size:Annotated[int,Field(ge=1,le=100)]=50)->dict[str,Any]:
        """Read bounded saved synthetic inference outputs, with source measurement IDs, chronological timestamps, model version and fault probabilities. Predictions never overwrite ground truth."""
        return await invoke(service.predictions,Filters(machine_id=machine_id,page=page,page_size=page_size),job_id,model_version)
    @server.tool(annotations=ro)
    async def get_zsk_forecast_metrics()->dict[str,Any]:
        """Read measured chronological evaluation of the separate synthetic future-onset baseline. Not current health classification or industrial prognosis."""
        return await invoke(service.forecast.metrics)
    @server.tool(annotations=ro)
    async def predict_zsk_future_failure(measurement:Measurement,recent_history:Annotated[list[Measurement],Field(min_length=2,max_length=2)])->dict[str,Any]:
        """Estimate synthetic future fault onset within the registered horizon, with two preceding five-minute readings. No future measurements, simulator labels or controls."""
        return await invoke(service.forecast.predict,[r.row() for r in recent_history]+[measurement.row()])
    return server
