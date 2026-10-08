# Dependency licences

> Final licence audit, 2026-10-08 (plan feature 16.2.5; BRD Rule 5: only commercial-friendly
> components). The Python package tables further down are the output of `scripts/licence_audit.py`
> (feature 1.4.1). Everything above them is written by hand: the decisions, the two models and how
> the audit was run. **Running the script overwrites this whole file**, so a later run must keep
> those parts (or write to another file with `--output`).

## Result in short

- **145 packages** are locked in `uv.lock` (21 direct, 124 transitive). The licence of 122 of them was
  read today from the installed packages. The other 23 are not installed on this Mac, so their
  licences are carried forward from the audit of 2026-10-07 (see "Locked, not installed here").
- **No strong copyleft** (GPL, AGPL, SSPL, EUPL, CC BY-SA) in any of the 145.
- **Three weak-copyleft packages** (MPL-2.0): `certifi`, `pathspec` and `tqdm`. Each is already
  reviewed in the script, with a reason.
- **Sixteen NVIDIA CUDA packages** have a proprietary or an unknown licence (11 proprietary, 5
  unknown). They are installed only by `torch` on Linux, never on this Mac. **They are not reviewed.**
  They need the owner's decision below. Until then the acceptance rule for feature 16.2.5, "no
  unreviewed copyleft or unknown licence", is **not met**.
- **The two models** are not Python packages, so the tool does not see them. `gpt-6-luna` is a hosted
  service used under OpenAI's terms. Marqo-FashionSigLIP is Apache-2.0 according to its model card. See
  "The two models".
- Every other package is permissive (MIT, BSD, Apache-2.0, PSF, a Pillow/HPND-style licence, W3C,
  Zlib, CC0).
- Compared with 2026-10-07: `uv.lock` holds the same 145 packages at the same versions, and every
  licence read today matches the earlier one. The one change: `httpx2` is now a declared dev
  dependency (the Understand tests import it), so it counts as direct.

## How the audit was run

1. `uv sync --offline --frozen --group ml`. This installs from uv's local cache only. Nothing was
   downloaded, and `uv.lock` was not changed. It put the optional `ml` group (`torch`, `open-clip-torch`
   and their dependencies) into the environment, so those 15 packages were read from their own
   metadata today rather than from PyPI.
2. `uv run --offline --frozen python scripts/licence_audit.py --offline`. The tool lists every
   installed package with `pip-licenses`, classifies each licence, and flags copyleft, proprietary and
   unknown ones. `--offline` skips the PyPI lookups it would make for locked packages that are not
   installed. `--check` exits 0: the three flagged packages are all reviewed in the script.
3. The 23 locked packages that uv does not install on macOS (the Linux CUDA stack, `triton`, and a few
   Windows or Linux-only helpers) cannot be read locally. `uv.lock` was compared with the 2026-10-07
   audit: the same 23 names at the same versions. Their licences are those PyPI gave on 2026-10-07.
   They were **not re-read today**.

The script's own summary line below says "Locked but not installed here: 0". That is only what
`--offline` makes it print. The real number is 23.

## Decisions for the owner

Nothing in this table is decided. The "Notes" column is the auditor's reading, not a decision.

| # | Item | Notes | Options | Owner's decision, who, date |
|---|---|---|---|---|
| 1 | **Sixteen NVIDIA CUDA packages** (`cuda-toolkit`, `nvidia-cublas`, `nvidia-cuda-cupti`, `nvidia-cuda-nvrtc`, `nvidia-cuda-runtime`, `nvidia-cudnn-cu13`, `nvidia-cufft`, `nvidia-cufile`, `nvidia-curand`, `nvidia-cusolver`, `nvidia-cusparse`, `nvidia-cusparselt-cu13`, `nvidia-nccl-cu13`, `nvidia-nvjitlink`, `nvidia-nvshmem-cu13`, `nvidia-nvtx`) | PyPI gives them a proprietary licence ("Other/Proprietary License", "LicenseRef-NVIDIA-Proprietary", "NVIDIA Proprietary Software") or none (5 of them: `cuda-toolkit`, `nvidia-cuda-runtime`, `nvidia-cudnn-cu13`, `nvidia-nccl-cu13`, `nvidia-nvshmem-cu13`). Their terms were not read here. In `uv.lock`, `torch` depends on `cuda-toolkit` and `triton` only when `sys_platform == 'linux'`, and these wheels are Linux builds. None is installed on this Mac, where the demo runs. Same as plan risk R21. | (a) Accept for the demo, because they are never installed on the demo machine, and record that. (b) Before any Linux GPU or hosted deployment, read NVIDIA's terms for each. (c) Or install CPU-only `torch` wheels on Linux, so none of them is pulled in. | |
| 2 | **MPL-2.0 packages** (`certifi`, `pathspec`, `tqdm`) | File-level copyleft. Each is used unmodified and not redistributed in changed form. `pathspec` is a dev-only dependency of `mypy`. Already reviewed in the script, with those reasons. | Confirm the review stands. No action unless modified copies are ever shipped. | |
| 3 | **`gpt-6-luna`** (OpenAI, hosted) | A service, not a component. OpenAI's API terms apply. They were not read for this audit. Data handling is summarised in `docs/privacy.md`. | Confirm that using OpenAI's API under its terms is acceptable for the demo. Before real users, read the API terms and decide on zero data retention (`docs/privacy.md`). | |
| 4 | **Marqo-FashionSigLIP** | Apache-2.0 according to the model card, as recorded on 2026-10-07. Not re-checked today. The licence of the weights it was built from, and of its training data, is not stated in anything held locally. | Accept the model card's licence for the demo. Before real users, read the model card again at the pinned revision and decide whether the training data matters. | |
| 5 | **Unused dependencies** `extruct` and `selectolax` | Not a licence problem: both are permissive (BSD, MIT). They are declared runtime dependencies, but no code imports either (the Shopify reader uses the standard `json` module). `extruct` also brings in `lxml`, `rdflib`, `mf2py`, `html5lib`, `w3lib`, `pyrdfa3`, `jstyleson`, `html-text` and `lxml_html_clean`, all permissive. `CLAUDE.md` says `extruct` is for Phase 19. | Keep them for Phase 19, or drop them from `pyproject.toml` to shrink the dependency list. | |

## The two models

| Model | Used for | Licence or terms | Pin | What was and was not verified |
|---|---|---|---|---|
| `gpt-6-luna` | Understanding the request (one call per search) | A hosted OpenAI service, used under OpenAI's API terms. There is no model file in the repository or on the machine. | `openai_model: gpt-6-luna` in `config/settings.yaml`. OpenAI lists no dated snapshot, so the versioned name is the pin. The settings accept that id by name and reject aliases such as `gpt-6-luna-latest`. | Verified: the id, and how the settings treat it. Not verified: OpenAI's terms, and whether this account has zero data retention. OpenAI can change the model behind the name (recorded limitation, ADR 0002). |
| Marqo-FashionSigLIP (`Marqo/marqo-fashionSigLIP`) | Image similarity, run locally on the shopper's photo and the stores' thumbnails | Apache-2.0, according to the model card as read by the Phase 3 spike on 2026-10-07 (`spikes/siglip/REPORT.md`; also noted in `src/vga/rank/image/model.py`). FashionSigLIP-2 is commercial-inquiry only and is not used. | Hugging Face revision `c56244cc94f92419e8369fa71efdaf403b124ce8` in `config/settings.yaml` (`siglip_revision`). The settings reject anything that is not a 40-character commit hash. | Verified: the revision in the settings equals the folder name of the snapshot in the local Hugging Face cache, which holds 8 files (config, tokenizer and the 813 MB `open_clip_model.safetensors`). The architecture in its config is SigLIP ViT-B/16 (`vit_base_patch16_siglip_224`, tokenizer `timm/ViT-B-16-SigLIP`). Not verified: the licence text itself. The download leaves out the model card and any LICENSE file, so it could not be re-read offline. The licences of the base weights and of the training data are not stated in anything local. |

## Entries that read oddly

- "BSD License", "MIT License" and "Apache Software License" are older, classifier-style names. They do
  not say which BSD variant. Every BSD variant is permissive.
- `pillow` is "MIT-CMU", a permissive HPND-style licence.
- `numpy` and `torch` are bundles of permissive licences (BSD, MIT, Apache, Zlib, CC0, BSL-1.0).
- `regex` is "Apache-2.0 AND CNRI-Python". `python-dateutil` and `sniffio` are dual-licensed, and both
  licences are permissive. `packaging` is "Apache-2.0 OR BSD-2-Clause".
- `pyrdfa3` is under the W3C licence, which is permissive.

## Python packages: the tool's output

Everything from here to the end of the "All packages" table was written by the script on 2026-10-08.
It lists the 122 installed packages. The licences it reads are the packages' own metadata.

## Summary

- Packages listed: **122** (21 direct, 101 transitive).
- Installed in this environment: 122. Locked but not installed here: 0 (not looked up: `--offline`).
- Flagged: **3**; reviewed and accepted: 3; **still needing review: 0**.

Status meanings: `ok` permissive; `weak copyleft / proprietary: review` and `unknown licence: review` need a person to decide; `copyleft: do not ship` must be replaced. A `reviewed` row has its reason recorded in `REVIEWED` in the script.

## Flagged

| Package | Version | Licence | Status | Source | Decision |
|---|---|---|---|---|---|
| certifi | 2026.7.22 | Mozilla Public License 2.0 (MPL 2.0) | weak copyleft / proprietary: review | installed | reviewed: MPL-2.0 is file-level copyleft; used unmodified, never edited or redistributed. |
| pathspec | 1.1.1 | Mozilla Public License 2.0 (MPL 2.0) | weak copyleft / proprietary: review | installed | reviewed: MPL-2.0 is file-level copyleft; a dev-only dependency of mypy, never shipped. |
| tqdm | 4.70.1 | MPL-2.0 AND MIT | weak copyleft / proprietary: review | installed | reviewed: MPL-2.0 AND MIT; used unmodified, so MPL's file-level terms are not triggered. |

## All packages

| Package | Version | Licence | Direct | Groups | Status | Source |
|---|---|---|---|---|---|---|
| altair | 6.3.0 | BSD License | no | - | ok | installed |
| annotated-types | 0.8.0 | MIT | no | - | ok | installed |
| anyio | 4.15.1 | MIT | no | - | ok | installed |
| ast_serialize | 0.12.1 | MIT | no | - | ok | installed |
| attrs | 26.1.0 | MIT | no | - | ok | installed |
| beautifulsoup4 | 4.15.0 | MIT License | no | - | ok | installed |
| boolean.py | 5.0 | BSD-2-Clause | no | - | ok | installed |
| CacheControl | 0.14.4 | Apache-2.0 | no | - | ok | installed |
| certifi | 2026.7.22 | Mozilla Public License 2.0 (MPL 2.0) | no | - | reviewed | installed |
| cfgv | 3.5.0 | MIT | no | - | ok | installed |
| charset-normalizer | 3.5.2 | MIT | no | - | ok | installed |
| click | 8.5.0 | BSD-3-Clause | no | - | ok | installed |
| cyclonedx-python-lib | 11.12.0 | Apache Software License | no | - | ok | installed |
| defusedxml | 0.7.1 | Python Software Foundation License | no | - | ok | installed |
| distlib | 0.4.3 | Python Software Foundation License | no | - | ok | installed |
| extruct | 0.18.0 | BSD License | yes | runtime | ok | installed |
| filelock | 4.0.12 | MIT | no | - | ok | installed |
| fsspec | 2026.9.0 | BSD-3-Clause | no | - | ok | installed |
| ftfy | 6.3.1 | Apache-2.0 | no | - | ok | installed |
| h11 | 0.16.0 | MIT License | no | - | ok | installed |
| hf-xet | 1.7.0 | Apache-2.0 | no | - | ok | installed |
| html-text | 0.7.1 | MIT | no | - | ok | installed |
| html5lib | 1.1 | MIT License | no | - | ok | installed |
| httpcore | 1.0.9 | BSD-3-Clause | no | - | ok | installed |
| httpcore2 | 2.13.1 | BSD-3-Clause | no | - | ok | installed |
| httptools | 0.8.0 | MIT | no | - | ok | installed |
| httpx | 0.28.1 | BSD License | yes | runtime | ok | installed |
| httpx2 | 2.13.1 | BSD-3-Clause | yes | dev | ok | installed |
| huggingface_hub | 2.1.1 | Apache Software License | no | - | ok | installed |
| identify | 2.6.20 | MIT | no | - | ok | installed |
| idna | 3.20 | BSD-3-Clause | no | - | ok | installed |
| iniconfig | 2.3.1 | MIT | no | - | ok | installed |
| itsdangerous | 2.2.0 | BSD License | no | - | ok | installed |
| Jinja2 | 3.1.6 | BSD License | no | - | ok | installed |
| jiter | 0.17.0 | MIT | no | - | ok | installed |
| jsonschema | 4.26.0 | MIT | no | - | ok | installed |
| jsonschema-specifications | 2025.9.1 | MIT | no | - | ok | installed |
| jstyleson | 0.0.2 | MIT License | no | - | ok | installed |
| librt | 0.16.0 | MIT | no | - | ok | installed |
| license-expression | 30.4.4 | Apache-2.0 | no | - | ok | installed |
| lxml | 6.1.3 | BSD-3-Clause | no | - | ok | installed |
| lxml_html_clean | 0.4.5 | BSD-3-Clause | no | - | ok | installed |
| markdown-it-py | 4.2.0 | MIT License | no | - | ok | installed |
| MarkupSafe | 3.0.4 | BSD-3-Clause | no | - | ok | installed |
| mdurl | 0.1.2 | MIT License | no | - | ok | installed |
| mf2py | 2.0.2 | MIT License | no | - | ok | installed |
| mpmath | 1.3.0 | BSD License | no | - | ok | installed |
| msgpack | 1.2.3 | Apache-2.0 | no | - | ok | installed |
| mypy | 2.4.0 | MIT | yes | dev | ok | installed |
| mypy_extensions | 1.1.0 | MIT | no | - | ok | installed |
| narwhals | 2.26.0 | MIT | no | - | ok | installed |
| networkx | 3.7 | BSD-3-Clause | no | - | ok | installed |
| nodeenv | 1.11.0 | BSD License | no | - | ok | installed |
| numpy | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | no | - | ok | installed |
| open_clip_torch | 3.3.0 | MIT License | yes | ml | ok | installed |
| openai | 3.26.0 | Apache-2.0 | yes | runtime | ok | installed |
| packageurl-python | 0.17.6 | MIT License | no | - | ok | installed |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | no | - | ok | installed |
| pandas | 3.0.6 | BSD License | no | - | ok | installed |
| pathspec | 1.1.1 | Mozilla Public License 2.0 (MPL 2.0) | no | - | reviewed | installed |
| pillow | 12.3.0 | MIT-CMU | yes | runtime | ok | installed |
| pip | 26.2.1 | MIT | no | - | ok | installed |
| pip_api | 0.0.35 | Apache Software License | no | - | ok | installed |
| pip_audit | 2.10.1 | Apache Software License | yes | dev | ok | installed |
| pip-licenses | 5.5.5 | MIT | yes | dev | ok | installed |
| pip-requirements-parser | 32.0.1 | MIT | no | - | ok | installed |
| platformdirs | 4.12.3 | MIT | no | - | ok | installed |
| pluggy | 1.6.0 | MIT License | no | - | ok | installed |
| pre_commit | 4.6.2 | MIT | yes | dev | ok | installed |
| prettytable | 3.18.0 | BSD-3-Clause | no | - | ok | installed |
| Protego | 0.7.0 | BSD-3-Clause | yes | runtime | ok | installed |
| protobuf | 7.36.2 | 3-Clause BSD License | no | - | ok | installed |
| py-serializable | 2.1.0 | Apache Software License | no | - | ok | installed |
| pyarrow | 25.0.1 | Apache-2.0 | no | - | ok | installed |
| pydantic | 2.13.5 | MIT | yes | runtime | ok | installed |
| pydantic_core | 2.46.5 | MIT | no | - | ok | installed |
| pydeck | 0.9.3 | Apache License 2.0 | no | - | ok | installed |
| Pygments | 2.21.0 | BSD-2-Clause | no | - | ok | installed |
| pyparsing | 3.3.3 | MIT | no | - | ok | installed |
| pyrdfa3 | 3.6.5 | W3C License | no | - | ok | installed |
| pytest | 9.1.1 | MIT | yes | dev | ok | installed |
| pytest-asyncio | 1.4.0 | Apache-2.0 | yes | dev | ok | installed |
| python-dateutil | 2.9.0.post0 | Apache Software License; BSD License | no | - | ok | installed |
| python-discovery | 1.6.1 | MIT License | no | - | ok | installed |
| python-multipart | 0.0.32 | Apache-2.0 | no | - | ok | installed |
| PyYAML | 6.0.3 | MIT License | yes | runtime | ok | installed |
| rdflib | 7.6.0 | BSD License | no | - | ok | installed |
| referencing | 0.37.0 | MIT | no | - | ok | installed |
| regex | 2026.9.29 | Apache-2.0 AND CNRI-Python | no | - | ok | installed |
| requests | 2.34.2 | Apache Software License | no | - | ok | installed |
| respx | 0.23.1 | BSD License | yes | dev | ok | installed |
| rich | 15.0.0 | MIT License | no | - | ok | installed |
| rpds-py | 2026.9.1 | MIT | no | - | ok | installed |
| ruff | 0.16.10 | MIT | yes | dev | ok | installed |
| safetensors | 0.8.0 | Apache Software License | no | - | ok | installed |
| selectolax | 1.0.0 | MIT | yes | runtime | ok | installed |
| setuptools | 84.0.0 | MIT | no | - | ok | installed |
| six | 1.17.0 | MIT License | no | - | ok | installed |
| sniffio | 1.3.1 | Apache Software License; MIT License | no | - | ok | installed |
| sortedcontainers | 2.4.0 | Apache Software License | no | - | ok | installed |
| soupsieve | 2.10 | MIT | no | - | ok | installed |
| starlette | 1.7.0 | BSD-3-Clause | no | - | ok | installed |
| streamlit | 1.65.0 | Apache-2.0 | yes | runtime | ok | installed |
| sympy | 1.14.0 | BSD License | no | - | ok | installed |
| timm | 1.0.30 | Apache Software License | no | - | ok | installed |
| toml | 0.10.2 | MIT License | no | - | ok | installed |
| tomli | 2.5.0 | MIT | no | - | ok | installed |
| tomli_w | 1.2.0 | MIT License | no | - | ok | installed |
| torch | 2.14.1 | Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT | yes | ml | ok | installed |
| torchvision | 0.29.1 | BSD | no | - | ok | installed |
| tqdm | 4.70.1 | MPL-2.0 AND MIT | no | - | reviewed | installed |
| truststore | 0.10.4 | MIT | no | - | ok | installed |
| types-PyYAML | 6.0.12.20260906 | Apache-2.0 | yes | dev | ok | installed |
| typing_extensions | 4.16.0 | PSF-2.0 | no | - | ok | installed |
| typing-inspection | 0.4.4 | MIT | no | - | ok | installed |
| urllib3 | 2.8.0 | MIT | no | - | ok | installed |
| uvicorn | 0.54.0 | BSD-3-Clause | no | - | ok | installed |
| virtualenv | 21.14.5 | MIT | no | - | ok | installed |
| w3lib | 2.5.0 | BSD-3-Clause | no | - | ok | installed |
| wcwidth | 0.9.2 | MIT License | no | - | ok | installed |
| webencodings | 0.6.1 | BSD License | no | - | ok | installed |
| websockets | 17.2 | BSD-3-Clause | no | - | ok | installed |

## Locked, not installed here (carried forward, not re-read today)

These 23 packages are in `uv.lock` but uv does not install them on macOS. The platform marker in
`uv.lock` says when each is needed. The licence is what PyPI's metadata gave on 2026-10-07, copied
from the audit of that day. The versions equal the ones in `uv.lock` today. **Not re-read today**,
because reading PyPI needs the network. Re-run the script without `--offline` on a networked machine
to refresh them.

| Package | Version | Licence on 2026-10-07 | Needed when (marker in `uv.lock`) | Status |
|---|---|---|---|---|
| colorama | 0.4.6 | BSD License | `sys_platform == 'win32'` | ok |
| cuda-bindings | 13.4.3 | Apache-2.0 | `torch`, `sys_platform == 'linux'` | ok |
| cuda-pathfinder | 1.8.3 | Apache-2.0 | `cuda-bindings` | ok |
| cuda-toolkit | 13.0.3.0 | UNKNOWN | `torch`, `sys_platform == 'linux'` | **unknown licence: decision 1** |
| httpx2-jsfetch | 1.0 | BSD-3-Clause | `httpx2`, `sys_platform == 'emscripten'` | ok |
| nvidia-cublas | 13.1.1.3 | LicenseRef-NVIDIA-Proprietary | `cuda-toolkit`, Linux | **proprietary: decision 1** |
| nvidia-cuda-cupti | 13.0.85 | Other/Proprietary License | `cuda-toolkit`, Linux | **proprietary: decision 1** |
| nvidia-cuda-nvrtc | 13.0.88 | Other/Proprietary License | `cuda-toolkit`, Linux | **proprietary: decision 1** |
| nvidia-cuda-runtime | 13.0.96 | UNKNOWN | `cuda-toolkit`, Linux | **unknown licence: decision 1** |
| nvidia-cudnn-cu13 | 9.24.0.43 | UNKNOWN | `torch`, Linux | **unknown licence: decision 1** |
| nvidia-cufft | 12.0.0.61 | Other/Proprietary License | `cuda-toolkit`, Linux | **proprietary: decision 1** |
| nvidia-cufile | 1.15.1.6 | Other/Proprietary License | `cuda-toolkit`, Linux | **proprietary: decision 1** |
| nvidia-curand | 10.4.0.35 | Other/Proprietary License | `cuda-toolkit`, Linux | **proprietary: decision 1** |
| nvidia-cusolver | 12.0.4.66 | Other/Proprietary License | `cuda-toolkit`, Linux | **proprietary: decision 1** |
| nvidia-cusparse | 12.6.3.3 | Other/Proprietary License | `cuda-toolkit`, Linux | **proprietary: decision 1** |
| nvidia-cusparselt-cu13 | 0.8.1 | NVIDIA Proprietary Software | `torch`, Linux | **proprietary: decision 1** |
| nvidia-nccl-cu13 | 2.30.7 | UNKNOWN | `torch`, Linux | **unknown licence: decision 1** |
| nvidia-nvjitlink | 13.4.92 | LicenseRef-NVIDIA-Proprietary | `cuda-toolkit`, Linux | **proprietary: decision 1** |
| nvidia-nvshmem-cu13 | 3.4.5 | UNKNOWN | `torch`, Linux | **unknown licence: decision 1** |
| nvidia-nvtx | 13.0.85 | Other/Proprietary License | `cuda-toolkit`, Linux | **proprietary: decision 1** |
| triton | 3.8.0 | MIT | `torch`, `sys_platform == 'linux'` | ok |
| tzdata | 2026.5 | Apache-2.0 | `sys_platform == 'emscripten'` or `'win32'` | ok |
| watchdog | 6.0.0 | Apache Software License | `streamlit`, `sys_platform != 'darwin'` | ok |

Sixteen of the 23 are flagged (the `cuda-toolkit` and 15 `nvidia-*` rows). Add the 3 weak-copyleft
packages above and the total is the 19 flagged on 2026-10-07. Nothing flagged has changed.
