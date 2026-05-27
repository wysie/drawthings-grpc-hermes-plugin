from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import flatbuffers
import fpzip
import grpc
import numpy as np
from PIL import Image

try:
    from .generated import imageService_pb2, imageService_pb2_grpc
    from .generated.config_generated import GenerationConfigurationT, LoRAT, LoRAMode, SamplerType, SeedMode
except ImportError:  # Allows pytest/direct import from plugin root.
    from generated import imageService_pb2, imageService_pb2_grpc  # type: ignore
    from generated.config_generated import GenerationConfigurationT, LoRAT, LoRAMode, SamplerType, SeedMode  # type: ignore

_CERT = b'''-----BEGIN CERTIFICATE-----
MIIFHTCCAwWgAwIBAgIUWxJuoygy7Hsb9bcSfggNGLGZJW4wDQYJKoZIhvcNAQEL
BQAwHjEcMBoGA1UEAwwTRHJhdyBUaGluZ3MgUm9vdCBDQTAeFw0yNDEwMTUxNzI3
NTJaFw0zNDEwMTMxNzI3NTJaMB4xHDAaBgNVBAMME0RyYXcgVGhpbmdzIFJvb3Qg
Q0EwggIiMA0GCSqGSIb3DQEBAQUAA4ICDwAwggIKAoICAQDe/RKAuabH2pEadZj6
JRTOaEIMYXsAI7ZIG+LSAEkyK/QZAMdLq+wBq6uJDIEvTXMyyhNgkI3oUnS2PJqi
y9lzGAh1s2y6MDG17BFboyriW0y6BKd42amX/g9A40ZC1cBs2NI9e0zjy/vhHLw1
EHK1XDLsIYAZvqQLJR3zRslHTHN6BysNWNmO/s1myLHQzbjyg4+/JHqma5Xatz0W
I5Wi6zxu/G1IdWeO6tlWWBSArDbhru+rb2U9p9/jKGW7fOom7sH9oBpj7q+xcrr5
h2Aoam4xRqxc3SG7TRc1inEki86/FoWCARSqGo2t7q/brkwwGbeZsuwKhIuhWGzW
CJKp0NvD11HyCqsJsLMTx9PXzEsCDFsios+zI6zu1aIVomO5h8d59oxMGEvNozIc
gSHJI3pCiHmJt0o9xoRi0UGiB6PP3k4ZzxTV30wt0oMOzS8dgMdl1u0zpAc2aEGG
4cdWQaDP2UgZlNQyzGbGUC2Q2ln1ghTlEBAs23/yDZyEbtWj+Qo1Isk80CXISs8/
H4cdM9Xw/Rt5fGxSaNzHJZJ9gK8YFI0z7IDiQp9nWkMqyDhGjhT4ZR847Nz52gcK
zuqmSK6B7ksumilchQ8hq79VAAvZqQoyVIvLvkbb6pXZbH0qTK5yk0YQVJ49JU1L
XnB4Iu8IuDxTLmtW2WoCjUZaqQIDAQABo1MwUTAdBgNVHQ4EFgQUhmFk2qHWAU6/
3u6FyCnk2vaV0fswHwYDVR0jBBgwFoAUhmFk2qHWAU6/3u6FyCnk2vaV0fswDwYD
VR0TAQH/BAUwAwEB/zANBgkqhkiG9w0BAQsFAAOCAgEAdvryE1xbhpyDjtP+I95Z
tgmlkmIWTPoHL5WO20SWtWjryHTs0XGXkohqSFKBqYTOVTyRCTtUTF4nWoNfBhlz
aOExf64UgvYHO4NxcPNjUH2Yx/AKFWBeHx50jfjz/zTSqhAHv8rlYDt6rlLs1aFm
rNj3DObqmTfDoI8qkdLK8bekjhul6PusmezhW+qa/DMvDRy3moUugpXwzvyG5GRW
C3+nNbBdCdblUyiEgFu5htH6hSSu2IX5t/ryoKNjAAfUxMKcNFdYCnzWiHKOlrmp
wYL4YhVQZZYmis8ZIFOQ+BKVQHJcqE5bdrbNbCpurMNODEuDDB/VkbGHEVFVgB0n
x+ZtaGnfTeJJ6h7IIl+Gnpx0u9k+2pu78cEQ+6ZYKaGUoOKccxgipsSXWL75qHl9
7/scB3imqRq0Q7/jKP6mvcB3/5irQwVmczsFwELLP0LJdsCZMcQQQsSCGuskzcAJ
iiiGzRVTfYFUu2hJ5JIgewg+NEzMCwzR5yyWacBcrrDxQTymTNW9NWahHxvdZJHd
zRd4Y3HNLPikGg37mCYIPWtUxJCU7/lZleNSqlMBhDdbIZcAqaHOQlYJQSZaTMwK
kWF1y/C6TdCKWyXhAEV8zp/0q4b6vC1ynn/GfopROPXceLbGA+BLG9JEQ1AiGae3
ejQ40oILyZjEclMPGLYjqoQ=
-----END CERTIFICATE-----
'''

PLUGIN_DIR = Path(__file__).parent
HERMES_HOME = Path(os.getenv("HERMES_HOME", str(Path.home() / ".hermes"))).expanduser()
USER_CONFIG_PATH = HERMES_HOME / "drawthings-grpc" / "config.json"

SAMPLERS = {
    "dpm++ 2m karras": SamplerType.DPMPP2MKarras,
    "euler a": SamplerType.EulerA,
    "ddim": SamplerType.DDIM,
    "plms": SamplerType.PLMS,
    "dpm++ sde karras": SamplerType.DPMPPSDEKarras,
    "unipc": SamplerType.UniPC,
    "lcm": SamplerType.LCM,
    "tcd": SamplerType.TCD,
    "euler a trailing": SamplerType.EulerATrailing,
    "dpm++ sde trailing": SamplerType.DPMPPSDETrailing,
    "dpm++ 2m trailing": SamplerType.DPMPP2MTrailing,
    "ddim trailing": SamplerType.DDIMTrailing,
    "unipc trailing": SamplerType.UniPCTrailing,
    "tcd trailing": SamplerType.TCDTrailing,
}

@dataclass
class Inventory:
    models: list[dict[str, Any]]
    loras: list[dict[str, Any]]
    controlnets: list[dict[str, Any]]
    upscalers: list[dict[str, Any]]
    textual_inversions: list[dict[str, Any]]


def _as_bool(v: Any, default: bool = True) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    return str(v).lower() not in {"0", "false", "no"}


def _endpoint() -> tuple[str, int, bool, str]:
    cfg = plugin_config().get("endpoint", {})
    merged = plugin_config()
    host = os.getenv("DRAWTHINGS_GRPC_HOST") or cfg.get("host") or merged.get("host") or "localhost"
    port = int(os.getenv("DRAWTHINGS_GRPC_PORT") or cfg.get("port") or merged.get("port") or 7859)
    tls = _as_bool(os.getenv("DRAWTHINGS_GRPC_TLS"), _as_bool(cfg.get("tls", merged.get("tls", True))))
    tls_name = os.getenv("DRAWTHINGS_GRPC_TLS_NAME") or cfg.get("tls_name") or merged.get("tls_name") or "localhost"
    return str(host), port, tls, str(tls_name)


def _channel():
    host, port, tls, tls_name = _endpoint()
    opts = [("grpc.max_send_message_length", -1), ("grpc.max_receive_message_length", -1)]
    if tls:
        # Draw Things cert CN is localhost even when accessed over LAN IP.
        opts.append(("grpc.ssl_target_name_override", tls_name))
        return grpc.secure_channel(f"{host}:{port}", grpc.ssl_channel_credentials(_CERT), options=opts)
    return grpc.insecure_channel(f"{host}:{port}", options=opts)


def _stub():
    return imageService_pb2_grpc.ImageGenerationServiceStub(_channel())


def _json_load_bytes(b: bytes | None) -> list[dict[str, Any]]:
    if not b:
        return []
    return json.loads(b.decode("utf-8"))


def slugify(s: str) -> str:
    s = s.lower().replace("+", " plus ")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def _load_json(path: Path) -> dict[str, Any]:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {}


def _deep_merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = dict(a or {})
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def plugin_config() -> dict[str, Any]:
    built_in = _load_json(PLUGIN_DIR / "defaults.json")
    user = _load_json(USER_CONFIG_PATH)
    return _deep_merge(built_in, user)


def _configured_aliases() -> dict[str, str]:
    return {slugify(k): v for k, v in plugin_config().get("aliases", {}).items()}


def aliases_for(item: dict[str, Any]) -> list[str]:
    vals = {item.get("name", ""), item.get("file", "")}
    aliases: set[str] = set()
    for v in vals:
        if not v:
            continue
        stem = re.sub(r"\.(ckpt|safetensors|bin)$", "", v, flags=re.I)
        base = slugify(stem.replace("_", " "))
        if base:
            aliases.add(base)
            aliases.add(base.replace("-", ""))
            aliases.add(re.sub(r"-(q[0-9]p|f16|q8p|q6p)+$", "", base))
            aliases.add(re.sub(r"-1-0$", "", base))
    name = item.get("name", "")
    file = item.get("file", "")
    low = f"{name} {file}".lower()
    curated = {
        "z_image_turbo": ["z-image-turbo", "zturbo", "zimage", "z-image"],
        "qwen_image_2512": ["qwen-image-2512", "qwen2512", "qwen-image", "qwen"],
        "flux_2_klein": ["flux2-klein", "flux-klein", "flux2-4b"],
        "flux_1_schnell": ["flux-schnell", "flux1-schnell", "schnell"],
        "realvisxl": ["realvisxl", "realvisxl-v4", "realvis"],
        "juggernaut": ["juggernaut-xl", "juggernaut-v9", "juggernaut"],
        "lightning_4_step": ["qwen-lightning", "qwen-image-lightning", "qwen2512-lightning", "lightning-4step"],
        "turbo_4_step": ["qwen-turbo-lora", "qwen2512-turbo-lora", "turbo-4step"],
        "faceid": ["faceid", "ip-adapter-faceid"],
    }
    for needle, adds in curated.items():
        if needle in low:
            aliases.update(adds)
    for alias, target in _configured_aliases().items():
        if target == file:
            aliases.add(alias)
    return sorted(a for a in aliases if a)


def _configured_lora_files(cfg: dict[str, Any] | None = None) -> list[str]:
    """Return LoRA files the user/config knows about.

    Draw Things gRPC Echo can return an empty LoRA metadata list even while
    FilesExist/GenerateImage can see and use the LoRA files. Keep config as the
    source of truth for those known files, but verify existence before exposing
    them.
    """
    cfg = cfg or plugin_config()
    files: set[str] = set()
    for file in (cfg.get("lora_defaults") or {}).keys():
        if isinstance(file, str) and file:
            files.add(file)
    for target in (cfg.get("aliases") or {}).values():
        if isinstance(target, str) and "lora" in target.lower():
            files.add(target)
    return sorted(files)


def _existing_files(files: list[str]) -> set[str]:
    if not files:
        return set()
    try:
        resp = _stub().FilesExist(imageService_pb2.FileListRequest(files=files), timeout=30)
        return {f for f, exists in zip(resp.files, resp.existences) if exists}
    except Exception:
        return set()


def _synthetic_loras_from_config(models: list[dict[str, Any]], cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cfg = cfg or plugin_config()
    existing = _existing_files(_configured_lora_files(cfg))
    if not existing:
        return []
    default_model = cfg.get("default_model")
    version = None
    if default_model:
        try:
            version = resolve(models, str(default_model), default_first=True).get("version")
        except Exception:
            version = None
    out = []
    for file in sorted(existing):
        aliases = [alias for alias, target in (cfg.get("aliases") or {}).items() if target == file]
        friendly = aliases[0] if aliases else re.sub(r"\.(ckpt|safetensors|bin)$", "", file, flags=re.I)
        out.append({
            "name": friendly.replace("-", " ").replace("_", " ").title(),
            "file": file,
            "version": version,
            "synthetic": True,
            "source": "config+FilesExist",
        })
    return out


def inventory() -> Inventory:
    resp = _stub().Echo(imageService_pb2.EchoRequest(name="Agent Hammy"), timeout=30)
    models = _json_load_bytes(resp.override.models)
    loras = _json_load_bytes(resp.override.loras)
    synthetic_loras = _synthetic_loras_from_config(models)
    seen_lora_files = {x.get("file") for x in loras}
    loras.extend(x for x in synthetic_loras if x.get("file") not in seen_lora_files)
    return Inventory(
        models=models,
        loras=loras,
        controlnets=_json_load_bytes(resp.override.controlNets),
        upscalers=_json_load_bytes(resp.override.upscalers),
        textual_inversions=_json_load_bytes(resp.override.textualInversions),
    )


def _decorate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for item in items:
        x = dict(item)
        x["aliases"] = aliases_for(item)
        out.append(x)
    return out


def list_inventory(kind: str = "all", query: str | None = None) -> dict[str, Any]:
    inv = inventory()
    buckets = {
        "models": _decorate(inv.models),
        "loras": _decorate(inv.loras),
        "controlnets": _decorate(inv.controlnets),
        "upscalers": _decorate(inv.upscalers),
        "textual_inversions": _decorate(inv.textual_inversions),
    }
    if query:
        q = slugify(query)
        def keep(item):
            hay = " ".join([item.get("name", ""), item.get("file", ""), *item.get("aliases", [])]).lower()
            return query.lower() in hay or q in slugify(hay)
        buckets = {k: [x for x in v if keep(x)] for k, v in buckets.items()}
    if kind and kind != "all":
        return {kind: buckets.get(kind, [])}
    return buckets


def resolve(items: list[dict[str, Any]], value: str | None, default_first: bool = False) -> dict[str, Any]:
    if not value and default_first:
        return items[0]
    if not value:
        raise ValueError("value is required")
    q = value.strip().lower()
    qslug = slugify(value)
    configured = _configured_aliases()
    if qslug in configured:
        target = configured[qslug].lower()
        for item in items:
            if target == item.get("file", "").lower() or target == item.get("name", "").lower():
                return item
    for item in items:
        if q == item.get("file", "").lower() or q == item.get("name", "").lower():
            return item
    for item in items:
        if qslug in aliases_for(item):
            return item
    candidates = [i for i in items if qslug in slugify(i.get("name", "") + " " + i.get("file", ""))]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        names = [f"{c.get('name')} ({c.get('file')})" for c in candidates]
        raise ValueError(f"Ambiguous '{value}'. Candidates: {names}")
    raise ValueError(f"No match for '{value}'")


def generation_defaults(model: dict[str, Any], lora: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = plugin_config()
    defaults: dict[str, Any] = {
        "steps": 20,
        "sampler": "Euler A Trailing",
        "cfg": 1.0,
        "shift": 1.0,
        "shift_terminal": None,
        "guidance_embed": 3.5,
        "resolution_dependent_shift": True,
    }
    version = model.get("version")
    if version:
        defaults = _deep_merge(defaults, cfg.get("version_defaults", {}).get(version, {}))
    model_file = model.get("file")
    if model_file:
        defaults = _deep_merge(defaults, cfg.get("model_defaults", {}).get(model_file, {}))
    if lora and lora.get("file"):
        defaults = _deep_merge(defaults, cfg.get("lora_defaults", {}).get(lora["file"], {}))
    return defaults


def _default_steps(model: dict[str, Any], lora: dict[str, Any] | None) -> int:
    return int(generation_defaults(model, lora).get("steps", 20))


def _safe_dim(v: int) -> int:
    return max(64, min(2048, int(v) // 64 * 64))


def _decode_image(raw: bytes) -> Image.Image:
    ints = np.frombuffer(raw, dtype=np.uint32, count=17)
    height, width, channels = [int(x) for x in ints[6:9]]
    if ints[0] == 1012247:
        arr = fpzip.decompress(raw[68:], order="C").astype(np.float16)
    else:
        arr = np.frombuffer(raw[68:], dtype=np.float16)
    if channels in (3, 4):
        data = np.clip((arr.reshape((height, width, channels)) + 1) * 127, 0, 255).astype(np.uint8)
        return Image.fromarray(data, "RGBA" if channels == 4 else "RGB")
    raise ValueError(f"Unsupported Draw Things response channels={channels}; expected decoded RGB/RGBA")


def generate_image(args: dict[str, Any]) -> dict[str, Any]:
    prompt = (args.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required")
    inv = inventory()
    cfg = plugin_config()
    selected_model = args.get("model") or cfg.get("default_model") or "qwen-image-2512"
    model = resolve(inv.models, selected_model, default_first=True)
    selected_lora = args.get("lora") if "lora" in args else cfg.get("default_lora")
    if isinstance(selected_lora, str) and selected_lora.strip().lower() in {"", "none", "null", "false", "off"}:
        selected_lora = None
    lora = resolve(inv.loras, selected_lora) if selected_lora else None

    width = _safe_dim(args.get("width", 1024))
    height = _safe_dim(args.get("height", 1024))
    defaults = generation_defaults(model, lora)
    steps = int(args.get("steps") or defaults.get("steps", 20))
    sampler_name = (args.get("sampler") or defaults.get("sampler") or "Euler A Trailing").lower()
    sampler_key = slugify(sampler_name).replace("-", " ")
    sampler = SAMPLERS.get(sampler_name) or SAMPLERS.get(sampler_key) or SamplerType.EulerATrailing
    seed = int(args.get("seed") or (int(time.time()) % 4294967295))

    cfg = GenerationConfigurationT()
    cfg.model = model["file"]
    cfg.startWidth = width // 64
    cfg.startHeight = height // 64
    cfg.seed = seed
    cfg.steps = steps
    cfg.guidanceScale = float(args.get("cfg", defaults.get("cfg", 1.0)))
    cfg.strength = 1.0
    cfg.sampler = sampler
    cfg.batchCount = 1
    cfg.batchSize = 1
    cfg.seedMode = SeedMode.ScaleAlike
    cfg.shift = float(args.get("shift", defaults.get("shift", 1.0)))
    unsupported_settings: dict[str, Any] = {}
    shift_terminal = args.get("shift_terminal", defaults.get("shift_terminal"))
    if shift_terminal is not None:
        # Newer/alternate Draw Things schemas may expose scheduler terminal shift.
        # The current public gRPC FlatBuffer schema used by this plugin does not,
        # so keep this best-effort and report when it cannot be applied.
        if hasattr(cfg, "shiftTerminal"):
            cfg.shiftTerminal = float(shift_terminal)
        elif hasattr(cfg, "shift_terminal"):
            cfg.shift_terminal = float(shift_terminal)
        else:
            unsupported_settings["shift_terminal"] = shift_terminal
    cfg.resolutionDependentShift = bool(args.get("resolution_dependent_shift", defaults.get("resolution_dependent_shift", True)))
    cfg.speedUpWithGuidanceEmbed = bool(args.get("speed_up", defaults.get("speed_up", True)))
    cfg.guidanceEmbed = float(args.get("guidance_embed", defaults.get("guidance_embed", 3.5)))
    cfg.tiledDecoding = True
    cfg.decodingTileWidth = 10
    cfg.decodingTileHeight = 10
    cfg.decodingTileOverlap = 2
    if lora:
        lt = LoRAT()
        lt.file = lora["file"]
        lt.weight = float(args.get("lora_weight", defaults.get("lora_weight", 1.0)))
        lt.mode = LoRAMode.All
        cfg.loras = [lt]

    builder = flatbuffers.Builder(0)
    builder.Finish(cfg.Pack(builder))
    override = imageService_pb2.MetadataOverride(models=json.dumps([model]).encode("utf-8"))
    if lora:
        override.loras = json.dumps([lora]).encode("utf-8")

    request = imageService_pb2.ImageGenerationRequest(
        scaleFactor=1,
        prompt=prompt,
        negativePrompt=args.get("negative_prompt") or "",
        configuration=bytes(builder.Output()),
        override=override,
        user="Agent Hammy",
        device=imageService_pb2.LAPTOP,
        chunked=False,
    )
    images: list[bytes] = []
    final_step = None
    for r in _stub().GenerateImage(request, timeout=int(args.get("timeout", 900))):
        if r.currentSignpost.HasField("sampling"):
            final_step = r.currentSignpost.sampling.step
        if r.generatedImages:
            images.extend(r.generatedImages)
    if not images:
        raise RuntimeError("Draw Things returned no images")

    out = args.get("output_path")
    if out:
        out_path = Path(out).expanduser()
    else:
        out_dir = Path(os.getenv("DRAWTHINGS_OUTPUT_DIR", str(Path.home() / "Pictures" / "Draw Things"))).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out_path = out_dir / f"drawthings-{slugify(model.get('name','model'))}-{stamp}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image = _decode_image(images[-1])
    image.save(out_path)
    return {
        "ok": True,
        "output_path": str(out_path),
        "model": {"name": model.get("name"), "file": model.get("file"), "version": model.get("version"), "aliases": aliases_for(model)},
        "lora": ({"name": lora.get("name"), "file": lora.get("file"), "weight": float(args.get("lora_weight", defaults.get("lora_weight", 1.0))), "aliases": aliases_for(lora)} if lora else None),
        "width": width,
        "height": height,
        "steps": steps,
        "defaults": defaults,
        "final_step": final_step,
        "sampler": args.get("sampler") or defaults.get("sampler") or "Euler A Trailing",
        "unsupported_settings": unsupported_settings,
        "seed": seed,
        "bytes": out_path.stat().st_size,
    }
