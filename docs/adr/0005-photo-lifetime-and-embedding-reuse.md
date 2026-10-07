# ADR 0005: The photo lives for one request; only its embedding is reused

- **Status:** Accepted. Decided in the approved implementation plan (v2, 2026-10-07), following BRD Rule 4 and assumption A8; recorded here.
- **Date:** 2026-10-07
- **Sources:** `docs/01-business-requirements.md` (Rule 4), `docs/02-prd.md` (R3), plan sections 7 (features 5.2.2, 8.1.3, 13.1.5, 14.2, 15.1.2), 8 (R6, R19), 11 (A8, A13), 12.3.

## Context

BRD Rule 4: do not keep uploaded photos after the request. The photo may show a person, possibly a face (plan R6), and it is sent to OpenAI for analysis.

Yet editing a chip must re-run the search (PRD R3), and a re-run should not need the shopper to upload the photo again, nor another call to OpenAI. Streamlit also keeps an uploaded file in memory for the whole session unless the uploader's widget key is changed (R19).

## Options considered

1. **Keep the photo in the session for re-runs.** Simple, but breaks Rule 4.
2. **Ask the shopper to upload the photo again for every re-run.** Respects Rule 4, but a poor experience for something chips are meant to make cheap.
3. **Keep only a derived vector (the query embedding) and the earlier understood result (chosen).** The embedding is what image scoring needs; the understood result is what chip edits are applied to.

## Decision

- **Photo bytes exist in memory for one request.** The pipeline checks the image server-side by its magic bytes (not its file extension), size and dimensions. Before sending to OpenAI the image is decoded, its EXIF data (including GPS) is removed, it is downscaled (long edge at most 1024 pixels), re-encoded as JPEG and sent as a base64 data URL, with request storage disabled where the API supports it. The bytes are **never written to disk** and **never logged**: the log redaction filter drops bytes, base64 and data URLs, and prompt logging (`VGA_LOG_PROMPTS`) covers text only (A13).
- **After the first run** the UI drops the bytes and rotates the uploader's widget key so Streamlit releases the uploaded file. What stays in session memory is the **query embedding** and the earlier understood result.
- **Chip re-runs** use them: a change to the price-range mix or budget alone re-shapes cached candidates (no store request, no OpenAI call); a change to an attribute searches again, still with no OpenAI call and with the stored embedding instead of the photo (A8).
- The embedding is excluded from the response's JSON and from `repr`, so dumps and logs carry nothing derived from the photo. Thumbnails of store products are held in memory only. The store-result cache holds no user data.
- **Proof, not promise:** an audit test runs a full request against faked boundaries while watching file writes and logs, and fails if any image bytes or base64 appear (feature 14.2.1). A privacy note (`docs/privacy.md`) records what leaves the machine.

## Consequences

- Rule 4 is met by construction and checked by a test, and chip edits stay fast and free of extra API calls.
- A new search with a different photo needs a new upload. The embedding of one photo cannot be used for another.
- Faces in outfit photos are **not** redacted before sending (a deliberate deviation, plan 12.3). The shopper sees a notice that the photo is sent to OpenAI and is not stored by us. Legal review (UAE PDPL / GDPR) is required before real users, and enabling zero data retention at the OpenAI organisation level is left to whoever runs the demo.
- The shopper sees these limits in plain words: what is AI-inferred, and that the photo goes to OpenAI.
