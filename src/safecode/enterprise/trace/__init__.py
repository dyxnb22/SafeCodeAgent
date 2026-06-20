"""Enterprise trace events and persistence.

中文包说明：企业运行追踪与持久化。
- 记录节点、审批、策略等运行时事件，供可观测性与排障。
- 追踪载荷须经脱敏；不得将 trace 内容当作策略或执行依据。
"""

__all__ = [
    "TRACE_SCHEMA_VERSION",
    "TraceContext",
    "TraceEmitter",
    "TraceEvent",
    "TraceEventType",
    "TraceSession",
    "emit_standalone_trace",
    "make_event_id",
    "trace_file_path",
]


def __getattr__(name: str):
    if name in {"TraceEmitter", "trace_file_path"}:
        from safecode.enterprise.trace.emitter import TraceEmitter, trace_file_path

        return {"TraceEmitter": TraceEmitter, "trace_file_path": trace_file_path}[name]
    if name in {"TRACE_SCHEMA_VERSION", "TraceContext", "TraceEvent", "TraceEventType", "make_event_id"}:
        from safecode.enterprise.trace import events as events_module

        return getattr(events_module, name)
    if name in {"TraceSession", "emit_standalone_trace"}:
        from safecode.enterprise.trace.session import TraceSession, emit_standalone_trace

        return {"TraceSession": TraceSession, "emit_standalone_trace": emit_standalone_trace}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
