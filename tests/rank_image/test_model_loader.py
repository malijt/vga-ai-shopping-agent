"""8.1.1 Model loader: pinned, local-only, lazy singleton, image tower only (fake weights)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from PIL import Image

from tests.rank_image.ml_fakes import (
    EMBEDDING_SIZE,
    OTHER_REVISION,
    REVISION,
    FakeMlPackages,
)
from vga.rank.image import model
from vga.rank.image.model import (
    ALLOW_PATTERNS,
    DOWNLOAD_COMMAND,
    MODEL_REPO,
    REQUIRED_FILES,
    ImageModelUnavailableError,
    build_embedder,
    clear_embedder_cache,
    get_embedder,
    pick_device,
    resolve_snapshot,
)


@pytest.fixture(autouse=True)
def fresh_singleton() -> Iterator[None]:
    clear_embedder_cache()
    yield
    clear_embedder_cache()


@pytest.fixture
def ml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeMlPackages:
    return FakeMlPackages(tmp_path).install(monkeypatch)


class TestPinning:
    @pytest.mark.parametrize("revision", [None, "", "main", "c56244c", "G" * 40, REVISION[:-1]])
    def test_an_unpinned_load_is_refused(self, ml: FakeMlPackages, revision: str | None) -> None:
        with pytest.raises(ImageModelUnavailableError) as caught:
            get_embedder(revision)

        assert caught.value.code == "image_model_unavailable"
        assert "refusing to load an unpinned model" in (caught.value.detail or "")
        assert ml.hub.calls == []  # refused before the Hub or the cache was consulted

    def test_the_snapshot_is_requested_at_the_pinned_revision(self, ml: FakeMlPackages) -> None:
        resolve_snapshot(REVISION, download=False)

        (call,) = ml.hub.calls
        assert call["repo_id"] == MODEL_REPO == "Marqo/marqo-fashionSigLIP"
        assert call["revision"] == REVISION

    def test_only_the_files_open_clip_needs_are_requested(self, ml: FakeMlPackages) -> None:
        resolve_snapshot(REVISION, download=False)

        (call,) = ml.hub.calls
        assert call["allow_patterns"] == list(ALLOW_PATTERNS)
        assert set(REQUIRED_FILES) <= set(ALLOW_PATTERNS)
        assert "open_clip_model.safetensors" in ALLOW_PATTERNS
        assert not any(pattern.endswith((".onnx", ".bin")) for pattern in ALLOW_PATTERNS)

    def test_the_model_is_built_from_the_pinned_local_folder(self, ml: FakeMlPackages) -> None:
        build_embedder(REVISION)

        assert ml.open_clip.model_names == [f"local-dir:{ml.hub.folder}"]
        assert not any(name.startswith("hf-hub:") for name in ml.open_clip.model_names)


class TestNoDownloadInsideARequest:
    def test_loading_only_looks_in_the_local_cache(self, ml: FakeMlPackages) -> None:
        get_embedder(REVISION)

        assert ml.hub.calls
        assert ml.hub.downloads == []

    def test_missing_weights_are_an_error_not_a_download(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        packages = FakeMlPackages(tmp_path, cached=False).install(monkeypatch)

        with pytest.raises(ImageModelUnavailableError) as caught:
            get_embedder(REVISION)

        assert DOWNLOAD_COMMAND in (caught.value.detail or "")
        assert packages.hub.downloads == []
        assert packages.open_clip.model_names == []

    def test_an_incomplete_snapshot_is_an_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        packages = FakeMlPackages(tmp_path, cached=False).install(monkeypatch)
        packages.hub.write_snapshot(files=["open_clip_config.json"])
        packages.hub.cached = True  # the folder exists but the weights file is missing

        with pytest.raises(ImageModelUnavailableError) as caught:
            get_embedder(REVISION)

        assert "open_clip_model.safetensors" in (caught.value.detail or "")

    def test_the_setup_step_may_download(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        packages = FakeMlPackages(tmp_path, cached=False).install(monkeypatch)

        folder = resolve_snapshot(REVISION, download=True)

        assert folder == packages.hub.folder
        assert [call["local_files_only"] for call in packages.hub.calls] == [False]
        assert all((folder / name).is_file() for name in REQUIRED_FILES)

    def test_a_failed_load_is_not_remembered(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        FakeMlPackages(tmp_path, cached=False).install(monkeypatch)
        with pytest.raises(ImageModelUnavailableError):
            get_embedder(REVISION)

        resolve_snapshot(REVISION, download=True)  # the weights arrive while the app runs
        embedder = get_embedder(REVISION)

        assert embedder.revision == REVISION


class TestMissingPackages:
    @pytest.mark.parametrize("package", ["huggingface_hub", "torch", "open_clip"])
    def test_a_missing_ml_package_is_unavailable_with_the_install_hint(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, package: str
    ) -> None:
        FakeMlPackages(tmp_path, missing=[package]).install(monkeypatch)

        with pytest.raises(ImageModelUnavailableError) as caught:
            get_embedder(REVISION)

        assert package in (caught.value.detail or "")
        assert "uv sync --group ml" in (caught.value.detail or "")

    def test_importing_a_package_that_is_really_absent_is_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def absent(name: str) -> object:
            raise ModuleNotFoundError(f"No module named {name!r}")

        monkeypatch.setattr(model, "import_module", absent)

        with pytest.raises(ImageModelUnavailableError):
            model._import_optional("torch")

    def test_a_broken_native_library_is_unavailable_too(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken(name: str) -> object:
            raise OSError("dlopen failed")

        monkeypatch.setattr(model, "import_module", broken)

        with pytest.raises(ImageModelUnavailableError):
            model._import_optional("torch")


class TestDevice:
    @pytest.mark.parametrize(
        ("cuda", "mps", "expected"),
        [(True, True, "cuda"), (True, False, "cuda"), (False, True, "mps"), (False, False, "cpu")],
    )
    def test_the_order_is_cuda_then_mps_then_cpu(
        self, tmp_path: Path, cuda: bool, mps: bool, expected: str
    ) -> None:
        packages = FakeMlPackages(tmp_path, cuda=cuda, mps=mps)

        assert pick_device(packages.torch) == expected

    def test_a_torch_without_mps_support_falls_back_to_cpu(self, tmp_path: Path) -> None:
        packages = FakeMlPackages(tmp_path)
        packages.torch.backends = object()  # type: ignore[assignment]

        assert pick_device(packages.torch) == "cpu"

    def test_the_model_runs_on_the_chosen_device(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        packages = FakeMlPackages(tmp_path, mps=True).install(monkeypatch)

        embedder = build_embedder(REVISION)

        assert embedder.device == "mps"
        assert packages.open_clip.models[0].device == "mps"

    def test_a_device_can_be_forced(self, ml: FakeMlPackages) -> None:
        assert build_embedder(REVISION, device="cpu").device == "cpu"


class TestModelSetup:
    def test_the_model_is_in_eval_mode_with_gradients_off_and_warmed_up(
        self, ml: FakeMlPackages
    ) -> None:
        build_embedder(REVISION)

        (clip,) = ml.open_clip.models
        assert clip.training is False
        assert len(clip.encode_calls) == 1  # the warm-up call
        assert clip.encode_calls[0]["gradients_off"] is True
        assert ml.torch.grad_depth == 0  # and it did not leave gradients off for the process

    def test_embedding_runs_without_gradients_on_normalised_output(
        self, ml: FakeMlPackages
    ) -> None:
        embedder = build_embedder(REVISION)

        rows = embedder.embed([Image.new("RGB", (5, 5)), Image.new("RGB", (6, 6))])

        (clip,) = ml.open_clip.models
        assert clip.encode_calls[-1] == {
            "batch": 2,
            "normalize": True,
            "gradients_off": True,
            "device": "cpu",
            "eval": True,
        }
        assert rows == [[0.5] * EMBEDDING_SIZE] * 2

    def test_embedding_nothing_does_not_call_the_model(self, ml: FakeMlPackages) -> None:
        embedder = build_embedder(REVISION)
        (clip,) = ml.open_clip.models
        calls_after_load = len(clip.encode_calls)

        assert embedder.embed([]) == []
        assert len(clip.encode_calls) == calls_after_load

    def test_a_checkpoint_that_will_not_load_is_unavailable(self, ml: FakeMlPackages) -> None:
        ml.open_clip.error = RuntimeError("corrupt checkpoint")

        with pytest.raises(ImageModelUnavailableError) as caught:
            build_embedder(REVISION)

        assert "corrupt checkpoint" in (caught.value.detail or "")

    def test_the_load_is_logged_with_revision_and_device(
        self, ml: FakeMlPackages, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level("INFO", logger="vga"):
            build_embedder(REVISION)

        (record,) = [r for r in caplog.records if r.getMessage() == "image model loaded"]
        assert record.revision == REVISION  # type: ignore[attr-defined]
        assert record.device == "cpu"  # type: ignore[attr-defined]


class TestLazySingleton:
    def test_the_second_call_does_not_reload(self, ml: FakeMlPackages) -> None:
        first = get_embedder(REVISION)
        second = get_embedder(REVISION)

        assert first is second
        assert ml.open_clip.model_names == [f"local-dir:{ml.hub.folder}"]  # built once

    def test_nothing_is_loaded_until_it_is_asked_for(self, ml: FakeMlPackages) -> None:
        assert ml.hub.calls == []
        assert ml.open_clip.model_names == []

    def test_another_revision_loads_another_model(self, ml: FakeMlPackages) -> None:
        first = get_embedder(REVISION)
        second = get_embedder(OTHER_REVISION)

        assert first is not second
        assert (first.revision, second.revision) == (REVISION, OTHER_REVISION)
        assert len(ml.open_clip.models) == 2

    def test_clearing_the_cache_loads_again(self, ml: FakeMlPackages) -> None:
        first = get_embedder(REVISION)
        clear_embedder_cache()

        assert get_embedder(REVISION) is not first
