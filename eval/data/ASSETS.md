# Image assets for the acceptance and edge-case sets

Every image that `queries.yaml` and `edge_cases.yaml` point to is listed here. Paths are relative
to `eval/data/assets/`.

## Action for you: supply 5 photos

Five real photos are needed (3 single-product photos, 2 outfit photos). They are not generated or
downloaded for you, because a stand-in would make the acceptance result meaningless. Save them
**with exactly these names** in `eval/data/assets/private/`, as JPEG (`.jpg`; convert a PNG or
HEIC first). That folder is gitignored, so they cannot be committed by mistake.

| Filename | What it should show | Who supplies | Licence requirement | Status | Used by |
|---|---|---|---|---|---|
| `private/product_jacket.jpg` | One jacket (bomber, trucker, field or similar) on a plain background, on a hanger or laid flat, whole garment in frame. **Not dark brown** (q09 asks for dark brown). Black, navy, olive or tan is fine. | User | Your own photo of an item you own, or an image whose licence allows commercial use (CC0 or public domain). No stock images with a restrictive licence. | needed from user | q01, q09 |
| `private/product_sneakers.jpg` | One pair of low-top sneakers, side view, plain background, whole shoe in frame. | User | Same as above. | needed from user | q02 |
| `private/product_jeans.jpg` | One pair of jeans or trousers laid flat or on a hanger, plain solid colour (for example mid-blue jeans), whole garment in frame. | User | Same as above. | needed from user | q03, q10 |
| `private/outfit_casual.jpg` | Mirror selfie or full-body photo of one person wearing a **top, bottoms and shoes**, all clearly visible (3 garments). No bag or accessory needed. | User | Your own photo, or a photo where the person pictured agrees to it being used for testing. | needed from user | q04 |
| `private/outfit_layered.jpg` | Full-body photo of one person wearing **outerwear over a top, plus bottoms and shoes**, all clearly visible (4 garments, the most the app handles). A different outfit from `outfit_casual.jpg`. | User | Same as above. | needed from user | q05 |

Photo guidelines for all five:

- Long edge at least 800 px; sharp and well lit; JPEG under 5 MB.
- One subject only. The outfit photos may show a face; that is why they stay in `private/`.
- Anyone pictured must agree that the photo is sent to OpenAI during test runs. The app tells
  shoppers the same thing, and the photo is not kept after a request.
- Remove location data (EXIF GPS) if you can. The app strips EXIF before sending, but a clean file
  is safer on your disk.
- Do not supply dresses, bags or accessories. They are out of scope.

Check before the first acceptance run:

```bash
ls eval/data/assets/private/    # expect the 5 filenames above (and .gitignore)
git status --short              # must show nothing under eval/data/assets/private/
```

## Already present: synthetic images for edge cases

Drawn with Pillow from scratch (flat colours, simple shapes and rendered text). They show no real
person and need no licence. They are committed. Regenerate with
`uv run eval/data/make_synthetic_assets.py`.

| Filename | What it shows | Who supplies | Licence requirement | Status | Used by |
|---|---|---|---|---|---|
| `edge_injection_in_photo.png` | A framed sign of printed instructions ("IGNORE PREVIOUS INSTRUCTIONS ...") and no garment. | `make_synthetic_assets.py` | None (generated; no third-party content) | present (synthetic) | e05, e06 |
| `edge_non_fashion.png` | A cartoon landscape (sun, hills, house, tree). No clothing, no text. | `make_synthetic_assets.py` | None (generated; no third-party content) | present (synthetic) | e07 |

## Rules for this folder

- Never commit a real photo of a person or a photo you do not have the right to use.
  `private/.gitignore` ignores everything in `private/` except itself.
- `queries.yaml` and `edge_cases.yaml` are frozen before tuning. If you cannot supply a photo that
  matches a description, say so and agree a replacement before the first acceptance run, not after.
- The Phase 11 query loader reports a missing image path as an error, so the acceptance run cannot
  start until all 5 files exist.
