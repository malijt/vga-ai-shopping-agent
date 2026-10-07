"""Fake ``huggingface_hub``, ``torch`` and ``open_clip``: the weights boundary, without the weights.

The loader reaches the optional ``ml`` packages only through ``model._import_optional``. Installing
``FakeMlPackages`` swaps that one function, so the loader's real logic (pinning, local-only lookup,
device choice, ``eval()``, ``no_grad``, warm-up, the singleton) runs in the default test suite,
which has no ``torch`` and no network.
"""

from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace, TracebackType
from typing import Any

import pytest

from vga.rank.image import model
from vga.rank.image.model import REQUIRED_FILES, ImageModelUnavailableError

REVISION = "c56244cc94f92419e8369fa71efdaf403b124ce8"
OTHER_REVISION = "0123456789abcdef0123456789abcdef01234567"
EMBEDDING_SIZE = 4


class FakeHub:
    """``huggingface_hub`` with a cache that starts empty or full, and a record of every call."""

    def __init__(self, folder: Path, *, cached: bool) -> None:
        self.folder = folder
        self.cached = cached
        self.fail_download: Exception | None = None
        self.calls: list[dict[str, Any]] = []

    @property
    def downloads(self) -> list[dict[str, Any]]:
        """Calls that were allowed to use the network."""
        return [call for call in self.calls if not call["local_files_only"]]

    def snapshot_download(
        self,
        repo_id: str,
        *,
        revision: str | None = None,
        allow_patterns: Sequence[str] | None = None,
        local_files_only: bool = False,
    ) -> str:
        self.calls.append(
            {
                "repo_id": repo_id,
                "revision": revision,
                "allow_patterns": list(allow_patterns or []),
                "local_files_only": local_files_only,
            }
        )
        if not self.cached:
            if local_files_only:
                raise FileNotFoundError("not in the local cache")
            if self.fail_download is not None:
                raise self.fail_download
            self.write_snapshot()
            self.cached = True
        return str(self.folder)

    def write_snapshot(self, files: Sequence[str] = REQUIRED_FILES) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        for name in files:
            (self.folder / name).write_text("stub")


class FakeTensor:
    def __init__(self, rows: list[Any], torch: "FakeTorch", device: str = "cpu") -> None:
        self.rows = rows
        self.torch = torch
        self.device = device

    def to(self, device: str) -> "FakeTensor":
        self.device = device
        return self

    def float(self) -> "FakeTensor":
        return self

    def cpu(self) -> "FakeTensor":
        return self

    def tolist(self) -> list[Any]:
        return self.rows


class _NoGrad:
    def __init__(self, torch: "FakeTorch") -> None:
        self._torch = torch

    def __enter__(self) -> None:
        self._torch.grad_depth += 1

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._torch.grad_depth -= 1


class FakeTorch:
    def __init__(self, *, cuda: bool = False, mps: bool = False) -> None:
        self.cuda = SimpleNamespace(is_available=lambda: cuda)
        self.backends = SimpleNamespace(mps=SimpleNamespace(is_available=lambda: mps))
        self.grad_depth = 0

    def no_grad(self) -> _NoGrad:
        return _NoGrad(self)

    def stack(self, tensors: Sequence[FakeTensor]) -> FakeTensor:
        return FakeTensor(list(tensors), self)


class FakeClipModel:
    """The image tower: ``encode_image`` returns one vector per image, and notes the conditions."""

    def __init__(self, torch: FakeTorch) -> None:
        self.torch = torch
        self.training = True
        self.device: str | None = None
        self.encode_calls: list[dict[str, Any]] = []

    def to(self, device: str) -> "FakeClipModel":
        self.device = device
        return self

    def eval(self) -> "FakeClipModel":
        self.training = False
        return self

    def encode_image(self, batch: FakeTensor, *, normalize: bool = False) -> FakeTensor:
        self.encode_calls.append(
            {
                "batch": len(batch.rows),
                "normalize": normalize,
                "gradients_off": self.torch.grad_depth > 0,
                "device": batch.device,
                "eval": not self.training,
            }
        )
        return FakeTensor([[0.5] * EMBEDDING_SIZE for _ in batch.rows], self.torch)


class FakeOpenClip:
    def __init__(self, torch: FakeTorch) -> None:
        self.torch = torch
        self.model_names: list[str] = []
        self.models: list[FakeClipModel] = []
        self.error: Exception | None = None

    def create_model_and_transforms(self, name: str) -> tuple[FakeClipModel, None, Any]:
        self.model_names.append(name)
        if self.error is not None:
            raise self.error
        built = FakeClipModel(self.torch)
        self.models.append(built)
        return built, None, lambda image: FakeTensor([image.size], self.torch)


class FakeMlPackages:
    """The three optional packages, installed in place of the real ones for one test."""

    def __init__(
        self,
        tmp_path: Path,
        *,
        cached: bool = True,
        cuda: bool = False,
        mps: bool = False,
        missing: Sequence[str] = (),
    ) -> None:
        self.hub = FakeHub(tmp_path / "snapshot", cached=cached)
        if cached:
            self.hub.write_snapshot()
        self.torch = FakeTorch(cuda=cuda, mps=mps)
        self.open_clip = FakeOpenClip(self.torch)
        self.missing = set(missing)

    def import_optional(self, name: str) -> Any:
        if name in self.missing:
            raise ImageModelUnavailableError(
                detail=f"cannot import {name!r}; install the optional ML packages with "
                f"`{model.INSTALL_COMMAND}`"
            )
        return {"huggingface_hub": self.hub, "torch": self.torch, "open_clip": self.open_clip}[name]

    def install(self, monkeypatch: pytest.MonkeyPatch) -> "FakeMlPackages":
        monkeypatch.setattr(model, "_import_optional", self.import_optional)
        return self
