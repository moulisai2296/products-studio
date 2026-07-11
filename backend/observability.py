"""Thin Langfuse observability wrapper.

Rules (CLAUDE.md §7):
- One trace per session (trace keyed by session_id).
- One generation span per model call with model, latency, cost.
- LANGFUSE_ENABLED=0 must cleanly no-op EVERYTHING.
- Observability must NEVER take down the app — every call is guarded.

We pass observation objects explicitly (rather than relying on the SDK's
context-var "current observation") because provider calls run inside
asyncio.to_thread worker threads where context vars don't propagate.
"""
from contextlib import contextmanager
import time

import config

_client = None
_init_tried = False


def _get_client():
    """Lazily init the Langfuse client. Returns None if disabled or unavailable."""
    global _client, _init_tried
    if not config.LANGFUSE_ENABLED:
        return None
    if _init_tried:
        return _client
    _init_tried = True
    if not (config.LANGFUSE_PUBLIC_KEY and config.LANGFUSE_SECRET_KEY):
        print("[langfuse] enabled but keys missing — disabling")
        _client = None
        return None
    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=config.LANGFUSE_PUBLIC_KEY,
            secret_key=config.LANGFUSE_SECRET_KEY,
            host=config.LANGFUSE_HOST,
        )
        print("[langfuse] client initialized")
    except Exception as e:  # pragma: no cover - defensive
        print(f"[langfuse] init failed, disabling: {e}")
        _client = None
    return _client


class _Span:
    """Guarded wrapper around a Langfuse observation. All methods swallow errors."""

    def __init__(self, obs):
        self._obs = obs

    def update(self, **kwargs):
        if self._obs is None:
            return
        try:
            self._obs.update(**kwargs)
        except Exception:
            try:  # some kwargs may be unsupported on this SDK version — retry bare
                self._obs.update(metadata=kwargs.get("metadata"))
            except Exception:
                pass

    def end(self):
        if self._obs is None:
            return
        try:
            self._obs.end()
        except Exception:
            pass


def _start_generation(client, name, model, session_id, inp, metadata):
    """Best-effort creation of a generation observation across SDK variants."""
    md = {**(metadata or {})}
    if session_id:
        md["session_id"] = session_id
    # Preferred modern (v3/v4) API.
    try:
        obs = client.start_observation(
            as_type="generation", name=name, model=model, input=inp, metadata=md
        )
    except TypeError:
        try:
            obs = client.start_observation(name=name)
        except Exception:
            return None
    except Exception:
        return None
    # Tie the observation to a session-keyed trace so all calls group per campaign.
    if session_id:
        try:
            obs.update_trace(session_id=session_id, name=f"campaign:{session_id}")
        except Exception:
            pass
    return obs


@contextmanager
def generation(name, model=None, session_id=None, inp=None, metadata=None):
    """Context manager wrapping one model call as a Langfuse generation span.

    Usage:
        with observability.generation("angle", model=M, session_id=sid) as span:
            ... call model ...
            span.set_result(cost_usd=0.034, output="ok")
    """
    client = _get_client()
    obs = _start_generation(client, name, model, session_id, inp, metadata) if client else None
    span = _Span(obs)
    start = time.time()

    # Attach a convenience method for provider code to record cost/output/latency.
    def set_result(cost_usd=None, output=None, latency_ms=None, extra=None):
        latency = latency_ms if latency_ms is not None else int((time.time() - start) * 1000)
        md = {"latency_ms": latency}
        if cost_usd is not None:
            md["cost_usd"] = cost_usd
        if extra:
            md.update(extra)
        kwargs = {"metadata": md}
        if output is not None:
            kwargs["output"] = output
        if cost_usd is not None:
            # Structured cost so Langfuse dashboards sum spend correctly.
            kwargs["cost_details"] = {"total": cost_usd}
        span.update(**kwargs)

    span.set_result = set_result  # type: ignore[attr-defined]
    try:
        yield span
    finally:
        span.end()
        if client is not None:
            try:
                client.flush()  # short-lived request threads must flush to send
            except Exception:
                pass


def flush():
    client = _get_client()
    if client is not None:
        try:
            client.flush()
        except Exception:
            pass
