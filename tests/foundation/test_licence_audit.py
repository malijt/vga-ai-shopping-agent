"""The licence audit script (plan feature 1.4.1)."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def audit() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "licence_audit", ROOT / "scripts" / "licence_audit.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["licence_audit"] = module
    spec.loader.exec_module(module)
    return module


class TestClassify:
    @pytest.mark.parametrize(
        "licence",
        [
            "MIT",
            "MIT License",
            "BSD License",
            "BSD-3-Clause",
            "Apache-2.0",
            "Apache Software License",
            "ISC License (ISCL)",
            "Python Software Foundation License",
            "Historical Permission Notice and Disclaimer (HPND)",
            "MIT-CMU",
            "The Unlicense (Unlicense)",
            "BSD License (BSD-3-Clause)",
            "Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND MIT",
            "MIT; Apache Software License",
        ],
    )
    def test_permissive_licences_are_ok(self, audit: ModuleType, licence: str) -> None:
        assert audit.classify(licence) == "ok"

    @pytest.mark.parametrize(
        "licence",
        [
            "GPL-3.0-only",
            "GNU General Public License v3 (GPLv3)",
            "AGPL-3.0-or-later",
            "GNU Affero General Public License v3",
            "SSPL-1.0",
            "EUPL-1.2",
        ],
    )
    def test_strong_copyleft_is_flagged_as_copyleft(self, audit: ModuleType, licence: str) -> None:
        assert audit.classify(licence) == "copyleft"

    @pytest.mark.parametrize(
        "licence",
        [
            "LGPL-2.1-or-later",
            "GNU Lesser General Public License v3 (LGPLv3)",
            "Mozilla Public License 2.0 (MPL 2.0)",
            "MPL-2.0",
            "EPL-2.0",
            "CDDL-1.0",
            "LicenseRef-NVIDIA-Proprietary",
            "Other/Proprietary License",
        ],
    )
    def test_weak_copyleft_and_proprietary_need_review(
        self, audit: ModuleType, licence: str
    ) -> None:
        assert audit.classify(licence) == "review"

    @pytest.mark.parametrize("licence", ["UNKNOWN", "", None, "unlicensed", "Other"])
    def test_unknown_licences_are_flagged(self, audit: ModuleType, licence: str | None) -> None:
        assert audit.classify(licence) == "unknown"

    def test_a_choice_of_licences_counts_as_the_better_one(self, audit: ModuleType) -> None:
        assert audit.classify("MIT OR GPL-2.0-only") == "ok"
        assert audit.classify("Apache-2.0 OR (GPL-3.0 OR LGPL-3.0)") == "ok"

    def test_licences_that_all_apply_count_as_the_worst_one(self, audit: ModuleType) -> None:
        assert audit.classify("MIT AND GPL-3.0-only") == "copyleft"
        assert audit.classify("MPL-2.0 AND MIT") == "review"
        assert audit.classify("MIT; GNU General Public License (GPL)") == "copyleft"

    def test_nested_expressions(self, audit: ModuleType) -> None:
        assert audit.classify("MIT AND (BSD-3-Clause OR GPL-3.0-only)") == "ok"
        assert audit.classify("MIT AND (GPL-3.0-only OR AGPL-3.0-only)") == "copyleft"


@pytest.fixture(scope="module")
def report(tmp_path_factory: pytest.TempPathFactory) -> str:
    output = tmp_path_factory.mktemp("licences") / "licences.md"
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(ROOT / "scripts" / "licence_audit.py"),
            "--offline",
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        cwd=ROOT,
    )
    return output.read_text(encoding="utf-8")


class TestReport:
    def test_lists_every_direct_dependency_with_its_group(self, report: str) -> None:
        for name in (
            "openai",
            "pydantic",
            "httpx",
            "selectolax",
            "extruct",
            "streamlit",
            "protego",
        ):
            assert f"| {name} |" in report.lower()

    def test_lists_transitive_dependencies_too(self, report: str) -> None:
        assert "| annotated-types |" in report
        assert "| no |" in report

    def test_has_a_flagged_section_and_a_summary(self, report: str) -> None:
        assert "## Flagged" in report
        assert "still needing review" in report

    def test_every_installed_distribution_appears(self, report: str) -> None:
        from importlib import metadata

        names = {d.metadata["Name"].lower().replace("_", "-") for d in metadata.distributions()}
        names.discard("vga")
        rows = report.lower().replace("_", "-")

        missing = [name for name in names if f"| {name} |" not in rows]
        assert not missing
