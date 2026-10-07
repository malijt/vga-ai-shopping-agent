"""3.1.3 Quality smoke test: do FashionSigLIP cosines rank clothing sensibly, and what 0-1 mapping fits?

Run:  uv run python 03_quality.py            # needs `00_fetch_images.py` to have been run

Method
  * Candidates are the sample images as ~400 px JPEG thumbnails (what a store CDN would give us).
  * A query is one of the 5 chosen images (full 500 px download, as a stand-in for the shopper's
    photo) ranked against all the OTHER images by cosine similarity.
  * Pairwise cosines over every image pair are grouped by relation: same kind of item (jeans vs
    jeans), same category but a different kind (jeans vs trousers), different category.
  * "Same item, different photo" is approximated by synthetic variants of each image (mirror,
    80% centre crop, 250 px low-quality JPEG, colour shift). This is only a proxy for the upper end
    of the scale; it is not a substitute for real same-product photos.
  * The 0-1 mapping constants are derived from those distributions below and printed.

Writes results/quality.json.
"""

from __future__ import annotations

import io
import sys
from itertools import combinations

import numpy as np
import torch
from PIL import Image, ImageEnhance, ImageOps

import common

QUERY_IDS = [
    "02_top_tshirt",
    "06_top_sweater",
    "11_outerwear_jacket",
    "13_bottom_jeans",
    "20_shoes_sneakers",
]


# Noun phrases for the supplementary zero-shot text check, keyed by the manifest's "kind".
KIND_PROMPTS = {
    "tshirt": "a t-shirt",
    "shirt": "a button-up shirt",
    "sweater": "a sweater",
    "parka": "a parka",
    "coat": "a long coat",
    "jacket": "a jacket",
    "jeans": "jeans",
    "trousers": "trousers",
    "shorts": "shorts",
    "sneakers": "sneakers",
    "dress-shoes": "leather dress shoes",
    "dress": "a dress",
}


def embed_images(model, preprocess, device: str, images: list[Image.Image], batch_size: int = 16) -> np.ndarray:
    out = []
    for i in range(0, len(images), batch_size):
        batch = torch.stack([preprocess(common.to_rgb(im)) for im in images[i : i + batch_size]])
        with torch.inference_mode():
            out.append(model.encode_image(batch.to(device), normalize=True).cpu())
    return torch.cat(out).numpy()


def variants(original: Image.Image) -> dict[str, Image.Image]:
    img = common.to_rgb(original)
    w, h = img.size
    crop = img.crop((int(w * 0.1), int(h * 0.1), int(w * 0.9), int(h * 0.9)))
    small = img.copy()
    small.thumbnail((250, 250))
    buf = io.BytesIO()
    small.save(buf, format="JPEG", quality=40)
    low = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    colour = ImageEnhance.Color(ImageEnhance.Contrast(ImageEnhance.Brightness(img).enhance(0.8)).enhance(1.2)).enhance(0.8)
    return {"mirror": ImageOps.mirror(img), "crop80": crop, "lowres_jpeg": low, "colour_shift": colour}


def stats(values: list[float]) -> dict:
    a = np.array(values)
    return {
        "n": int(a.size),
        "min": float(a.min()),
        "p10": float(np.percentile(a, 10)),
        "median": float(np.median(a)),
        "p90": float(np.percentile(a, 90)),
        "max": float(a.max()),
    }


def main() -> int:
    entries = common.load_image_set()
    ids = [e["id"] for e in entries]
    for q in QUERY_IDS:
        if q not in ids:
            common.die(f"query image {q} not in image set; update QUERY_IDS (ids: {ids})")

    originals = [common.to_rgb(Image.open(e["path"])) for e in entries]
    thumbs = [Image.open(io.BytesIO(common.make_thumbnail_bytes(e["path"]))).convert("RGB") for e in entries]

    devices = common.available_devices()
    sims: dict[str, np.ndarray] = {}
    query_to_cand: dict[str, np.ndarray] = {}
    variant_cos: dict[str, list[float]] = {}
    zero_shot: dict = {}
    for device in devices:
        model, preprocess, tokenizer, _info = common.load_model(device, with_text=device == devices[0])
        cand = embed_images(model, preprocess, device, thumbs)
        if tokenizer is not None:
            kinds = sorted({e["kind"] for e in entries})
            prompts = [f"a product photo of {KIND_PROMPTS[k]}" for k in kinds]
            with torch.inference_mode():
                text = model.encode_text(tokenizer(prompts).to(device), normalize=True).cpu().numpy()
            predicted = [kinds[int(np.argmax(cand[i] @ text.T))] for i in range(len(entries))]
            category_of = {e["kind"]: e["category"] for e in entries}
            zero_shot = {
                "images": len(entries),
                "prompts": prompts,
                "kind_accuracy": float(np.mean([p == e["kind"] for p, e in zip(predicted, entries)])),
                "category_accuracy": float(np.mean([category_of[p] == e["category"] for p, e in zip(predicted, entries)])),
                "errors": [{"id": e["id"], "true_kind": e["kind"], "predicted_kind": p}
                           for p, e in zip(predicted, entries) if p != e["kind"]],
            }
        orig = embed_images(model, preprocess, device, originals)
        sims[device] = cand @ cand.T
        query_to_cand[device] = orig @ cand.T  # row i: full-size image i vs every thumbnail
        if device == devices[0]:
            names = ["mirror", "crop80", "lowres_jpeg", "colour_shift"]
            per_variant: dict[str, list[Image.Image]] = {n: [] for n in names}
            for im in originals:
                for name, v in variants(im).items():
                    per_variant[name].append(v)
            for name in names:
                v_emb = embed_images(model, preprocess, device, per_variant[name])
                variant_cos[name] = [float(v_emb[i] @ cand[i]) for i in range(len(entries))]
        del model

    primary = devices[0]
    sim = sims[primary]
    cross = {d: float(np.abs(sims[d] - sim).max()) for d in devices[1:]}
    print(f"analysis device: {primary}; max |cos(other device) - cos({primary})| over all pairs: {cross}")

    # ---- Distributions by relation -------------------------------------------------
    groups: dict[str, list[float]] = {"same_kind": [], "same_category_other_kind": [], "different_category": []}
    for i, j in combinations(range(len(entries)), 2):
        a, b = entries[i], entries[j]
        if a["category"] != b["category"]:
            groups["different_category"].append(float(sim[i, j]))
        elif a["kind"] == b["kind"]:
            groups["same_kind"].append(float(sim[i, j]))
        else:
            groups["same_category_other_kind"].append(float(sim[i, j]))
    dist = {k: stats(v) for k, v in groups.items()}
    all_variant = [c for cs in variant_cos.values() for c in cs]
    dist["synthetic_same_item_variants"] = stats(all_variant)
    dist["synthetic_same_item_variants_by_kind_of_edit"] = {k: stats(v) for k, v in variant_cos.items()}
    print("\nCosine distributions (min / p10 / median / p90 / max):")
    for name in ("synthetic_same_item_variants", "same_kind", "same_category_other_kind", "different_category"):
        s = dist[name]
        print(f"  {name:32s} n={s['n']:>3}  {s['min']:.3f} / {s['p10']:.3f} / {s['median']:.3f} / {s['p90']:.3f} / {s['max']:.3f}")

    # ---- Top-3 for the five queries -----------------------------------------------
    queries_out = []
    print("\nTop-3 for each query (query = full-size image, candidates = other thumbnails):")
    for qid in QUERY_IDS:
        qi = ids.index(qid)
        scores = [(j, float(query_to_cand[primary][qi, j])) for j in range(len(entries)) if j != qi]
        scores.sort(key=lambda t: t[1], reverse=True)
        top = scores[:3]
        peers_kind = sum(1 for j in range(len(entries)) if j != qi and entries[j]["kind"] == entries[qi]["kind"])
        record = {
            "query": qid,
            "query_title": entries[qi]["title"],
            "query_kind": entries[qi]["kind"],
            "same_kind_candidates_available": peers_kind,
            "top3": [
                {
                    "id": entries[j]["id"],
                    "kind": entries[j]["kind"],
                    "category": entries[j]["category"],
                    "cosine": c,
                    "same_kind": entries[j]["kind"] == entries[qi]["kind"],
                    "same_category": entries[j]["category"] == entries[qi]["category"],
                }
                for j, c in top
            ],
            "best_cosine_in_other_category": max(c for j, c in scores if entries[j]["category"] != entries[qi]["category"]),
            "worst_cosine_in_same_category": min(
                (c for j, c in scores if entries[j]["category"] == entries[qi]["category"]), default=None
            ),
        }
        queries_out.append(record)
        print(f"  {qid} ({entries[qi]['kind']}; {peers_kind} same-kind peers):")
        for t in record["top3"]:
            flag = "same kind" if t["same_kind"] else ("same category" if t["same_category"] else "DIFFERENT CATEGORY")
            print(f"      {t['cosine']:.3f}  {t['id']:28s} {flag}")
        print(f"      best other-category cosine {record['best_cosine_in_other_category']:.3f}")

    # ---- Leave-one-out retrieval over every image ---------------------------------
    # Each image in turn is the query; the other 25 thumbnails are ranked. Judged on category
    # (top / outerwear / bottom / shoes); the single dress has no peers and is skipped as a query.
    per_category: dict[str, dict[str, list[float]]] = {}
    p1 = []
    p3 = []
    for i, e in enumerate(entries):
        peers = sum(1 for j in range(len(entries)) if j != i and entries[j]["category"] == e["category"])
        if peers < 3:
            continue
        order = [j for j in np.argsort(-sim[i]) if j != i]
        hit1 = entries[order[0]]["category"] == e["category"]
        prec3 = sum(entries[j]["category"] == e["category"] for j in order[:3]) / 3
        p1.append(hit1)
        p3.append(prec3)
        bucket = per_category.setdefault(e["category"], {"top1": [], "top3": []})
        bucket["top1"].append(float(hit1))
        bucket["top3"].append(prec3)
    loo = {
        "queries": len(p1),
        "top1_same_category": float(np.mean(p1)),
        "top3_same_category_precision": float(np.mean(p3)),
        "by_category": {c: {"queries": len(v["top1"]), "top1": float(np.mean(v["top1"])), "top3_precision": float(np.mean(v["top3"]))}
                        for c, v in per_category.items()},
    }
    print(f"\nLeave-one-out over {loo['queries']} images (categories with >=3 peers): "
          f"top-1 same category {loo['top1_same_category']:.2f}, top-3 precision {loo['top3_same_category_precision']:.2f}")
    for c, v in loo["by_category"].items():
        print(f"    {c:10s} queries={v['queries']} top-1 {v['top1']:.2f} top-3 precision {v['top3_precision']:.2f}")

    # ---- Proposed 0-1 mapping ------------------------------------------------------
    # lo: the noise floor, i.e. the median cosine of images from different categories, rounded down
    #     to 0.05. Anything at or below it carries no evidence of similarity -> 0.
    # hi: the p10 of the synthetic same-photo variants, rounded down to 0.05. A faithful copy of the
    #     same product photo scores at or above it -> 1. Real "same product, different photo" pairs
    #     will land lower than these synthetic edits, so this top is an optimistic anchor.
    def floor_005(x: float) -> float:
        return float(np.floor(x * 20) / 20)

    lo = floor_005(dist["different_category"]["median"])
    hi = floor_005(dist["synthetic_same_item_variants"]["p10"])
    proposal = {
        "formula": "score = clip((cosine - lo) / (hi - lo), 0, 1)",
        "lo": round(lo, 2),
        "hi": round(hi, 2),
        "lo_rule": "median cosine between images of different categories, rounded down to 0.05",
        "hi_rule": "10th percentile cosine of synthetic same-photo variants, rounded down to 0.05",
    }
    mapped = {}
    for name, values in {**groups, "synthetic_same_item_variants": all_variant}.items():
        s = np.clip((np.array(values) - lo) / (hi - lo), 0, 1)
        mapped[name] = {"min": float(s.min()), "p10": float(np.percentile(s, 10)), "median": float(np.median(s)),
                        "p90": float(np.percentile(s, 90)), "max": float(s.max())}
    proposal["resulting_score_distribution"] = mapped
    print("\nProposal:", proposal["formula"], "with lo =", proposal["lo"], "hi =", proposal["hi"])
    for name, s in mapped.items():
        print(f"  {name:32s} score min/p10/median/p90/max = {s['min']:.2f} / {s['p10']:.2f} / {s['median']:.2f} / {s['p90']:.2f} / {s['max']:.2f}")

    # ---- Supplementary: zero-shot text check ---------------------------------------
    # Not part of the Phase 8 ranker (which is image vs image). It shows whether the model "knows"
    # these garments at all, which separates "weak model" from "weak image-image signal".
    print("\nSupplementary zero-shot text->image check (prompt 'a product photo of <noun>'):")
    print(f"  kind-level accuracy {zero_shot['kind_accuracy']:.2f}, category-level accuracy {zero_shot['category_accuracy']:.2f} "
          f"over {zero_shot['images']} images")
    for wrong in zero_shot["errors"]:
        print(f"    {wrong['id']}: predicted {wrong['predicted_kind']} (true {wrong['true_kind']})")

    path = common.write_json(
        "quality.json",
        {
            "analysis_device": primary,
            "max_abs_cosine_difference_vs_primary": cross,
            "images": [{"id": e["id"], "category": e["category"], "kind": e["kind"], "title": e["title"]} for e in entries],
            "similarity_matrix_thumbnails": [[round(float(x), 4) for x in row] for row in sim],
            "distributions": dist,
            "queries": queries_out,
            "leave_one_out": loo,
            "proposed_normalisation": proposal,
            "zero_shot_text_check": zero_shot,
        },
    )
    print("\nwrote", path.relative_to(common.SPIKE_DIR))
    return 0


if __name__ == "__main__":
    sys.exit(main())
