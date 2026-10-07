"""3.1.1 Load and embed: load FashionSigLIP at the pinned revision, embed one image + one text.

Run:
    uv run python 01_load_embed.py                # first run downloads ~0.8 GB, then embeds
    uv run python 01_load_embed.py --offline      # proves it works with the network cut

Prints (and writes results/load_embed[_offline].json): embedding dimension, revision hash,
download size on disk, load times per device, versions of torch / open_clip_torch / pillow.
The "image" is a synthetic gradient so this step has no image-licence dependency; real
images are used from step 3.1.2/3.1.3 on.
"""

from __future__ import annotations

import argparse
import sys
import time

import common

parser = argparse.ArgumentParser()
parser.add_argument("--offline", action="store_true", help="forbid all network access")
parser.add_argument("--loads", type=int, default=3, help="model loads per device to time")
args = parser.parse_args()
if args.offline:
    common.go_offline()

import numpy as np  # noqa: E402
import torch  # noqa: E402
from PIL import Image  # noqa: E402


def dir_bytes_following_links(root: str) -> int:
    """Size of the real blobs behind a HF snapshot dir (it is made of symlinks)."""
    from pathlib import Path

    return sum(p.resolve().stat().st_size for p in Path(root).rglob("*") if p.is_file())


def synthetic_image(size: int = 400) -> Image.Image:
    x = np.linspace(0, 255, size, dtype=np.uint8)
    arr = np.stack([np.tile(x, (size, 1)), np.tile(x[::-1], (size, 1)), np.full((size, size), 128, np.uint8)], axis=-1)
    return Image.fromarray(arr, "RGB")


def main() -> None:
    result: dict = {
        "offline": args.offline,
        "repo": common.REPO_ID,
        "revision": common.REVISION,
        "versions": common.versions(),
        "devices_available": common.available_devices(),
        "per_device": {},
    }
    print(f"offline={args.offline}  revision={common.REVISION}")
    print("versions:", result["versions"])

    for device in result["devices_available"]:
        loads = []
        for i in range(args.loads):
            t0 = time.perf_counter()
            model, preprocess, tokenizer, info = common.load_model(device, with_text=True)
            total = time.perf_counter() - t0
            loads.append(
                {
                    "run": i + 1,
                    "total_s": total,
                    "snapshot_s": info["snapshot_seconds"],
                    "build_and_to_device_s": info["build_and_to_device_seconds"],
                }
            )
            print(f"[{device}] load #{i + 1}: total {total:.2f}s "
                  f"(snapshot {info['snapshot_seconds']:.2f}s, build+to({device}) {info['build_and_to_device_seconds']:.2f}s)")
            if i < args.loads - 1:
                del model
        local_dir = info["local_dir"]

        image = synthetic_image()
        with torch.no_grad():
            img_t = preprocess(image).unsqueeze(0).to(device)
            txt_t = tokenizer(["a red cotton t-shirt"]).to(device)
            img_emb = model.encode_image(img_t, normalize=True)
            txt_emb = model.encode_text(txt_t, normalize=True)
            common.sync(device)
        dim = int(img_emb.shape[-1])
        cos = float((img_emb @ txt_emb.T).item())
        result["per_device"][device] = {
            "embedding_dim_image": dim,
            "embedding_dim_text": int(txt_emb.shape[-1]),
            "image_embedding_norm": float(img_emb.norm().item()),
            "dtype": str(img_emb.dtype),
            "image_input_shape": list(img_t.shape),
            "text_token_shape": list(txt_t.shape),
            "synthetic_image_vs_text_cosine": cos,
            "loads": loads,
            "median_load_total_s": common.median([load["total_s"] for load in loads]),
            "first_load_total_s": loads[0]["total_s"],
        }
        print(f"[{device}] image dim={dim} text dim={int(txt_emb.shape[-1])} "
              f"norm={img_emb.norm().item():.4f} cos(synthetic img, text)={cos:.4f}")
        result["snapshot_dir"] = local_dir
        result["snapshot_bytes_on_disk"] = dir_bytes_following_links(local_dir)
        result["parameters_millions"] = sum(p.numel() for p in model.parameters()) / 1e6
        del model

    print(f"snapshot on disk: {result['snapshot_bytes_on_disk'] / 1e6:.1f} MB; "
          f"parameters: {result['parameters_millions']:.1f} M")
    path = common.write_json("load_embed_offline.json" if args.offline else "load_embed.json", result)
    print("wrote", path.relative_to(common.SPIKE_DIR))


if __name__ == "__main__":
    sys.exit(main())
