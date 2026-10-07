"""Render results/*.json as the Markdown tables used in REPORT.md (so numbers are never retyped).

Run:  uv run python 04_make_tables.py            # prints to stdout and writes results/tables.md
"""

from __future__ import annotations

import json
import sys

import common


def load(name: str) -> dict:
    path = common.RESULTS_DIR / name
    if not path.exists():
        common.die(f"{name} missing: run the earlier scripts first (see README in REPORT.md)")
    return json.loads(path.read_text())


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def main() -> int:
    out: list[str] = []

    # --- 3.1.1 ---
    le = load("load_embed.json")
    off = load("load_embed_offline.json")
    out.append("### 3.1.1 Load and embed\n")
    rows = []
    for device, d in le["per_device"].items():
        loads = ", ".join(f"{x['total_s']:.2f}" for x in d["loads"])
        build = ", ".join(f"{x['build_and_to_device_s']:.2f}" for x in d["loads"])
        rows.append([device, str(d["embedding_dim_image"]), f"{d['image_embedding_norm']:.4f}", build, loads])
    out.append(md_table(["device", "embedding dim", "L2 norm", "model build + move to device, 3 loads (s)", "load incl. tokenizer, 3 loads (s)"], rows))
    out.append("")
    out.append(f"- revision: `{le['revision']}`; snapshot on disk: {le['snapshot_bytes_on_disk'] / 1e6:.1f} MB; parameters: {le['parameters_millions']:.1f} M")
    out.append("- versions: " + ", ".join(f"{k} {v}" for k, v in le["versions"].items()))
    off_rows = [[device, f"{d['first_load_total_s']:.2f}", str(d["embedding_dim_image"])] for device, d in off["per_device"].items()]
    out.append("")
    out.append("Offline re-run (`HF_HUB_OFFLINE=1` plus a dead proxy so any network attempt fails):\n")
    out.append(md_table(["device", "load incl. tokenizer (s)", "embedding dim"], off_rows))
    out.append("")

    # --- 3.1.2 ---
    bench = load("benchmark.json")
    out.append("### 3.1.2 Latency (seconds, median of %d runs; JPEG decode + preprocess + model, no network)\n" % bench["runs_per_cell"])
    sizes = sorted({c["n"] for d in bench["devices"].values() for c in d["cells"]})
    batches = sorted({c["batch"] for d in bench["devices"].values() for c in d["cells"]})
    rows = []
    for device, d in bench["devices"].items():
        for b in batches:
            row = [device, str(b)]
            for n in sizes:
                cell = next(c for c in d["cells"] if c["n"] == n and c["batch"] == b)
                row.append(f"{cell['median_s']:.2f}")
            rows.append(row)
    out.append(md_table(["device", "batch"] + [f"{n} thumbs" for n in sizes], rows))
    out.append("")
    out.append("Spread and split for 40 thumbnails:\n")
    rows = []
    for device, d in bench["devices"].items():
        for b in batches:
            cell = next(c for c in d["cells"] if c["n"] == 40 and c["batch"] == b)
            rows.append([device, str(b), f"{cell['median_s']:.3f}", f"{cell['min_s']:.3f} to {cell['max_s']:.3f}",
                         f"{cell['median_preprocess_s']:.3f}", f"{cell['median_forward_s']:.3f}", f"{cell['images_per_s']:.0f}",
                         "yes" if cell["max_s"] <= 3.0 else "NO"])
    out.append(md_table(["device", "batch", "median (s)", "min to max (s)", "CPU preprocess (s)", "device forward (s)", "images/s", "worst run within 3 s?"], rows))
    out.append("")
    out.append(f"Cold first call right after load (8 images, no warm-up): " + ", ".join(
        f"{device} {d['cold_first_call_8_images_s']:.2f} s" for device, d in bench["devices"].items()))
    out.append(f"Machine state: {bench['power_source']}; load average at start {bench['load_average_start']}, at end {bench['load_average_end']}; "
               f"torch threads {bench['torch_threads']}; peak RSS {bench.get('peak_rss_mb', float('nan')):.0f} MB (whole process, both devices).")
    out.append("")

    # --- 3.1.3 ---
    src = load("image_sources.json")
    out.append("### 3.1.3 Image sources and licences (Wikimedia Commons, accessed %s)\n" % src["accessed"])
    rows = []
    for img in src["images"]:
        author = " ".join((img["author"] or "unknown").split())
        author = author.replace("Unknown authorUnknown author", "Unknown author")
        author = (author[:40] + "...") if len(author) > 43 else author
        title = img["title"].removeprefix("File:")
        title = (title[:42] + "...") if len(title) > 45 else title
        rows.append([img["id"], f"{img['category']} / {img['kind']}", f"[{title}]({img['source_page']})", img["licence"], author.replace("|", "/")])
    out.append(md_table(["id", "category / kind", "source page", "licence", "author (as listed)"], rows))
    out.append("")

    q = load("quality.json")
    out.append("Cosine distributions (min / p10 / median / p90 / max), analysis on `%s`:\n" % q["analysis_device"])
    rows = []
    for name in ("synthetic_same_item_variants", "same_kind", "same_category_other_kind", "different_category"):
        s = q["distributions"][name]
        rows.append([name, str(s["n"])] + [f"{s[k]:.3f}" for k in ("min", "p10", "median", "p90", "max")])
    out.append(md_table(["pair type", "pairs", "min", "p10", "median", "p90", "max"], rows))
    out.append("")
    out.append("Top-3 for the five queries (query = full-size image; candidates = the other 25 thumbnails):\n")
    rows = []
    for rec in q["queries"]:
        for rank, t in enumerate(rec["top3"], start=1):
            verdict = "same kind" if t["same_kind"] else ("same category" if t["same_category"] else "different category")
            rows.append([rec["query"] if rank == 1 else "", str(rank), t["id"], f"{t['cosine']:.3f}", verdict])
    out.append(md_table(["query", "rank", "result", "cosine", "relation"], rows))
    out.append("")
    loo = q["leave_one_out"]
    out.append(f"Leave-one-out over {loo['queries']} images: top-1 in the same category {loo['top1_same_category']:.2f}, "
               f"top-3 precision {loo['top3_same_category_precision']:.2f}.\n")
    rows = [[c, str(v["queries"]), f"{v['top1']:.2f}", f"{v['top3_precision']:.2f}"] for c, v in loo["by_category"].items()]
    out.append(md_table(["category", "queries", "top-1 same category", "top-3 precision"], rows))
    out.append("")
    p = q["proposed_normalisation"]
    out.append(f"Proposed mapping: `{p['formula']}` with lo = {p['lo']}, hi = {p['hi']}.\n")
    rows = [[name] + [f"{s[k]:.2f}" for k in ("min", "p10", "median", "p90", "max")] for name, s in p["resulting_score_distribution"].items()]
    out.append(md_table(["pair type", "min", "p10", "median", "p90", "max"], rows))
    out.append("")
    z = q["zero_shot_text_check"]
    out.append(f"Supplementary zero-shot text check: kind accuracy {z['kind_accuracy']:.2f}, category accuracy {z['category_accuracy']:.2f} over {z['images']} images; "
               f"errors: {', '.join(e['id'] + ' predicted ' + e['predicted_kind'] for e in z['errors']) or 'none'}.")

    text = "\n".join(out) + "\n"
    (common.RESULTS_DIR / "tables.md").write_text(text)
    print(text)

    # Keep REPORT.md's measurement tables in sync: everything between the two markers is replaced.
    report = common.SPIKE_DIR / "REPORT.md"
    begin, end = "<!-- BEGIN GENERATED TABLES -->", "<!-- END GENERATED TABLES -->"
    if report.exists() and begin in report.read_text() and end in report.read_text():
        body = report.read_text()
        head, rest = body.split(begin, 1)
        _, tail = rest.split(end, 1)
        report.write_text(f"{head}{begin}\n\n{text}\n{end}{tail}")
        print("updated tables in REPORT.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
