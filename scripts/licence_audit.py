"""Licence audit (BRD Rule 5: only commercial-friendly components).

Lists the licence of every installed package (direct and transitive) with ``pip-licenses``, adds
the packages that are locked in ``uv.lock`` but not installed here (for example the optional
``ml`` group) by reading their metadata from PyPI, flags copyleft, proprietary and unknown
licences, and writes ``docs/licences.md``.

    uv run python scripts/licence_audit.py            # write docs/licences.md
    uv run python scripts/licence_audit.py --offline  # installed packages only, no PyPI lookups
    uv run python scripts/licence_audit.py --check    # exit 1 if a flagged package is unreviewed

Run it after adding a dependency. A flagged package is either replaced or reviewed: add it to
``REVIEWED`` below with the reason, so the decision is written down and versioned.
"""

import argparse
import json
import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "licences.md"
OWN_PACKAGE = "vga"

# Reviewed exceptions: normalised package name -> why it is acceptable. A reviewed package is
# still listed as flagged-and-reviewed, never hidden. Keep reasons factual.
REVIEWED: dict[str, str] = {
    "certifi": "MPL-2.0 is file-level copyleft; used unmodified, never edited or redistributed.",
    "pathspec": "MPL-2.0 is file-level copyleft; a dev-only dependency of mypy, never shipped.",
    "tqdm": "MPL-2.0 AND MIT; used unmodified, so MPL's file-level terms are not triggered.",
}

# Facts shown next to an unreviewed package, so the reader sees where it comes from.
NOTES_BY_PREFIX: dict[str, str] = {
    "nvidia-": "NVIDIA CUDA library pulled in by torch on Linux CUDA builds only (not macOS)",
    "cuda-toolkit": "NVIDIA CUDA toolkit pulled in by torch on Linux CUDA builds only (not macOS)",
}

RANK = {"ok": 0, "review": 1, "unknown": 2, "copyleft": 3}
LABEL = {
    "ok": "ok",
    "review": "weak copyleft / proprietary: review",
    "unknown": "unknown licence: review",
    "copyleft": "copyleft: do not ship",
}

_COPYLEFT = re.compile(
    r"\bAGPL|Affero|\bGPL|GNU General Public|\bSSPL|Server Side Public|\bEUPL|European Union Public"
    r"|\bOSL\b|Open Software License|CC[- ]BY[- ]SA|ShareAlike",
    re.IGNORECASE,
)
_WEAK = re.compile(
    r"LGPL|Lesser General Public|Library General Public|\bMPL|Mozilla Public|\bEPL\b|Eclipse Public"
    r"|\bCDDL|Common Development and Distribution|Common Public License|\bMS-RL",
    re.IGNORECASE,
)
_PROPRIETARY = re.compile(
    r"proprietary|\bNVIDIA\b|\bEULA\b|all rights reserved|commercial licen", re.IGNORECASE
)
_UNKNOWN = {"", "unknown", "unlicensed", "none", "other"}
_TOKEN = re.compile(r"\(|\)|\bAND\b|\bOR\b")


# --------------------------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------------------------


def _classify_leaf(text: str) -> str:
    text = text.strip()
    if text.lower() in _UNKNOWN:
        return "unknown"
    # LGPL contains "GPL", so test the weak patterns first.
    if _WEAK.search(text):
        return "review"
    if _COPYLEFT.search(text):
        return "copyleft"
    if _PROPRIETARY.search(text):
        return "review"
    return "ok"


def classify(licence: str | None) -> str:
    """Return ``ok``, ``review``, ``unknown`` or ``copyleft`` for a licence string.

    Understands SPDX-style expressions (``A OR B`` means the user may choose, so the better one
    counts; ``A AND B`` means both apply, so the worse one counts) and the ``;``-joined lists
    ``pip-licenses`` produces (treated as ``AND``, the cautious reading).
    """
    if licence is None:
        return "unknown"
    worst = "ok"
    for part in licence.split(";"):
        outcome = _classify_expression(part)
        if RANK[outcome] > RANK[worst]:
            worst = outcome
    return worst


def _classify_expression(expression: str) -> str:
    tokens = [t.strip() for t in _TOKEN.split(expression) if t is not None]
    operators = _TOKEN.findall(expression)
    if not any(op in ("AND", "OR") for op in operators):
        # No operators: parentheses are just part of a name like "BSD License (BSD-3-Clause)".
        leaves = [t for t in tokens if t]
        return _worst(_classify_leaf(leaf) for leaf in leaves) if leaves else "unknown"
    return _evaluate(_parse(expression))


def _worst(outcomes: Iterable[str]) -> str:
    return max(outcomes, key=lambda outcome: RANK[outcome])


def _parse(expression: str) -> list:
    """Parse ``A AND (B OR C)`` into nested lists: ``["AND", A, ["OR", B, C]]``."""
    tokens: list[str] = []
    position = 0
    for match in _TOKEN.finditer(expression):
        text = expression[position : match.start()].strip()
        if text:
            tokens.append(text)
        tokens.append(match.group())
        position = match.end()
    tail = expression[position:].strip()
    if tail:
        tokens.append(tail)

    def parse_group(index: int) -> tuple[list, int]:
        operands: list = []
        operator = "AND"
        while index < len(tokens):
            item = tokens[index]
            if item == "(":
                inner, index = parse_group(index + 1)
                operands.append(inner)
            elif item == ")":
                return [operator, *operands], index + 1
            elif item in ("AND", "OR"):
                operator = item
                index += 1
            else:
                operands.append(item)
                index += 1
        return [operator, *operands], index

    return parse_group(0)[0]


def _evaluate(node: list | str) -> str:
    if isinstance(node, str):
        return _classify_leaf(node)
    operator, *operands = node
    outcomes = [_evaluate(operand) for operand in operands] or ["unknown"]
    if operator == "OR":
        return min(outcomes, key=lambda outcome: RANK[outcome])
    return max(outcomes, key=lambda outcome: RANK[outcome])


# --------------------------------------------------------------------------------------------
# Collecting packages
# --------------------------------------------------------------------------------------------


def normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass
class Package:
    name: str
    version: str
    licence: str
    source: str  # "installed" or "locked, not installed"
    groups: set[str] = field(default_factory=set)
    direct: bool = False

    @property
    def status(self) -> str:
        return classify(self.licence)

    @property
    def reviewed(self) -> bool:
        return self.status != "ok" and normalise(self.name) in REVIEWED


def direct_dependencies() -> dict[str, set[str]]:
    """Normalised direct dependency name -> the groups that declare it."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    found: dict[str, set[str]] = {}

    def add(requirement: object, group: str) -> None:
        if isinstance(requirement, str):
            name = re.split(r"[<>=!~;\[ ]", requirement, maxsplit=1)[0]
            found.setdefault(normalise(name), set()).add(group)

    for requirement in config["project"].get("dependencies", []):
        add(requirement, "runtime")
    for group, requirements in config.get("dependency-groups", {}).items():
        for requirement in requirements:
            add(requirement, group)
    return found


def installed_packages() -> dict[str, Package]:
    output = subprocess.run(
        [
            sys.executable,
            "-m",
            "piplicenses",
            "--format=json",
            "--with-urls",
            "--with-system",
            "--from=mixed",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    packages: dict[str, Package] = {}
    for row in json.loads(output):
        name = normalise(row["Name"])
        if name != OWN_PACKAGE:
            packages[name] = Package(row["Name"], row["Version"], row["License"], "installed")
    return packages


def locked_packages() -> dict[str, str]:
    """Normalised name -> version for every package in uv.lock except this project."""
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    return {
        normalise(entry["name"]): entry["version"]
        for entry in lock.get("package", [])
        if normalise(entry["name"]) != OWN_PACKAGE and "version" in entry
    }


def pypi_licence(name: str, version: str) -> str:
    """Licence of a package version according to PyPI metadata (PEP 639 field, then classifiers,
    then the free-text field when it is short)."""
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            info = json.load(response)["info"]
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError):
        return "UNKNOWN (PyPI lookup failed)"
    if info.get("license_expression"):
        return str(info["license_expression"])
    classifiers = [
        c.split("::")[-1].strip()
        for c in info.get("classifiers", [])
        if c.startswith("License ::") and "OSI Approved" not in c.split("::")[-1]
    ]
    if classifiers:
        return "; ".join(dict.fromkeys(classifiers))
    text = (info.get("license") or "").strip()
    if text and len(text) <= 80 and "\n" not in text:
        return text
    return "UNKNOWN"


def collect(offline: bool) -> list[Package]:
    direct = direct_dependencies()
    packages = installed_packages()
    if not offline:
        for name, version in locked_packages().items():
            if name not in packages:
                packages[name] = Package(
                    name, version, pypi_licence(name, version), "locked, not installed"
                )
    for name, package in packages.items():
        package.direct = name in direct
        package.groups = direct.get(name, set())
    return sorted(packages.values(), key=lambda p: normalise(p.name))


# --------------------------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------------------------


def note_for(name: str) -> str:
    key = normalise(name)
    return next((note for prefix, note in NOTES_BY_PREFIX.items() if key.startswith(prefix)), "")


def cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render(packages: list[Package], offline: bool) -> str:
    flagged = [p for p in packages if p.status != "ok"]
    unreviewed = [p for p in flagged if not p.reviewed]
    not_installed = [p for p in packages if p.source != "installed"]
    lines = [
        "# Dependency licences",
        "",
        "> Generated by `scripts/licence_audit.py` on "
        f"{date.today().isoformat()} (Python {sys.version.split()[0]}). Do not edit by hand: "
        "re-run the script after adding a dependency (BRD Rule 5: only commercial-friendly "
        "components).",
        "",
        "## Summary",
        "",
        f"- Packages listed: **{len(packages)}** "
        f"({sum(p.direct for p in packages)} direct, "
        f"{sum(not p.direct for p in packages)} transitive).",
        f"- Installed in this environment: {len(packages) - len(not_installed)}. "
        f"Locked but not installed here: {len(not_installed)}"
        + (" (not looked up: `--offline`)." if offline else " (licence read from PyPI metadata)."),
        f"- Flagged: **{len(flagged)}**; reviewed and accepted: {len(flagged) - len(unreviewed)}; "
        f"**still needing review: {len(unreviewed)}**.",
        "",
        "Status meanings: `ok` permissive; `weak copyleft / proprietary: review` and "
        "`unknown licence: review` need a person to decide; `copyleft: do not ship` must be "
        "replaced. A `reviewed` row has its reason recorded in `REVIEWED` in the script.",
        "",
    ]
    if flagged:
        lines += [
            "## Flagged",
            "",
            "| Package | Version | Licence | Status | Source | Decision |",
            "|---|---|---|---|---|---|",
        ]
        for p in flagged:
            note = note_for(p.name)
            decision = (
                f"reviewed: {REVIEWED[normalise(p.name)]}"
                if p.reviewed
                else "**NEEDS REVIEW**" + (f": {note}" if note else "")
            )
            lines.append(
                f"| {cell(p.name)} | {p.version} | {cell(p.licence)} | {LABEL[p.status]} | "
                f"{p.source} | {cell(decision)} |"
            )
        lines.append("")
    else:
        lines += ["## Flagged", "", "None.", ""]
    lines += [
        "## All packages",
        "",
        "| Package | Version | Licence | Direct | Groups | Status | Source |",
        "|---|---|---|---|---|---|---|",
    ]
    for p in packages:
        status = "reviewed" if p.reviewed else p.status
        lines.append(
            f"| {cell(p.name)} | {p.version} | {cell(p.licence)} | {'yes' if p.direct else 'no'} | "
            f"{', '.join(sorted(p.groups)) or '-'} | {status} | {p.source} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="skip PyPI lookups for packages that are not installed",
    )
    parser.add_argument(
        "--check", action="store_true", help="exit 1 if any flagged package is not reviewed"
    )
    parser.add_argument(
        "--output", type=Path, default=OUTPUT, help="file to write (default: docs/licences.md)"
    )
    args = parser.parse_args()

    packages = collect(args.offline)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(packages, args.offline), encoding="utf-8")

    flagged = [p for p in packages if p.status != "ok"]
    unreviewed = [p for p in flagged if not p.reviewed]
    print(
        f"{len(packages)} packages, {len(flagged)} flagged, {len(unreviewed)} unreviewed "
        f"-> {args.output}"
    )
    for p in unreviewed:
        print(f"  NEEDS REVIEW: {p.name} {p.version}: {p.licence} ({LABEL[p.status]})")
    return 1 if args.check and unreviewed else 0


if __name__ == "__main__":
    raise SystemExit(main())
