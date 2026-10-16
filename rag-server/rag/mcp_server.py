from typing import Annotated, Any
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import StringConstraints, ValidationError
from starlette.concurrency import run_in_threadpool

from .errors import ServiceError
from .observability import request_id_context
from .schemas import SearchInput


def build_mcp(app, settings):
    hosts = [host.strip() for host in settings.mcp_allowed_hosts.split(",") if host.strip()]
    server = FastMCP(
        "Local RAG Evidence",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/mcp",
        max_request_body_size=65536,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=hosts,
            allowed_origins=[f"http://{host}" for host in hosts],
        ),
    )
    readonly = ToolAnnotations(
        readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
    )

    async def invoke(function, *args, **kwargs):
        try:
            return await run_in_threadpool(function, *args, **kwargs)
        except ServiceError as error:
            raise ToolError(f"{error.code}: {error.message}") from None
        except (ValueError, ValidationError):
            raise ToolError(
                "INVALID_ARGUMENTS: Supply valid identifiers and bounded search parameters"
            ) from None
        except Exception:
            raise ToolError("SERVICE_ERROR: Could not complete the retrieval request") from None

    @server.tool(annotations=readonly)
    async def find_device(
        name: Annotated[str, StringConstraints(min_length=1, max_length=200)], model: str | None = None
    ) -> dict[str, Any]:
        """Find exact device-name/model matches; report ambiguity without guessing device identity."""
        return await invoke(app.state.knowledge.find_device, name, model)

    @server.tool(annotations=readonly)
    async def get_device_issues(device_id: str, category: str | None = None) -> dict[str, Any]:
        """Return known issues. Possible causes remain unconfirmed hypotheses; includes pagination metadata."""
        try:
            identifier = UUID(device_id)
        except ValueError:
            raise ToolError("INVALID_DEVICE_ID: Provide a UUID") from None
        return await invoke(app.state.knowledge.list_issues, 0, 100, identifier, category)

    @server.tool(annotations=readonly)
    async def search_knowledge(
        query: str, device_id: str | None = None, issue_category: str | None = None, top_k: int = 10
    ) -> dict[str, Any]:
        """Retrieve scoped issue/document evidence using vector, keyword and RRF search; never generate an answer."""
        try:
            request = SearchInput(
                query=query, device_id=device_id, issue_category=issue_category, top_k=top_k
            )
        except (ValueError, ValidationError):
            raise ToolError(
                "INVALID_SEARCH: Provide valid filters, a nonblank query and top_k from 1 to 50"
            ) from None
        return await invoke(app.state.retrieval.search, request, request_id_context.get())

    @server.tool(annotations=readonly)
    async def get_document_context(chunk_ids: list[str]) -> dict[str, Any]:
        """Return ready source passages by chunk UUID, preserving document/version/section/page references."""
        return await invoke(app.state.knowledge.context, chunk_ids)

    return server
