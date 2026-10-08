"""The list of critical tests (``tests/critical_suite.txt``) cannot rot silently.

CI runs only the tests that list names (``pytest -m critical``), so a list that quietly stopped
naming real tests would make CI pass while checking nothing. ``tests/conftest.py`` marks the tests
the list names and keeps what it found; these checks turn every way the list can go wrong into a
failure, in the complete suite and in the critical one alike (this file is itself critical).

``-m critical`` replaces the ``-m 'not live'`` of ``addopts`` instead of adding to it, so a
critical test that was also marked ``live`` would be run by CI against the real network. That is
the second check below.
"""

import re
from collections import Counter

from tests.conftest import CRITICAL_LIST, CriticalSuite, critical_names

CEILING = 150
"""The most tests the critical suite may hold. The suite is meant to stay small and fast, so
growth is a deliberate edit of this number next to the new entries, not an accident."""

SLACK = 12
"""How far below the ceiling the real count may sit. A ceiling far above the count would let the
suite grow unnoticed, so lowering the list means lowering the ceiling too."""

LINES = [str(number) for number in range(1, 16)]
"""The fifteen lines of what "critical" means, as the headings of the list number them."""

HEADING = re.compile(r"^# \[(\w+)\]")


def test_every_entry_names_a_test_that_exists(critical_suite: CriticalSuite) -> None:
    assert critical_suite.entries, f"{CRITICAL_LIST.name} names no test at all"

    unmatched = critical_suite.unmatched_entries()

    assert unmatched == [], f"entries of {CRITICAL_LIST.name} that name no test:\n" + "\n".join(
        unmatched
    )


def test_no_entry_is_listed_twice(critical_suite: CriticalSuite) -> None:
    times_listed = Counter(critical_suite.entries)

    repeated = [entry for entry, times in times_listed.items() if times > 1]

    assert repeated == [], "listed more than once:\n" + "\n".join(repeated)


def test_no_critical_test_is_also_marked_live(critical_suite: CriticalSuite) -> None:
    live = critical_suite.critical_and_live

    assert live == [], "critical tests that are marked live (CI would hit the network):\n" + (
        "\n".join(live)
    )


def test_the_critical_count_stays_under_its_ceiling_and_close_to_it(
    critical_suite: CriticalSuite,
) -> None:
    count = len(critical_suite.critical)

    assert count <= CEILING, f"{count} critical tests; raise CEILING on purpose, or list fewer"
    if critical_suite.collected_the_whole_suite():
        assert count >= CEILING - SLACK, f"{count} critical tests; lower CEILING to match"


def test_each_of_the_fifteen_lines_has_a_heading_and_a_test() -> None:
    headings: list[str] = []
    entries_under: dict[str, int] = {}
    for raw in CRITICAL_LIST.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if heading := HEADING.match(line):
            headings.append(heading.group(1))
            entries_under[heading.group(1)] = 0
        elif line and not line.startswith("#") and headings:
            entries_under[headings[-1]] += 1

    assert headings == [*LINES, "own"]
    assert [name for name, count in entries_under.items() if count == 0] == []


def test_an_entry_names_one_case_a_test_with_its_cases_a_class_or_a_file() -> None:
    case = "tests/ui/test_chips.py::TestApply::test_a[x-1]"

    assert critical_names(case) == {
        case,
        "tests/ui/test_chips.py::TestApply::test_a",
        "tests/ui/test_chips.py::TestApply",
        "tests/ui/test_chips.py",
    }
    assert critical_names("tests/ui/test_page.py::test_b") == {
        "tests/ui/test_page.py::test_b",
        "tests/ui/test_page.py",
    }
