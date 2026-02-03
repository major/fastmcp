"""OpenTelemetry instrumentation for FastMCP.

This module provides native OpenTelemetry integration for FastMCP servers and clients.
It uses only the opentelemetry-api package, so telemetry is a no-op unless the user
installs an OpenTelemetry SDK and configures exporters.

Example usage with SDK:
    ```python
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

    # Configure the SDK (user responsibility)
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)

    # Now FastMCP will emit traces
    from fastmcp import FastMCP
    mcp = FastMCP("my-server")
    ```
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opentelemetry.context import Context
    from opentelemetry.trace import Span, Tracer


def _check_otel_available() -> bool:
    """Check if OpenTelemetry is available and enabled via settings."""
    # Import here to avoid circular imports
    from fastmcp.settings import Settings

    settings = Settings()
    if not settings.telemetry_enabled:
        return False

    try:
        import opentelemetry  # noqa: F401

        return True
    except ImportError:
        return False


OTEL_AVAILABLE = _check_otel_available()

if OTEL_AVAILABLE:
    from opentelemetry import context as otel_context
    from opentelemetry import propagate, trace
    from opentelemetry.trace import StatusCode
    from opentelemetry.trace import get_tracer as otel_get_tracer
else:
    otel_context = None  # type: ignore
    propagate = None  # type: ignore
    trace = None  # type: ignore
    StatusCode = None  # type: ignore
    otel_get_tracer = None  # type: ignore


class _NoOpSpanContext:
    """No-op span context when OpenTelemetry is unavailable."""

    is_valid = False


class _NoOpSpan:
    """No-op span implementation when OpenTelemetry is unavailable."""

    def set_attributes(self, attributes: dict[str, Any]) -> None:
        """No-op implementation."""

    def set_attribute(self, key: str, value: Any) -> None:
        """No-op implementation."""

    def record_exception(self, exception: BaseException) -> None:
        """No-op implementation."""

    def set_status(self, status: Any) -> None:
        """No-op implementation."""

    def is_recording(self) -> bool:
        """Return False since no-op spans don't record."""
        return False

    def get_span_context(self) -> _NoOpSpanContext:
        """Return no-op span context."""
        return _NoOpSpanContext()

    def __enter__(self) -> _NoOpSpan:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""


class _NoOpTracer:
    """No-op tracer implementation when OpenTelemetry is unavailable."""

    def start_as_current_span(self, name: str, **kwargs: Any) -> _NoOpSpan:
        """Return a no-op span."""
        return _NoOpSpan()


class _NoOpContext:
    """No-op context implementation when OpenTelemetry is unavailable."""


INSTRUMENTATION_NAME = "fastmcp"

TRACE_PARENT_KEY = "fastmcp.traceparent"
TRACE_STATE_KEY = "fastmcp.tracestate"


def get_tracer(version: str | None = None) -> Tracer | Any:
    """Get the FastMCP tracer for creating spans.

    Args:
        version: Optional version string for the instrumentation

    Returns:
        A tracer instance. Returns a no-op tracer if no SDK is configured.
    """
    if not OTEL_AVAILABLE:
        return _NoOpTracer()
    return otel_get_tracer(INSTRUMENTATION_NAME, version)


def inject_trace_context(
    meta: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Inject current trace context into a meta dict for MCP request propagation.

    Args:
        meta: Optional existing meta dict to merge with trace context

    Returns:
        A new dict containing the original meta (if any) plus trace context keys,
        or None if no trace context to inject and meta was None
    """
    if not OTEL_AVAILABLE:
        return meta

    carrier: dict[str, str] = {}
    propagate.inject(carrier)

    trace_meta: dict[str, Any] = {}
    if "traceparent" in carrier:
        trace_meta[TRACE_PARENT_KEY] = carrier["traceparent"]
    if "tracestate" in carrier:
        trace_meta[TRACE_STATE_KEY] = carrier["tracestate"]

    if trace_meta:
        return {**(meta or {}), **trace_meta}
    return meta


def record_span_error(span: Span, exception: BaseException) -> None:
    """Record an exception on a span and set error status."""
    if not OTEL_AVAILABLE or isinstance(span, _NoOpSpan):
        return
    from opentelemetry.trace import Status

    span.record_exception(exception)
    span.set_status(Status(StatusCode.ERROR))


def extract_trace_context(meta: dict[str, Any] | None) -> Context | Any:
    """Extract trace context from an MCP request meta dict.

    If already in a valid trace (e.g., from HTTP propagation), the existing
    trace context is preserved and meta is not used.

    Args:
        meta: The meta dict from an MCP request (ctx.request_context.meta)

    Returns:
        An OpenTelemetry Context with the extracted trace context,
        or the current context if no trace context found or already in a trace
    """
    if not OTEL_AVAILABLE:
        return _NoOpContext()

    current_span = trace.get_current_span()
    if current_span.get_span_context().is_valid:
        return otel_context.get_current()

    if not meta:
        return otel_context.get_current()

    carrier: dict[str, str] = {}
    if TRACE_PARENT_KEY in meta:
        carrier["traceparent"] = str(meta[TRACE_PARENT_KEY])
    if TRACE_STATE_KEY in meta:
        carrier["tracestate"] = str(meta[TRACE_STATE_KEY])

    if carrier:
        return propagate.extract(carrier)
    return otel_context.get_current()


__all__ = [
    "INSTRUMENTATION_NAME",
    "OTEL_AVAILABLE",
    "TRACE_PARENT_KEY",
    "TRACE_STATE_KEY",
    "_NoOpSpan",
    "extract_trace_context",
    "get_tracer",
    "inject_trace_context",
    "record_span_error",
]
