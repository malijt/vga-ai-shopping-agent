"""Does the image-vs-image ranker (Phase 8) need `transformers`? (It only builds the vision tower.)

Run:  uv run python 05_image_only_check.py

`transformers` is only used by open_clip's text tokenizer. This script makes `import transformers`
fail on purpose, then loads the pinned model and embeds an image. If it succeeds, the Phase 8 `ml`
dependency group can drop `transformers` (and its tokenizers / typer / rich tail) and keep
torch, open_clip_torch, timm, huggingface_hub, pillow, numpy.
"""

from __future__ import annotations

import sys

import common

# Any attempt to import transformers (or tokenizers) now raises ImportError.
for blocked in ("transformers", "tokenizers"):
    sys.modules[blocked] = None  # type: ignore[assignment]

import torch  # noqa: E402

images = common.load_image_set()
device = common.available_devices()[0]
model, preprocess, tokenizer, _info = common.load_model(device)  # with_text=False: no tokenizer built
from PIL import Image  # noqa: E402

with torch.inference_mode():
    batch = torch.stack([preprocess(common.to_rgb(Image.open(e["path"]))) for e in images[:4]])
    emb = model.encode_image(batch.to(device), normalize=True).cpu()
# Reaching this line means nothing tried to import the blocked modules (that would have raised).
print(f"OK without transformers/tokenizers on {device}: embeddings {tuple(emb.shape)}, tokenizer built: {tokenizer is not None}")
