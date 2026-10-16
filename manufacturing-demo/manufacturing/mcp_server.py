from typing import Annotated, Any
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field, ValidationError
from jsonschema import Draft202012Validator
from starlette.concurrency import run_in_threadpool

from .errors import ServiceError
from .schemas import DatasetFilters, Features, TrainInput, TrainingConfiguration


class StrictFastMCP(FastMCP):
    async def list_tools(self):
        tools = await super().list_tools()
        for tool in tools:
            tool.inputSchema = {**tool.inputSchema, "additionalProperties": False}
        return tools

    async def call_tool(self, name, arguments):
        tool = next((tool for tool in await self.list_tools() if tool.name == name), None)
        if not tool or not Draft202012Validator(tool.inputSchema).is_valid(arguments):
            raise ToolError("INVALID_ARGUMENTS: Arguments must match the discovered tool schema")
        return await super().call_tool(name, arguments)


def build_mcp(app, settings):
    hosts = settings.mcp_allowed_hosts.split(",")
    server = StrictFastMCP("Manufacturing Quality Model", stateless_http=True, json_response=True,
                    streamable_http_path="/mcp", max_request_body_size=65536,
                    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
                        allowed_hosts=hosts, allowed_origins=[f"http://{host}" for host in hosts]))
    readonly = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
    changes = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

    async def invoke(fn, *args):
        try:
            return await run_in_threadpool(fn, *args)
        except ServiceError as error:
            raise ToolError(f"{error.code}: {error.message}") from None
        except (ValueError, ValidationError):
            raise ToolError("INVALID_ARGUMENTS: Supply valid features, identifiers and bounded pagination") from None
        except Exception:
            raise ToolError("SERVICE_ERROR: Manufacturing operation failed; check service health") from None

    @server.tool(annotations=readonly)
    async def get_manufacturing_dataset(limit: Annotated[int, Field(ge=1, le=100)] = 25,
        offset: Annotated[int, Field(ge=0, le=100000)] = 0,
        machine_id: Annotated[str | None, Field(description="Exact dataset machine code, such as M01. Use only when the user supplies an exact code; omit for machine types/names such as milling.")] = None,
        quality_label: Annotated[int, Field(ge=0, le=1)] | None = None) -> dict[str, Any]:
        """Retrieve synthetic manufacturing measurements. Seeded machine codes are M01–M05. Do not infer machine_id from natural-language names or types; omit it unless the user supplies an exact code. Ground-truth labels are not stored."""
        return await invoke(app.state.dataset.records, DatasetFilters(limit=limit, offset=offset, machine_id=machine_id, quality_label=quality_label))

    @server.tool(annotations=changes)
    async def train_quality_model(use_all_approved_training_data: bool = True,
                                  configuration: TrainingConfiguration | None = None) -> dict[str, Any]:
        """STATE CHANGE: requires explicit user confirmation. Queue LogisticRegression retraining on approved data, excluding fixed held-out products. Returns job_id immediately; poll get_training_status until ready before reporting metrics. Never claim training finished from a queued result."""
        request = TrainInput(use_all_approved_training_data=use_all_approved_training_data,
                             configuration=configuration or TrainingConfiguration())
        return await invoke(app.state.model.submit, request)

    @server.tool(annotations=readonly)
    async def get_training_status(job_id: str) -> dict[str, Any]:
        """Get a queued/running/ready/failed training job, version, training samples and actual held-out metrics. Poll again if queued/running; training is usually fast for this synthetic dataset."""
        try:
            UUID(job_id)
        except ValueError:
            raise ToolError("INVALID_JOB_ID: Supply the training job UUID") from None
        return await invoke(app.state.model.job, job_id)

    @server.tool(annotations=readonly)
    async def predict_product_quality(temperature: float, pressure: float, vibration: float,
        production_speed: float, humidity: float, material_quality: float) -> dict[str, Any]:
        """Classify six measured features using the deployed synthetic quality model. Return actual model probabilities and version; 0 means Defective, 1 Good. Not a real industrial safety assessment."""
        try:
            request = Features(temperature=temperature, pressure=pressure, vibration=vibration,
                production_speed=production_speed, humidity=humidity, material_quality=material_quality)
        except ValidationError:
            raise ToolError("INVALID_FEATURES: Provide finite features within documented physical bounds") from None
        return (await invoke(app.state.model.predict, [request.model_dump()]))[0]

    @server.tool(annotations=readonly)
    async def classify_manufacturing_dataset(limit: Annotated[int, Field(ge=1, le=100)] = 25,
        offset: Annotated[int, Field(ge=0, le=100000)] = 0,
        machine_id: Annotated[str | None, Field(description="Exact dataset machine code, such as M01. Use only when the user supplies an exact code; omit for machine types/names such as milling.")] = None,
        quality_label: Annotated[int, Field(ge=0, le=1)] | None = None,
        predicted_label: Annotated[int, Field(ge=0, le=1)] | None = None) -> dict[str, Any]:
        """Classify synthetic records. Seeded machine codes are M01–M05. Do not infer machine_id from natural-language names or types; omit it unless the user supplies an exact code. Ground-truth labels are not stored. Use predicted_label=0 for predicted defective."""
        return await invoke(app.state.dataset.predictions, DatasetFilters(limit=limit, offset=offset,
            machine_id=machine_id, quality_label=quality_label, predicted_label=predicted_label))

    @server.tool(annotations=readonly)
    async def get_quality_model_metrics() -> dict[str, Any]:
        """Return measured accuracy/precision/recall/F1/confusion matrix on the fixed held-out SYNTHETIC test set, model version, timestamp and sample counts. Not training-set accuracy or real manufacturing performance."""
        return await invoke(app.state.model.metrics)

    return server
