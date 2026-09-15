from __future__ import annotations

import json
import traceback


def _client():
    """Import the gRPC client lazily so registration works without grpc/fpzip/etc. installed."""
    if __package__:
        from . import client
    else:  # Allows direct execution from the plugin root.
        import client  # type: ignore
    return client


def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def drawthings_list(args=None, **kwargs) -> str:
    args = args or {}
    try:
        kind = args.get("kind", "all")
        # schema uses controlnets; accept common variants
        if kind in {"controlNets", "control_nets", "controls"}:
            kind = "controlnets"
        data = _client().list_inventory(kind=kind, query=args.get("query"))
        return _json({"ok": True, "endpoint": _endpoint_info(), **data})
    except Exception as e:
        return _json({"ok": False, "error": str(e), "traceback": traceback.format_exc(limit=3)})


def drawthings_generate(args=None, **kwargs) -> str:
    args = args or {}
    try:
        result = _client().generate_image(args)
        return _json(result)
    except Exception as e:
        return _json({"ok": False, "error": str(e), "traceback": traceback.format_exc(limit=3)})


def _endpoint_info():
    host, port, tls, tls_name = _client()._endpoint()
    return {"host": host, "port": port, "tls": tls, "tls_name": tls_name}
