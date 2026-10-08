"""Skeleton, repository hygiene and tool configuration (plan features 1.1.1 to 1.1.7)."""

import importlib
import pkgutil
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

import vga

ROOT = Path(__file__).resolve().parents[2]
ENV_VARIABLES = [
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "VGA_USER_AGENT",
    "VGA_IMAGE_RANKER",
    "VGA_LOG_DIR",
    "VGA_LOG_LEVEL",
    "VGA_LOG_PROMPTS",
    "VGA_DEBUG_DUMP",
    "VGA_SETTINGS_PATH",
    "VGA_DAILY_LLM_CALL_CAP",
    "VGA_UI_FIXTURE",
]


@pytest.fixture(scope="module")
def text() -> str:
    return (ROOT / ".env.example").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def readme() -> str:
    return (ROOT / "README.md").read_text(encoding="utf-8")


def pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


class TestPackageLayout:
    def test_every_vga_package_imports(self) -> None:
        names = [m.name for m in pkgutil.walk_packages(vga.__path__, prefix="vga.")]

        assert {
            "vga.models",
            "vga.interfaces",
            "vga.errors",
            "vga.settings",
            "vga.log",
            "vga.understand",
            "vga.fetch",
            "vga.stores",
            "vga.rank",
            "vga.rank.image",
            "vga.tiers",
            "vga.pipeline",
        } <= set(names)
        for name in names:
            importlib.import_module(name)

    @pytest.mark.parametrize(
        "path",
        [
            "config/settings.yaml",
            "config/stores",
            "src/vga/understand/__init__.py",
            "src/vga/fetch/__init__.py",
            "src/vga/stores/__init__.py",
            "src/vga/rank/__init__.py",
            "src/vga/rank/image/__init__.py",
            "src/vga/tiers/__init__.py",
            "src/vga/pipeline/__init__.py",
            "app/__init__.py",
            "eval/harness/__init__.py",
            "tests/fakes.py",
            "tests/factories.py",
            "tests/fixtures/response_sample.json",
            ".github/workflows/ci.yml",
            ".pre-commit-config.yaml",
            "scripts/licence_audit.py",
            "docs/licences.md",
            "uv.lock",
        ],
    )
    def test_planned_paths_exist(self, path: str) -> None:
        assert (ROOT / path).exists()

    def test_adrs_one_to_five_exist(self) -> None:
        numbers = sorted(
            p.name[:4] for p in (ROOT / "docs" / "adr").glob("[0-9][0-9][0-9][0-9]-*.md")
        )

        assert numbers[:5] == ["0001", "0002", "0003", "0004", "0005"]


# A variable line in .env.example. It may be commented out (`# NAME=value`): that documents a
# variable without overriding the YAML default when the file is copied to `.env`.
_ANY_VARIABLE_LINE = r"^(?:# )?([A-Z][A-Z0-9_]*)=(.*)$"
_ACTIVE_VARIABLE_LINE = r"^([A-Z][A-Z0-9_]*)=(.*)$"


class TestEnvExample:
    def test_lists_exactly_the_documented_variables(self, text: str) -> None:
        names = re.findall(_ANY_VARIABLE_LINE, text, flags=re.MULTILINE)

        assert [name for name, _ in names] == ENV_VARIABLES

    def test_every_variable_has_a_comment_line_directly_above(self, text: str) -> None:
        lines = text.splitlines()
        for index, line in enumerate(lines):
            if re.match(_ANY_VARIABLE_LINE, line):
                assert lines[index - 1].startswith("#"), f"no comment above {line!r}"

    def test_the_image_ranker_is_commented_out_so_the_yaml_default_stays_in_force(
        self, text: str
    ) -> None:
        active = dict(re.findall(_ACTIVE_VARIABLE_LINE, text, flags=re.MULTILINE))

        assert "VGA_IMAGE_RANKER" not in active
        assert re.search(r"^# VGA_IMAGE_RANKER=off$", text, flags=re.MULTILINE)

    def test_copying_it_to_dot_env_keeps_siglip_as_the_image_ranker(self, text: str) -> None:
        from vga.settings import DEFAULT_SETTINGS_PATH, load_settings

        active = dict(re.findall(_ACTIVE_VARIABLE_LINE, text, flags=re.MULTILINE))
        active.pop("VGA_SETTINGS_PATH")

        assert load_settings(DEFAULT_SETTINGS_PATH, env=active).image_ranker == "siglip"

    def test_holds_placeholders_only(self, text: str) -> None:
        values = dict(re.findall(_ACTIVE_VARIABLE_LINE, text, flags=re.MULTILINE))

        assert values["OPENAI_API_KEY"] == "sk-your-key-here"
        assert not re.search(r"sk-[A-Za-z0-9_-]{20,}", text)
        assert values["VGA_USER_AGENT"] == "vga-shopping-agent-demo/0.1 (store search demo)"

    def test_values_are_accepted_by_the_settings_loader(self, tmp_path: Path) -> None:
        from vga.settings import DEFAULT_SETTINGS_PATH, load_settings

        # Commented-out values count too: they are what a user gets after uncommenting them.
        env = dict(re.findall(_ANY_VARIABLE_LINE, (ROOT / ".env.example").read_text(), re.M))
        env.pop("VGA_SETTINGS_PATH")

        load_settings(DEFAULT_SETTINGS_PATH, env=env)


class TestGitignore:
    @pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
    @pytest.mark.parametrize(
        ("path", "ignored"),
        [
            (".env", True),
            (".env.local", True),
            (".env.example", False),
            (".DS_Store", True),
            ("docs/.DS_Store", True),
            (".venv/bin/python", True),
            ("src/vga/__pycache__/models.cpython-312.pyc", True),
            (".pytest_cache/README.md", True),
            (".ruff_cache/x", True),
            (".mypy_cache/x", True),
            ("logs/vga.jsonl", True),
            ("models/weights.safetensors", True),
            ("eval/data/assets/private/selfie.jpg", True),
            ("eval/data/assets/private/.gitignore", False),
            ("eval/data/assets/product-1.jpg", False),
            ("eval/results/run-1/results.json", True),
            ("eval/results/run-1/labels.csv", True),
            ("eval/results/run-1/SUMMARY.md", False),
            ("eval/results/SUMMARY.md", False),
            ("uv.lock", False),
        ],
    )
    def test_patterns(self, path: str, ignored: bool) -> None:
        result = subprocess.run(  # noqa: S603
            ["git", "check-ignore", "-q", path],  # noqa: S607
            cwd=ROOT,
            capture_output=True,
            check=False,
        )

        assert (result.returncode == 0) is ignored


class TestToolConfiguration:
    def test_python_is_pinned_to_3_12(self) -> None:
        assert (ROOT / ".python-version").read_text().strip() == "3.12"
        assert pyproject()["project"]["requires-python"] == ">=3.12,<3.13"

    def test_runtime_dependencies(self) -> None:
        names = {
            re.split(r"[<>=!~ ]", d, maxsplit=1)[0].lower()
            for d in pyproject()["project"]["dependencies"]
        }

        assert names == {
            "openai",
            "pydantic",
            "pyyaml",
            "httpx",
            "selectolax",
            "extruct",
            "streamlit",
            "pillow",
            "protego",
        }

    def test_ml_group_is_optional_and_dev_group_is_the_default(self) -> None:
        config = pyproject()
        groups = config["dependency-groups"]

        assert {re.split(r"[<>=!~ ]", d)[0] for d in groups["ml"]} == {"torch", "open-clip-torch"}
        assert config["tool"]["uv"]["default-groups"] == ["dev"]
        assert "ml" not in config["tool"]["uv"]["default-groups"]

    def test_dev_group_has_the_quality_tools(self) -> None:
        dev = {re.split(r"[<>=!~ ]", d)[0].lower() for d in pyproject()["dependency-groups"]["dev"]}

        assert {
            "pytest",
            "pytest-asyncio",
            "respx",
            "ruff",
            "mypy",
            "pip-audit",
            "pip-licenses",
            "pre-commit",
        } <= dev

    def test_pytest_is_configured_for_async_markers_and_skipping_live(self) -> None:
        options = pyproject()["tool"]["pytest"]["ini_options"]

        assert options["asyncio_mode"] == "auto"
        assert {m.split(":")[0] for m in options["markers"]} == {"live", "slow"}
        assert "not live" in options["addopts"]
        assert "src" in options["pythonpath"]
        assert "." in options["pythonpath"]

    def test_ruff_security_rules_are_on(self) -> None:
        assert "S" in pyproject()["tool"]["ruff"]["lint"]["select"]

    def test_mypy_checks_src_strictly(self) -> None:
        mypy = pyproject()["tool"]["mypy"]

        assert mypy["files"] == ["src"]
        assert mypy["strict"] is True


class TestWorkflows:
    def test_runs_on_pull_requests_and_pushes(self, workflow: dict) -> None:
        triggers = workflow.get("on", workflow.get(True))

        assert "pull_request" in triggers
        assert "push" in triggers

    def test_has_test_audit_and_secret_scan_jobs(self, workflow: dict) -> None:
        assert {"test", "pip-audit", "gitleaks"} <= set(workflow["jobs"])

    def test_test_job_runs_every_gate_without_live_tests(self, workflow: dict) -> None:
        commands = "\n".join(step.get("run", "") for step in workflow["jobs"]["test"]["steps"])

        for expected in ("uv sync --locked", "ruff check", "mypy src", "pytest"):
            assert expected in commands
        assert "-m live" not in commands

    def test_permissions_are_read_only(self, workflow: dict) -> None:
        assert workflow["permissions"] == {"contents": "read"}

    def test_audit_and_scan_jobs_do_the_right_thing(self, workflow: dict) -> None:
        audit = "\n".join(step.get("run", "") for step in workflow["jobs"]["pip-audit"]["steps"])
        scan = workflow["jobs"]["gitleaks"]["steps"]

        assert "pip-audit" in audit
        assert any("gitleaks" in str(step) for step in scan)

    def test_pre_commit_runs_ruff_and_gitleaks(self) -> None:
        config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
        hooks = {hook["id"] for repo in config["repos"] for hook in repo["hooks"]}

        assert {"gitleaks"} <= hooks
        assert any(h.startswith("ruff") for h in hooks)


class TestReadme:
    def test_documents_every_environment_variable(self, readme: str) -> None:
        for name in ENV_VARIABLES:
            assert name in readme, f"README does not mention {name}"

    def test_shows_the_cold_start_commands(self, readme: str) -> None:
        for command in ("uv sync", "uv run pytest", "uv run ruff check", "uv run mypy src"):
            assert command in readme

    def test_states_the_known_limits_of_the_ai_features(self, readme: str) -> None:
        assert "limitations" in readme.lower()

    def test_does_not_suggest_urllib_robotparser(self, readme: str) -> None:
        assert "robotparser" not in readme
