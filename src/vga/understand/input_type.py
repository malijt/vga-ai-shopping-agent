"""The one place that decides what kind of request this is (plan A26).

The kind of request is a fact the code already knows, not something to ask the model:

- no photo: ``text``;
- a photo and typed text: ``photo_text``;
- a photo only, exactly one garment: ``product_photo``;
- a photo only, two or more garments: ``outfit_photo``.

It matters downstream. Only an ``outfit_photo`` skips the image comparison and gets a shorter list
per garment, so a model that calls a single gown worn by a person an "outfit" in one run and a
"product" in the next (it did, on 2026-10-08) would silently take both away from the shopper. The
model still writes an ``input_type`` (the answer schema asks for it); validation ignores it.

Both the validated model answer and the raw-text fallback use ``derive_input_type``, so the two
paths cannot drift apart.
"""

from vga.models import InputType


def derive_input_type(*, has_image: bool, has_text: bool, item_count: int) -> InputType:
    """The request kind for a request with or without a photo and typed text, and ``item_count``
    garments found in it. ``item_count`` only matters for a photo with no text."""
    if not has_image:
        return InputType.TEXT
    if has_text:
        return InputType.PHOTO_TEXT
    return InputType.OUTFIT_PHOTO if item_count > 1 else InputType.PRODUCT_PHOTO
