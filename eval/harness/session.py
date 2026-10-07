"""How one live session treated the stores, in the words of the report.

A run folder can be fed by more than one live session: the first run, then each ``--only`` that
finished it later (``resume.py``). Each session leaves one note in ``RunMeta.session_notes`` saying
when it ran, which queries, how long it paused between them and how it spaced the link checks, so a
report over a run finished in pieces still says how every piece was made.
"""

from dataclasses import dataclass
from datetime import date

from eval.harness.links import LinksMode
from eval.harness.runstore import WarmUp


@dataclass(frozen=True)
class Session:
    """The settings of one live session."""

    number: int
    """1 for the first run, 2 for the first ``--only`` that continued it, and so on."""
    day: date
    ran: tuple[str, ...] | None
    """The queries it was asked to run, or ``None`` when it was all of them."""
    pause_s: float
    link_interval_s: float
    links: LinksMode


def session_note(session: Session, warm_up: WarmUp | None) -> str:
    """One sentence for the report's notes. ``warm_up`` is this session's own (only a later
    session's is spelled out: the first one is the run's, shown with the timings)."""
    when = session.day.isoformat()
    if session.ran is not None:
        when += f", ran {', '.join(session.ran)}"
    if session.pause_s > 0:
        pause = (
            f"paused {session.pause_s:g} s between queries (`--pause`), outside every query's "
            "seconds, so the stores were not asked ten searches in a minute"
        )
    else:
        pause = "no pause between queries (`--pause 0`)"
    if session.links is LinksMode.NONE:
        links = "links were not checked (`--links none`)"
    elif session.link_interval_s > 0:
        links = (
            f"sent at most one link request every {session.link_interval_s:g} s across all "
            "stores (`--link-interval`), on top of the fetch engine's own per-store limit"
        )
    else:
        links = (
            "link checks were not spaced out (`--link-interval 0`); only the fetch engine's own "
            "limits applied"
        )
    note = f"Session {session.number} ({when}): {pause}; {links}"
    if session.number > 1 and warm_up is not None:
        state = (
            "image scoring ready"
            if warm_up.ready
            else "image scoring NOT available, so photo queries were ranked on text and price"
        )
        note += f"; the model warm-up took {warm_up.duration_ms / 1000:.1f} s and {state}"
    return note + "."
