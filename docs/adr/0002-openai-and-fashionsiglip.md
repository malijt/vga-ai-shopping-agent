# ADR 0002: OpenAI for understanding, local Marqo-FashionSigLIP for image similarity

- **Status:** Accepted. Decided in the approved implementation plan (v2, 2026-10-07; "Approved stack decision: Option A"); recorded here.
- **Date:** 2026-10-07
- **Sources:** plan sections 1, 2, 3, 10, 12 and assumptions A10, risks R4, R5, R6, R7, R15; `docs/03-proposed-ideas.md` ("Options per step").

## Context

Two jobs need a model:

1. **Understand** a photo and/or text (English or Arabic) and return structured JSON: per item category, colour, style, material, gender, a budget, and 2-3 English search keyword variants (PRD R2).
2. **Image similarity**: rank product thumbnails against the shopper's photo when there is one (PRD R8).

OpenAI embeddings are text-only models, so they cannot embed images. The user already has an OpenAI key. The demo runs on a laptop or one GPU box (PRD).

## Options considered

For Understand:

1. **OpenAI vision with native structured outputs (chosen).** One call, one prompt, a Pydantic schema, a `gpt-5-mini`-class model.
2. Two calls (intent, then keyword expansion). Listed as an alternative in the proposed-ideas document; more calls for no stated need.

For image similarity:

1. **Local Marqo-FashionSigLIP through `open_clip` (chosen).** Apache-2.0, 203M parameters, trained for fashion, text and image in one space. Model card figures quoted in the plan: text-to-image recall 0.231, against 0.212 for base SigLIP and 0.163 for FashionCLIP 2.0.
2. **MODA FashionSigLIP** (a wrapper around Marqo). Skipped: the gains are self-reported and it needs 3 encodings per product.
3. **FashionSigLIP-2.** Commercial-inquiry licence only, so not used (BRD Rule 5).
4. **OpenAI embeddings.** Cannot embed images.
5. **A multimodal model looks at the photo plus the top thumbnails and picks the best** ("GPT-vision ranker"). Deferred; see the trigger below.

## Decision

- **OpenAI for every language and vision task**, called once per request through the OpenAI SDK with native structured outputs validated by Pydantic. The model is a **dated snapshot id pinned in `config/settings.yaml`**, never an alias; the exact snapshot is chosen from OpenAI's model docs at build time (assumption A10).
- **FashionSigLIP for image similarity**, run locally and **pinned to a Hugging Face revision hash**. It sits behind the small `ImageRanker` interface with two implementations, `siglip` and `off`; `off` is the fallback when the model fails or is slow.
- Torch and `open_clip` live in a separate optional dependency group (`ml`) so a plain install stays small.
- Python is pinned to 3.12 because PyTorch wheels may lag the system Python 3.14 (R5).

## Consequences

- The shopper's photo and text leave the machine for OpenAI (R6). Mitigations: a notice in the UI, EXIF stripped, image downscaled, request storage disabled where supported, nothing kept on our side (ADR 0005).
- OpenAI spend has no access control while the app is local (R7): a daily call cap and a per-request cap fail closed.
- The model snapshot, the prompt version and the FashionSigLIP revision are pinned together and logged together. Changing any of them requires re-running the evaluation set and adding a prompt-changelog entry (R15).
- FashionSigLIP on CPU may be too slow for 30-50 thumbnails (R4). Phase 3 measures it; the fallbacks are `mps`/`cuda`, fewer thumbnails, or `off`.
- Any failure of the image ranker degrades to text-and-price ranking, logged at warn level with the request id.
- **Revisit** with a GPT-vision ranker only if the Phase 3 spike shows SigLIP cannot score 40 thumbnails within 3 seconds on the demo machine (plan section 10).

## Update (2026-10-08): what the build changed

The decision stands. The details below changed or were settled. The text above is kept as written.

- **The model is `gpt-6-luna`**, chosen by the user on 2026-10-08. It replaces the planned
  `gpt-5-mini` snapshot, which never ran. OpenAI lists no dated snapshot for it, so the versioned
  name is the pin. `src/vga/settings.py` allows that one id by name (`UNDATED_SNAPSHOT_IDS`) and
  still rejects aliases such as `gpt-6-luna-latest`. This makes "pinned" weaker than the Decision
  intended: OpenAI can change what the model does behind the name. It is a recorded limitation. The
  Understand eval must be re-run from time to time, and before any change of prompt, model or effort.
- **Call settings.** Responses API, strict JSON schema, reasoning effort `low`, at most 3,000 output
  tokens, `store=false`, 15 seconds per call, at most 2 calls per request, a daily cap of 200 per
  process.
- **Prompt and eval.** The prompt is `understand-v2` (dresses became a fifth category). The live
  eval passed 24 of 24 on 2026-10-08, with a typical answer of 1.9 seconds and a worst of 3.0
  (`src/vga/understand/prompts/CHANGELOG.md`). One run labelled a single gown photo an outfit photo;
  that led to ADR 0009. The eval does not judge keyword quality.
- **FashionSigLIP.** Pinned to revision `c56244cc94f92419e8369fa71efdaf403b124ce8`. Because
  `open_clip`'s `hf-hub:` scheme cannot take a revision, the weights are fetched with
  `snapshot_download` and loaded from the local folder (`local-dir:`). The spike's verdict was GO as
  a low-weight signal: 40 thumbnails in 0.59 seconds on the Apple GPU and 1.12 seconds on the CPU.
  The image weight is 0.3. The model loads once, when the page opens.
- **Where it runs.** Only for a product photo and a photo with text. An outfit photo is not compared
  (ADR 0008).
- **Not built.** The GPT-vision ranker. Its trigger (SigLIP too slow) was not met.
