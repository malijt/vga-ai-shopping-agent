"""Behind-the-scenes details of one search (plan 10.2.5): which stores were skipped and why, and
how long each step took and how many AI tokens it used (PRD R12).

Both live in expanders so they are there when wanted and out of the way otherwise. Every line is
plain text: store ids and reasons come from configuration and from the pipeline.
"""

import streamlit as st
from app.safe_text import plain_text

from vga.models import SearchResponse, StepTiming

LINE_MAX_CHARS = 200


def timing_line(timing: StepTiming) -> str:
    """``fetch (souq-atelier): 1.8 s`` and, when a step did not finish well, its status."""
    where = f" ({plain_text(timing.store, 60)})" if timing.store else ""
    outcome = "" if timing.status == "ok" else f", {plain_text(timing.status, 40)}"
    return f"{plain_text(timing.step, 40)}{where}: {timing.duration_ms / 1000:.1f} s{outcome}"


def render_skipped_stores(response: SearchResponse) -> None:
    """List every skipped store with the reason, in an expander. Nothing when none were skipped."""
    skipped = response.stores_skipped
    if not skipped:
        return
    with st.expander(f"Skipped stores ({len(skipped)})", key="skipped_stores"):
        st.text(
            "\n".join(
                f"{plain_text(report.store_id, 60)}: {plain_text(report.reason, LINE_MAX_CHARS)}"
                for report in skipped
            )
        )


def render_timings_and_usage(response: SearchResponse) -> None:
    """Show the time per step and the AI token use, in an expander."""
    usage = response.usage
    lines = [f"Total time: {response.duration_ms / 1000:.1f} s"]
    lines.extend(timing_line(timing) for timing in response.timings)
    lines.append(
        f"AI calls: {usage.llm_calls}. Tokens in: {usage.input_tokens:,}, "
        f"out: {usage.output_tokens:,}, total: {usage.total_tokens:,}."
    )
    with st.expander("Timings and AI usage", key="timings_usage"):
        st.text("\n".join(lines))


def render_run_details(response: SearchResponse) -> None:
    searched = len(response.stores_used) + len(response.stores_skipped)
    st.text(
        f"Stores searched: {searched}. "
        f"{len(response.stores_used)} returned products, {len(response.stores_skipped)} skipped."
    )
    render_skipped_stores(response)
    render_timings_and_usage(response)
