"""Client-side telemetry helpers."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from fastmcp.telemetry import OTEL_AVAILABLE, get_tracer

if OTEL_AVAILABLE:
    from opentelemetry.trace import SpanKind, Status, StatusCode
else:
    from fastmcp.telemetry import _NoOpSpan


@contextmanager
def client_span(
    name: str,
    method: str,
    component_key: str,
    session_id: str | None = None,
    resource_uri: str | None = None,
) -> Generator[Any, None, None]:
    """Create a CLIENT span with standard MCP attributes.

    Automatically records any exception on the span and sets error status.
    """
    if not OTEL_AVAILABLE:
        yield _NoOpSpan()
        return

    tracer = get_tracer()
    with tracer.start_as_current_span(name, kind=SpanKind.CLIENT) as span:
        attrs: dict[str, str] = {
            # RPC semantic conventions
            "rpc.system": "mcp",
            "rpc.method": method,
            # MCP semantic conventions
            "mcp.method.name": method,
            # FastMCP-specific attributes
            "fastmcp.component.key": component_key,
        }
        if session_id:
            attrs["mcp.session.id"] = session_id
        if resource_uri:
            attrs["mcp.resource.uri"] = resource_uri
        span.set_attributes(attrs)
        try:
            yield span
        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR))
            raise


__all__ = ["client_span"]
