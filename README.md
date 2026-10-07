# VGA AI Shopping Agent

A one-day demo. A shopper gives a **photo, text (English or Arabic), or both**. One OpenAI call works out what they want, the app searches 4-6 GCC fashion stores' own search pages live, ranks the products, and shows the top 30 split into **Budget / Mid-range / Premium / Luxury**. Every result links to the store's own product page.

> **Status: Phase 1 (foundation and contracts).** What exists today is the project scaffold, the shared data contracts, settings, logging, test fakes, CI and the licence audit. The search pipeline, the store adapters and the Streamlit page arrive in later phases of the [implementation plan](docs/plans/2026-10-07-vga-ai-shopping-agent-implementation-plan.md). Commands for features that do not exist yet are marked *(later phase)* below.

Read in this order: [business requirements](docs/01-business-requirements.md) (why), [PRD](docs/02-prd.md) (what), the plan (how). Engineering rules are in [CLAUDE.md](CLAUDE.md).

## Quick start (from a fresh clone to green tests)

You need `git` and [`uv`](https://docs.astral.sh/uv/getting-started/installation/) (any recent version). You do **not** need Python installed: `uv` fetches Python 3.12, which this project pins (the system Python may be too new for PyTorch wheels).

```bash
git clone <this repository> && cd vga-ai-shopping-agent
uv sync                      # Python 3.12, runtime + dev dependencies (a few minutes the first time)
uv run pytest                # all tests; no network, no API key needed
```

Expected: every test passes. Then the other gates, which CI also runs:

```bash
uv run ruff check            # lint, including security rules
uv run mypy src              # types
uv run pip-audit             # known-vulnerability scan of the installed dependencies
uv run python scripts/licence_audit.py   # dependency licences -> docs/licences.md
```

Optional, once: `cp .env.example .env` and fill in what you need (see below), and `uv run pre-commit install` to run ruff and the secret scan before each commit.

## Commands

| Command | What it does |
|---|---|
| `uv sync` | Install runtime and dev dependencies (not the `ml` group) |
| `uv sync --group ml` | Also install `torch` and `open_clip` for local image similarity, the default image ranker. About 1 GB; without it (and the downloaded weights) image ranking falls back to `off` with a warning |
| `uv run pytest` | Unit, contract and integration tests. Tests marked `live` are skipped |
| `uv run pytest -m live` | Live store / OpenAI smoke tests. Needs keys, makes real requests, never runs in CI *(later phases add them)* |
| `uv run ruff check` / `uv run mypy src` | Lint / types |
| `uv run streamlit run app/main.py` | The demo UI; `VGA_UI_FIXTURE=1` runs it from a sample response with no backend *(later phase)* |
| `uv run python -m vga.search --text "..."` | Run the pipeline from the command line, prints JSON *(later phase)* |
| `uv run python -m eval.harness --replay` | Acceptance run from a recording, no network *(later phase)* |

## Environment variables

Copy `.env.example` to `.env` (it is gitignored). Values from the real environment win over `.env`, which wins over `config/settings.yaml`. Never commit a real key.

| Variable | Meaning | Default |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI key for the Understand step. Needed for real searches only. Read by the OpenAI client, never stored in settings or logs | none |
| `OPENAI_MODEL` | Dated model snapshot id (ends in `-YYYY-MM-DD`). Aliases are rejected | `gpt-5-mini-2025-08-07` (set in `config/settings.yaml`) |
| `VGA_USER_AGENT` | Honest, identifying User-Agent sent to stores; browser strings are rejected | `vga-shopping-agent-demo/0.1 (store search demo)` |
| `VGA_IMAGE_RANKER` | `siglip` (local model; needs the `ml` group and the downloaded weights, else it falls back to `off` with a warning) or `off` to disable image ranking. Commented out in `.env.example` so a copied `.env` does not override the YAML | `siglip` (set in `config/settings.yaml`) |
| `VGA_LOG_DIR` | Directory for JSON-lines logs | `logs` |
| `VGA_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING` or `ERROR` | `INFO` |
| `VGA_LOG_PROMPTS` | `1` also logs the text prompt and parsed result, never the photo | `0` |
| `VGA_DEBUG_DUMP` | `1` writes each request's ranked candidates to a JSONL file | `0` |
| `VGA_SETTINGS_PATH` | Path to a settings file | `config/settings.yaml` |
| `VGA_DAILY_LLM_CALL_CAP` | Daily cap on OpenAI calls; when reached, no more calls are made | `200` |
| `VGA_UI_FIXTURE` | `1` runs the UI from the bundled sample response | `0` |

## Settings

`config/settings.yaml` holds the tunable values: `country`, `stores`, `results` (30), `max_per_store` (6), `max_image_bytes` (8,000,000, the largest photo accepted), `timeout_s` (6), `rps_per_store` (1), `max_response_bytes` (2,000,000, the HTTP response size cap), `tier_mix` (25/25/25/25), `ranking_weights`, `min_match_score`, and the model settings. It is validated on load, and a bad value stops start-up with a message naming the field. For example, `tier_mix` must sum to 100.

The image model settings come from the FashionSigLIP spike (`spikes/siglip/REPORT.md`): `image_ranker` is `siglip` and `siglip_revision` is the measured Hugging Face commit. `siglip_cos_lo` (0.45) and `siglip_cos_hi` (0.90) turn an image cosine into a 0-1 score, `clip((cos - lo) / (hi - lo), 0, 1)`, so `lo` must be below `hi`. The code default for `image_ranker` stays `off`, and `siglip_revision` is unset there; only the shipped YAML turns the model on.

`openai_model` is pinned to the dated snapshot `gpt-5-mini-2025-08-07` (from OpenAI's model page for gpt-5-mini); the code default is unset. That id has not yet been exercised against the real API from this project. Pinned versions must not change under us, so aliases such as `gpt-5-mini` or `main` are rejected. Changing `openai_model` means re-running the Understand eval (`uv run pytest -m live tests/understand`) and adding an entry to `src/vga/understand/prompts/CHANGELOG.md`; changing `siglip_revision` also means re-running the spike's quality check.

Stores are one YAML file each in `config/stores/` and are **off unless `enabled: true`**. A store file may override `rps`, `timeout_s` and `max_response_bytes` for that store, and may set `max_variants` (1 to 3) to send fewer of the keyword variants to it; leaving a field out uses the global setting (or all variants). A store file may also list `genders` (for example `[women]`, never empty) when the store sells for one gender only: a request for another gender is not sent to it. A store that lists `unisex` sells for everyone, and a store without `genders` is treated as selling for all.

## How the code is organised

```
src/vga/models.py, interfaces.py, errors.py   shared contracts (frozen: change only in their own PR)
src/vga/settings.py, log.py                   validated settings; JSON logs with request id and redaction
src/vga/{understand,fetch,stores,rank,tiers,pipeline}/   one package per later phase
app/                  Streamlit UI            eval/harness/      acceptance harness
config/               settings.yaml, stores/  docs/adr/          decision records
tests/fakes.py        shared fakes for the three boundaries (store HTTP, OpenAI, image model) and the clock
tests/factories.py    builders for valid contract objects
tests/foundation/     contract suites that a fake and its real implementation must both pass
```

Tests fake only the boundaries, using `tests/fakes.py`, and never reach real stores or OpenAI unless marked `live`.

## Known limitations of the AI features

These describe the design; the features themselves land in later phases.

- **The model can misread a photo or a request.** Colour, style and category are guesses, shown as editable chips labelled "Detected by AI". Matching is AI-assisted and can be wrong.
- **Gender inferred from a photo is shown, never applied,** until the shopper confirms it. Gender stated in the text is applied.
- **Arabic is translated to English keywords** for store search; translation quality varies. The translated chip can be corrected.
- **Body size is never guessed** from a photo.
- **The photo is sent to OpenAI** for analysis. EXIF data is stripped and the image is downscaled first, and the app keeps nothing after the request. Faces in outfit photos are **not** redacted. Review the privacy position (UAE PDPL / GDPR) before real users.
- **Store coverage is the biggest risk.** A store that blocks an honest client is dropped, never bypassed, so results may come from fewer stores. If no luxury-leaning store works, "Luxury" only means "most expensive found".
- **Price ranges are relative.** Their borders are quartiles of the prices found for this search, not fixed market bands.
- **This is a demo.** Each store's terms of use must be checked before any real use.

## Continuous integration and repository settings

`.github/workflows/ci.yml` runs three jobs on every pull request and on pushes to `main` and `develop`: `test` (ruff, mypy, pytest without live tests), `pip-audit` (every locked dependency, including the `ml` group) and `gitleaks` (secret scan of the full history).

**One-time manual step for the repository owner:** in GitHub, protect `main` (Settings, Branches) and require the status checks `test`, `pip-audit` and `gitleaks` plus a review before merging. This cannot be done from the code.

## Licences

Only components with commercial-friendly licences are allowed. After adding a dependency, run `uv run python scripts/licence_audit.py`; it rewrites [docs/licences.md](docs/licences.md) and flags copyleft, proprietary and unknown licences for a decision.
