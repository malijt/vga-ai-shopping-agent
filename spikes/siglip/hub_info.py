"""Print the current Hugging Face commit hash, licence and file sizes for the model.

Run:  uv run python hub_info.py        (needs network; read-only metadata call)
"""

from __future__ import annotations

import common  # noqa: F401  (sets HF_HOME before huggingface_hub is imported)
from huggingface_hub import HfApi


def main() -> None:
    api = HfApi()
    info = api.model_info(common.REPO_ID, files_metadata=True)
    print(f"repo            : {common.REPO_ID}")
    print(f"latest sha      : {info.sha}")
    print(f"pinned sha      : {common.REVISION}")
    print(f"last modified   : {info.last_modified}")
    print(f"licence (card)  : {getattr(info.card_data, 'license', None)}")
    total = 0
    for sibling in info.siblings or []:
        size = sibling.size or 0
        total += size
        print(f"  {sibling.rfilename:40s} {size:>14,d} bytes")
    print(f"total repo size : {total:,d} bytes ({total / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
