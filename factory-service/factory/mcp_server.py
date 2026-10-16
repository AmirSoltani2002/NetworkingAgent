from typing import Any,Annotated
from contextvars import ContextVar
from datetime import datetime
from uuid import UUID
from pydantic import Field
from fastapi.encoders import jsonable_encoder
from starlette.concurrency import run_in_threadpool
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from zsk.mcp_server import StrictMCP
from .domain import Denied,InvalidAction,COMPONENTS

operation_key=ContextVar('factory_operation_key',default=None)

class FactoryMCP(StrictMCP):
    async def call_tool(self,name,arguments):
        # The SDK dispatches calls in its own task. Read its request context,
        # rather than depending on ASGI middleware ContextVar propagation.
        context=self.get_context().request_context
        request=context.request
        meta=context.meta.model_dump() if context.meta else {}
        key=(request.headers.get('Idempotency-Key') if request else None) or meta.get('operationId')
        token=operation_key.set(key)
        try:return await super().call_tool(name,arguments)
        finally:operation_key.reset(token)

def build(store):
    hosts=store.settings.mcp_allowed_hosts.split(',')
    server=FactoryMCP('Simulation-only ZSK Factory',stateless_http=True,json_response=True,streamable_http_path='/mcp',max_request_body_size=65536,transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,allowed_hosts=hosts,allowed_origins=['http://'+h for h in hosts]))
    ro=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False)
    write=ToolAnnotations(readOnlyHint=False,destructiveHint=False,idempotentHint=True,openWorldHint=False)
    async def invoke(fn,*args):
        try:return jsonable_encoder(await run_in_threadpool(fn,*args))
        except Denied:raise ToolError('PERMISSION_DENIED: simulation action disabled by backend policy') from None
        except (InvalidAction,ValueError,KeyError):raise ToolError('INVALID_ACTION: check simulation state, identifiers and preconditions') from None
        except Exception:raise ToolError('FACTORY_UNAVAILABLE: reconcile stable action ID before retrying writes') from None
    async def act(kind,args,key):
        return await invoke(store.action,kind,args,operation_key.get() or key)
    @server.tool(annotations=ro)
    async def get_factory_state()->dict[str,Any]:
        """Read authoritative simulation clock, mode, component state, alarms, predictions, actions and simulation-only policy. Never physical equipment."""
        return await invoke(store.state)
    @server.tool(annotations=ro)
    async def get_machine_state(machine_id:str,epoch:str|None=None)->dict[str,Any]:
        """Read exact simulated machine ID, mode, epoch, latest signals and completed inspections for verification."""
        state=await invoke(store.state)
        if state['machine_id']!=machine_id:raise ToolError('UNKNOWN_MACHINE')
        if epoch and state['epoch']!=epoch:raise ToolError('STALE_EPISODE: simulation reset; stop this investigation')
        # Keep exact live sensor/state evidence visible without duplicating the
        # factory-wide alarm/task/action history in this diagnostic response.
        return {key:state[key] for key in ('machine_id','epoch','mode','condition','clock','latest_measurement','last_inspections','technician','policy','pending_actions')}
    @server.tool(annotations=ro)
    async def get_machine_measurements(machine_id:str,start_time:datetime|None=None,end_time:datetime|None=None,limit:Annotated[int,Field(ge=1,le=100)]=50)->dict[str,Any]:
        """Read actual stored historical/new synthetic signals in chronological order; latest 100 within optional UTC range. Ground truth excluded."""
        return await invoke(store.measurements,machine_id,start_time,end_time,limit)
    @server.tool(annotations=ro)
    async def get_machine_alarms(machine_id:str)->dict[str,Any]:
        """Read current/predicted alarms and saved ML outputs, with model versions, horizon and task IDs."""
        await get_machine_state(machine_id);s=await invoke(store.state);return {'items':s['alarms'],'prediction':s['prediction'],'monitoring':s['monitoring']}
    @server.tool(annotations=ro)
    async def get_monitoring_results(machine_id:str)->dict[str,Any]:
        """Read latest saved current-condition and separate future-onset prediction plus durable monitoring checkpoint."""
        await get_machine_state(machine_id);s=await invoke(store.state);return {'prediction':s['prediction'],'checkpoint':s['monitoring'],'machine_id':machine_id}
    @server.tool(annotations=ro)
    async def list_factory_components()->dict[str,Any]:
        """List clickable simulated components and their scene positions."""
        return {'items':COMPONENTS}
    @server.tool(annotations=ro)
    async def list_factory_characters()->dict[str,Any]:
        """Read the simulated technician's authoritative location and action."""
        s=await invoke(store.state);return {'items':[s['technician']]}
    @server.tool(annotations=ro)
    async def get_factory_action_history()->dict[str,Any]:
        """Read recent persisted action acknowledgments/completions; accepted is not completed."""
        s=await invoke(store.state);return {'items':s['actions']}
    @server.tool(annotations=ro)
    async def get_maintenance_status(task_id:str,epoch:str|None=None,component_id:str|None=None,alarm_id:str|None=None)->dict[str,Any]:
        """Read actual persisted action status by returned action_id. Completed inspections include recorded observation evidence."""
        try:UUID(task_id)
        except ValueError:raise ToolError('INVALID_ID') from None
        return await invoke(store.action_status,task_id,epoch,component_id,alarm_id)
    @server.tool(annotations=write)
    async def move_character(character_id:str,destination:str,epoch:str,idempotency_key:str|None=None)->dict[str,Any]:
        """SIMULATION WRITE: move technician to a component; poll action_id for completion. Stable key or harness operation ID required."""
        return await act('move',{'character_id':character_id,'component_id':destination,'epoch':epoch},idempotency_key)
    @server.tool(annotations=write)
    async def inspect_component(component_id:str,epoch:str,idempotency_key:str|None=None)->dict[str,Any]:
        """SIMULATION WRITE: technician walks and inspects; accepted does not mean completed. Poll returned action_id with get_maintenance_status for evidence."""
        return await act('inspect',{'component_id':component_id,'epoch':epoch},idempotency_key)
    @server.tool(annotations=write)
    async def stop_manufacturing_line(machine_id:str,epoch:str,idempotency_key:str|None=None)->dict[str,Any]:
        """SIMULATION ONLY controlled write: backend auto-stop policy required; transitions RUNNING → STOPPING → STOPPED. Verify exact machine state afterward."""
        return await act('stop',{'machine_id':machine_id,'epoch':epoch},idempotency_key)
    @server.tool(annotations=write)
    async def start_manufacturing_line(machine_id:str,epoch:str,idempotency_key:str|None=None)->dict[str,Any]:
        """SIMULATION ONLY controlled write: explicit restart policy, stopped line and no severe fault/pending actions required."""
        return await act('start',{'machine_id':machine_id,'epoch':epoch},idempotency_key)
    @server.tool(annotations=write)
    async def pause_manufacturing_line(machine_id:str,epoch:str,idempotency_key:str|None=None)->dict[str,Any]:
        """Controlled simulated production stop; does not pause the simulation clock. Same stop permission and verification apply."""
        return await act('pause_line',{'machine_id':machine_id,'epoch':epoch},idempotency_key)
    @server.tool(annotations=write)
    async def acknowledge_alarm(alarm_id:str,idempotency_key:str|None=None)->dict[str,Any]:
        """SIMULATION WRITE: acknowledge exact alarm; acknowledgment does not resolve its condition."""
        try:UUID(alarm_id)
        except ValueError:raise ToolError('INVALID_ID') from None
        return await act('acknowledge',{'alarm_id':alarm_id},idempotency_key)
    @server.tool(annotations=write)
    async def assign_maintenance_task(character_id:str,component_id:str,epoch:str,idempotency_key:str|None=None)->dict[str,Any]:
        """SIMULATION WRITE: assign diagnostic inspection to technician; poll action completion before claiming findings."""
        return await act('inspect',{'character_id':character_id,'component_id':component_id,'epoch':epoch},idempotency_key)
    @server.tool(annotations=write)
    async def perform_simulated_maintenance(machine_id:str,component_id:str,maintenance_action:str,epoch:str,idempotency_key:str|None=None)->dict[str,Any]:
        """SIMULATION ONLY controlled repair: requires explicit maintenance policy, STOPPED line, prior inspection; duration and recovery change real backend state. Never physical equipment."""
        return await act('maintenance',{'machine_id':machine_id,'component_id':component_id,'maintenance_action':maintenance_action,'epoch':epoch},idempotency_key)
    return server
