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

## Update (2026-10-08): what the build changed

The decision stands and is now built and audited. The text above is kept as written.

- **The photo is redrawn, not only stripped.** The audit found that a JPEG comment, or a PNG text
  field named "comment", travelled to OpenAI with the picture. The outgoing JPEG is now built from
  the pixels alone, so no hidden field can go with it. Faces are still not blurred.
- **The page releases the photo.** After a search that used it, the uploader gets a new key and the
  file is dropped. A failed search keeps the photo so the shopper can retry. What the page keeps is
  the response, with the embedding and never the photo.
- **An outfit photo has no embedding at all.** It is not compared (ADR 0008), so nothing derived
  from it is kept. "Search again" with the embedding applies to a product photo and a photo with text.
- **How long the embedding lives.** In the re-run cache, which keeps the latest 32 requests until
  the process stops or a newer search pushes the oldest out. The 10-minute limit only decides whether
  the stored store answers can be reused. It deletes nothing.
- **A gender answer reuses what was fetched.** Answering "Who is this for?" filters the products
  already found. It makes no store request, no OpenAI call and no thumbnail download (ADR 0011).
- **Proof.** 135 tests run whole requests and look for the photo in files, logs, memory, outgoing
  requests and the answer. 23 planted leaks prove the audit can fail. `docs/privacy.md` says what
  leaves the machine.
- **Not verified.** Whether this OpenAI account has zero data retention. Whether an embedding can be
  turned back into a picture. What Streamlit keeps of an upload on a running page. The page's wording
  ("is not stored by us") says nothing about OpenAI's side and should be reworded once the retention
  question is decided (`docs/privacy.md`).

## Update (2026-10-08, the owner's decision): a small preview stays on the page

After using the page with a photo search, the owner asked that the reference photo stay visible with
the results until the page is refreshed or a new search starts. This changes BRD Rule 4 for one
thing. The text above is kept as written.

**What changed.** Option 1 above, "keep the photo in the session", was rejected. It is now adopted
for a **small preview only**, never for the upload:

- When a new search that used a photo finishes, the page draws the photo again from its pixels and
  keeps only that in the session (`app/photo_preview.py`, `app/state.py`). It is at most 512 pixels
  on the long side and a new JPEG: transparency is flattened onto white, and no EXIF, GPS position,
  colour profile, XMP or comment goes with it. It reuses the step that prepares the photo for OpenAI
  (`prepare_image`, now with an optional `max_edge`; the default and so the picture sent to OpenAI
  are unchanged).
- It is drawn in the block "What the AI saw in your photo", at a fixed small width, with a visible
  caption and a text alternative of its own.
- It stays through a search again (chips, the answer to "Who is this for?", the price-range mix). It
  is replaced when a new search with a photo finishes, removed when a new search without a photo
  finishes, removed when the page drops the results after an error, and gone on a refresh because
  the session is new. A search that fails changes nothing.
- If the photo cannot be drawn again, the search still succeeds, no preview is kept (an earlier one
  is removed too) and one warning is logged with the request number and the kind of error, never any
  part of the image.
- The page's two photo sentences now say so: "A small copy stays on this page until you refresh the
  page or start a new search", and that nothing is saved.

**What did not change.**

- The uploaded file is still released after its search (the uploader's key is rotated). The page
  holds no copy of the upload. A test checks the session for the uploaded bytes and for pieces of
  them.
- The pipeline, the response, the logs, the caches and the debug dump never hold the photo or the
  preview. Nothing is written to disk. Nothing is sent to OpenAI, a store or any other service: the
  preview is only shown to the shopper in their own browser.
- A search again still works from the stored embedding, never from the photo or the preview.
- The embedding rules, the lifetimes above and the OpenAI side are as before.

**Consequences.**

- The preview may show a person, a face or a child. It sits in the process's memory (and in
  Streamlit's in-memory picture store while it is drawn) for as long as the session shows it, and in
  the shopper's browser. The legal review that was already needed before real users (UAE PDPL, GDPR)
  now covers it too, and a hosted version would need a time limit and a fresh look
  (`docs/privacy.md`, "The preview that stays on the page").
- "The photo lives for one request" is no longer the whole truth, so the notice was reworded. The
  OpenAI-side wording is still open (zero data retention).
- Not verified: when Streamlit's in-memory store lets go of the picture after the page stops showing
  it (read from its source, not run on a live page).
- Checked by `tests/ui/test_photo_lifetime.py` and `tests/ui/test_photo_preview.py`.
