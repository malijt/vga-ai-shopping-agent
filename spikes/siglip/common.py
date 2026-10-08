"""Shared helpers for the SigLIP spike (Phase 3).

Everything here is local-only: no image or text ever leaves the machine except the
one-off model download from huggingface.co and the licence-clean sample images fetched
by ``03_fetch_images.py``.

Importing this module sets ``HF_HOME`` to a spike-local cache (``.cache/hf``, git-ignored)
*before* ``huggingface_hub`` is imported, so the download size is measurable from a clean
start and nothing leaks into the user's global cache. Set ``HF_HOME`` yourself to override.
"""

from __future__ import annotations

import json
import os
import platform
import statistics
import sys
import time
from importlib import metadata
from pathlib import Path

SPIKE_DIR = Path(__file__).resolve().parent
os.environ.setdefault("HF_HOME", str(SPIKE_DIR / ".cache" / "hf"))

REPO_ID = "Marqo/marqo-fashionSigLIP"
# Exact Hugging Face commit the spike was measured against (resolved from the Hub on
# 2026-10-07 by hub_info.py; re-check with `uv run python hub_info.py`). open_clip's
# "hf-hub:" scheme cannot take a revision, so we snapshot_download(revision=...) and load
# from the resulting local directory ("local-dir:") to make the pin real.
REVISION = "c56244cc94f92419e8369fa71efdaf403b124ce8"

# The repo is 4.9 GB because it also ships ONNX variants and a duplicate .bin. open_clip only
# needs the config, the safetensors weights and the tokenizer files (about 0.8 GB).
ALLOW_PATTERNS = [
    "open_clip_config.json",
    "open_clip_model.safetensors",
    "config.json",
    "preprocessor_config.json",
    "special_tokens_map.json",
    "spiece.model",
    "tokenizer.json",
    "tokenizer_config.json",
]

IMAGES_DIR = SPIKE_DIR / "images"
RESULTS_DIR = SPIKE_DIR / "results"
USER_AGENT = "vga-shopping-agent-demo/0.1 (image-similarity spike)"


def go_offline() -> None:
    """Make any network access fail: HF offline flags plus a dead proxy as a belt-and-braces check.

    Must be called before huggingface_hub / open_clip are imported.
    """
    for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        os.environ[key] = "1"
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        os.environ[key] = "http://127.0.0.1:9"  # discard port: connections are refused


def available_devices() -> list[str]:
    """Every torch device worth benchmarking on this machine, cpu always last."""
    import torch

    devices: list[str] = []
    if torch.cuda.is_available():
        devices.append("cuda")
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        devices.append("mps")
    devices.append("cpu")
    return devices


def sync(device: str) -> None:
    """Block until queued work on ``device`` has finished (needed for honest timings)."""
    import torch

    if device == "mps":
        torch.mps.synchronize()
    elif device == "cuda":
        torch.cuda.synchronize()


def versions() -> dict[str, str]:
    out = {"python": platform.python_version(), "platform": platform.platform(), "machine": platform.machine()}
    for pkg in ("torch", "open_clip_torch", "pillow", "huggingface_hub", "numpy", "torchvision", "timm", "httpx"):
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            out[pkg] = "not installed"
    return out


def load_model(device: str, revision: str = REVISION, with_text: bool = False):
    """Load the pinned FashionSigLIP and return ``(model, preprocess, tokenizer, info)``.

    ``info`` carries timings for the report: snapshot (download or cache hit) seconds and
    model construction seconds. The model is moved to ``device`` and set to eval mode.
    """
    import open_clip
    import torch
    from huggingface_hub import snapshot_download

    t0 = time.perf_counter()
    local_dir = snapshot_download(REPO_ID, revision=revision, allow_patterns=ALLOW_PATTERNS)
    t_snapshot = time.perf_counter() - t0

    t1 = time.perf_counter()
    model, _, preprocess = open_clip.create_model_and_transforms(f"local-dir:{local_dir}")
    model = model.to(device).eval()
    sync(device)
    t_build = time.perf_counter() - t1
    # The tokenizer needs the heavy `transformers` package and is only used for text
    # embeddings. The image ranker (image vs image) never needs it, so it is built outside
    # the timed model construction.
    tokenizer = open_clip.get_tokenizer(f"local-dir:{local_dir}") if with_text else None
    torch.set_grad_enabled(False)
    return model, preprocess, tokenizer, {
        "local_dir": local_dir,
        "snapshot_seconds": t_snapshot,
        "build_and_to_device_seconds": t_build,
    }


def to_rgb(image):
    """RGB copy of ``image``; transparent pixels become white (product cut-outs are often PNGs)."""
    from PIL import Image

    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    return image.convert("RGB")


def make_thumbnail_bytes(path: Path, long_edge: int = 400, quality: int = 85) -> bytes:
    """What a store CDN would hand us: a JPEG whose long edge is about ``long_edge`` px, in memory."""
    import io

    from PIL import Image

    with Image.open(path) as source:
        image = to_rgb(source)
    image.thumbnail((long_edge, long_edge), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality)
    return buffer.getvalue()


def load_image_set() -> list[dict]:
    """The images listed in results/image_sources.json, in manifest order, as dicts with ``path``."""
    sources_path = RESULTS_DIR / "image_sources.json"
    if not sources_path.exists():
        die("results/image_sources.json missing: run `uv run python 00_fetch_images.py` first")
    entries = json.loads(sources_path.read_text())["images"]
    for entry in entries:
        entry["path"] = SPIKE_DIR / entry["file"]
        if not entry["path"].exists():
            die(f"{entry['path']} missing: run `uv run python 00_fetch_images.py` first")
    return entries


def load_average() -> list[float]:
    return [round(x, 2) for x in os.getloadavg()]


def median(values: list[float]) -> float:
    return statistics.median(values)


def write_json(name: str, payload: dict) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / name
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def die(msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(1)
