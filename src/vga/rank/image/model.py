"""Loading the pinned FashionSigLIP image tower (plan 8.1.1) and fetching its weights (8.1.4).

``torch``, ``open_clip`` and ``huggingface_hub`` belong to the optional ``ml`` dependency group,
which CI and most developers do not install. They are imported only inside functions, through
``importlib``, so importing this module never needs them and a missing one becomes an
``ImageModelUnavailableError`` that the ranker turns into "no image scores".

How the model is pinned: ``open_clip``'s ``hf-hub:`` scheme cannot take a revision, so the exact
commit is fetched with ``huggingface_hub.snapshot_download(revision=...)`` and ``open_clip`` then
loads from that local folder (``local-dir:``). At run time the snapshot is only ever looked up in
the local cache; nothing is downloaded inside a request. The ``download`` module does the
download ahead of time.

Only the image tower is used, so the ranker works with ``transformers`` (the text tokenizer's
dependency) not importable.
"""

import re
import threading
import time
from collections.abc import Sequence
from importlib import import_module
from pathlib import Path
from typing import Any

from PIL import Image

from vga.errors import VgaError
from vga.log import get_logger

log = get_logger(__name__)

MODEL_REPO = "Marqo/marqo-fashionSigLIP"
"""The Hugging Face repository (model card licence apache-2.0)."""

ALLOW_PATTERNS = (
    "open_clip_config.json",
    "open_clip_model.safetensors",
    "config.json",
    "preprocessor_config.json",
    "special_tokens_map.json",
    "spiece.model",
    "tokenizer.json",
    "tokenizer_config.json",
)
"""The files of the repository that are downloaded (about 816 MB). The repository is 4.9 GB
because it also ships ONNX variants and a duplicate ``.bin``; ``open_clip`` needs only these."""

REQUIRED_FILES = ("open_clip_config.json", "open_clip_model.safetensors")
"""The files the image tower cannot load without."""

DOWNLOAD_COMMAND = "uv run --group ml python -m vga.rank.image.download"
INSTALL_COMMAND = "uv sync --group ml"

_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_WARM_UP_SIZE = (224, 224)


class ImageModelUnavailableError(VgaError):
    """The image model cannot be used: unpinned, the ``ml`` packages or the weights are missing, or
    loading failed. The ranker answers with "no image scores"; the shopper never sees this."""

    default_code = "image_model_unavailable"
    default_message = (
        "Matching by photo is not available right now, so results are ranked without it."
    )


def _import_optional(name: str) -> Any:
    """Import a module of the optional ``ml`` group, or raise ``ImageModelUnavailableError``."""
    try:
        return import_module(name)
    except (ImportError, OSError) as exc:  # OSError: a broken native library inside torch
        raise ImageModelUnavailableError(
            detail=f"cannot import {name!r} ({exc}); install the optional ML packages with "
            f"`{INSTALL_COMMAND}`"
        ) from exc


def _require_pinned(revision: str | None) -> str:
    """The revision, if it is a full commit hash; an unpinned load is refused."""
    if not revision or not _COMMIT_RE.match(revision):
        raise ImageModelUnavailableError(
            detail=(
                "siglip_revision must be a 40-character Hugging Face commit hash; refusing to "
                f"load an unpinned model (got {revision!r})"
            )
        )
    return revision


def resolve_snapshot(revision: str | None, *, download: bool) -> Path:
    """The local folder holding the pinned snapshot.

    With ``download=False`` (what a request uses) only the local Hugging Face cache is consulted
    and no network call is made. With ``download=True`` (the setup command) missing files are
    fetched, and files already present are not fetched again, so it is safe to repeat.
    Raises ``ImageModelUnavailableError`` when the revision is unpinned, ``huggingface_hub`` is not
    installed, or the snapshot is missing or incomplete.
    """
    pinned = _require_pinned(revision)
    hub = _import_optional("huggingface_hub")
    try:
        folder = Path(
            hub.snapshot_download(
                MODEL_REPO,
                revision=pinned,
                allow_patterns=list(ALLOW_PATTERNS),
                local_files_only=not download,
            )
        )
    except Exception as exc:  # the Hub client raises many kinds of error
        what = "downloading the weights failed" if download else "weights not found locally"
        raise ImageModelUnavailableError(
            detail=f"{what} ({type(exc).__name__}: {exc}); run `{DOWNLOAD_COMMAND}`"
        ) from exc
    missing = [name for name in REQUIRED_FILES if not (folder / name).is_file()]
    if missing:
        raise ImageModelUnavailableError(
            detail=f"model snapshot {folder} is missing {missing}; run `{DOWNLOAD_COMMAND}`"
        )
    return folder


def pick_device(torch: Any) -> str:
    """The best device on this machine: ``cuda``, then ``mps`` (Apple silicon), then ``cpu``."""
    if torch.cuda.is_available():
        return "cuda"
    mps = getattr(torch.backends, "mps", None)
    if mps is not None and mps.is_available():
        return "mps"
    return "cpu"


class SiglipEmbedder:
    """The FashionSigLIP image tower on one device. Satisfies ``siglip.ImageEmbedder``.

    Thread-safe: calls are serialised, because one model on one device is not safe to run from
    several threads at once.
    """

    def __init__(
        self, *, model: Any, preprocess: Any, torch: Any, device: str, revision: str
    ) -> None:
        self._model = model
        self._preprocess = preprocess
        self._torch = torch
        self._lock = threading.Lock()
        self.device = device
        self.revision = revision

    def embed(self, images: Sequence[Image.Image]) -> list[list[float]]:
        """L2-normalised embeddings (768 numbers each) of RGB images, one per image."""
        if not images:
            return []
        with self._lock, self._torch.no_grad():
            batch = self._torch.stack([self._preprocess(image) for image in images])
            vectors = self._model.encode_image(batch.to(self.device), normalize=True)
            rows: list[list[float]] = vectors.float().cpu().tolist()
        return rows


def build_embedder(revision: str | None, *, device: str | None = None) -> SiglipEmbedder:
    """Load the pinned model from the local cache onto ``device`` (default: the best available).

    Does the work every call; use ``get_embedder`` to load once per process. The model is put in
    ``eval()`` mode, gradients are off, and one warm-up call runs so the first real request is not
    slower than the rest. Raises ``ImageModelUnavailableError`` on any failure.
    """
    started = time.perf_counter()
    pinned = _require_pinned(revision)
    folder = resolve_snapshot(pinned, download=False)
    torch = _import_optional("torch")
    open_clip = _import_optional("open_clip")
    chosen = device or pick_device(torch)
    try:
        model, _, preprocess = open_clip.create_model_and_transforms(f"local-dir:{folder}")
        model = model.to(chosen).eval()
        embedder = SiglipEmbedder(
            model=model, preprocess=preprocess, torch=torch, device=chosen, revision=pinned
        )
        embedder.embed([Image.new("RGB", _WARM_UP_SIZE, (255, 255, 255))])
    except ImageModelUnavailableError:
        raise
    except Exception as exc:  # open_clip / torch raise many kinds of error on a bad checkpoint
        raise ImageModelUnavailableError(
            detail=f"loading the model failed ({type(exc).__name__}: {exc})"
        ) from exc
    log.info(
        "image model loaded",
        extra={
            "model": MODEL_REPO,
            "revision": pinned,
            "device": chosen,
            "load_seconds": round(time.perf_counter() - started, 3),
        },
    )
    return embedder


_lock = threading.Lock()
_loaded: tuple[str, SiglipEmbedder] | None = None


def get_embedder(revision: str | None) -> SiglipEmbedder:
    """The process-wide model, loaded on first use and then reused (a lazy singleton).

    Building the model takes about 3 s and 2 GB, so it happens once. A second call with the same
    revision returns the same object. Raises ``ImageModelUnavailableError`` when the revision is
    unpinned or the model cannot be loaded; a failed load is not remembered, so downloading the
    weights while the app runs is enough for the next request to succeed.
    """
    global _loaded
    pinned = _require_pinned(revision)
    with _lock:
        if _loaded is not None and _loaded[0] == pinned:
            return _loaded[1]
        embedder = build_embedder(pinned)
        _loaded = (pinned, embedder)
        return embedder


def clear_embedder_cache() -> None:
    """Forget the loaded model, so the next ``get_embedder`` loads it again (used by tests)."""
    global _loaded
    with _lock:
        _loaded = None
