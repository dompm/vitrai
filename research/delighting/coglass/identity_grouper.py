#!/usr/bin/env python3
"""Iteration 044 -- SKU-token identity grouper for coglassworks.com.

Precondition for the coglass pair build, per report 041 SS2.3/SS6: a coglassworks
"product listing" is NOT guaranteed to be one physical piece of glass -- 43.6%
of the SKU-named-filename subset bundles more than one physical piece under a
single product page (adjacent remnants cut from the same shipment, listed and
photographed together). A naive "all images in this listing are one sheet"
pipeline would silently manufacture false cross-capture pairs between two
different pieces of glass (report 041's own worked example:
white-mottled-oceana-ra395 mixes RA395 (8.5x5in) and RA396 (5x6in)).

This module groups a listing's image filenames by the literal SKU token baked
into the filename, so a "pair" can only ever be assembled from photos of the
SAME physical piece.

Two filename conventions coexist on this store (report 041 SS1/SS2.2):
  - SKU-named:  "<SKU>.jpg", "<SKU>_2.jpg", "<SKU>_3.jpg", ...
                one SKU token per physical piece, trailing "_<n>" is a photo
                sequence number, not part of the identity.
  - camera-roll: "IMG_<n>.jpg" or "IMG_<n>_<uuid>.jpg" -- raw phone photos,
                the SKU is NOT recoverable from the filename at all.

Anything that isn't confidently SKU-named -- including camera-roll images,
and anything that superficially LOOKS SKU-shaped but doesn't match one of the
listing's own variant SKUs -- goes to the "unverified" bucket and must never
be used to assemble an automatic pair (report 041 SS6 step 2: skip, or add a
sticker-OCR / VLM same-piece check later; this module only does the cheap,
safe, filename-only half).

Grounded against three live listings fetched read-only via the documented
JSON API (coglassworks.com/products/<handle>.json, one GET each, matching the
scout's SS1 posture) on 2026-07-13:
  - white-mottled-oceana-ra395 : RA395.jpg, RA395_2.jpg, RA396.jpg, RA396_2.jpg
    variants RA395, RA396               -> the report's own multi-piece example
  - amber-white-wispy-rk950    : RK950.jpg, RK950_2.jpg
    variant RK950                       -> single-piece SKU-named example
  - light-amber-white-wispy-vintage-spectrum : 11x IMG_####[_uuid].jpg
    variants SP-24676141 etc. (no overlap with filenames at all)
                                         -> pure camera-roll / unverified example
"""
from __future__ import annotations

import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations

IMG_RE = re.compile(r"^img[_-]?\d+", re.IGNORECASE)

# Letters (1-4), optional dash, digits (2+), optional trailing "-<digits>"
# block (some barcode-style SKUs), then an optional "_<seq>" photo-index
# suffix. Anchored full-match on the filename stem (extension stripped).
SKU_TOKEN_RE = re.compile(
    r"^(?P<token>[A-Za-z]{1,4}-?\d{2,}(?:-\d+)?)(?:_(?P<seq>\d{1,3}))?$",
    re.IGNORECASE,
)


def _stem(filename: str) -> str:
    base = os.path.basename(filename)
    return re.sub(r"\.(jpe?g|png|webp|gif)$", "", base, flags=re.IGNORECASE)


@dataclass
class GroupResult:
    handle: str
    groups: dict = field(default_factory=dict)       # token -> [filenames]
    unverified: list = field(default_factory=list)    # filenames
    unmatched_variant_tokens: list = field(default_factory=list)  # SKU-shaped but no variant match

    @property
    def piece_count(self) -> int:
        return len(self.groups)

    @property
    def is_multi_piece(self) -> bool:
        return self.piece_count >= 2

    @property
    def convention(self) -> str:
        """sku_named | camera_roll | mixed | none"""
        has_groups = bool(self.groups)
        has_unverified = bool(self.unverified)
        if has_groups and not has_unverified:
            return "sku_named"
        if has_groups and has_unverified:
            return "mixed"
        if has_unverified and not has_groups:
            return "camera_roll"
        return "none"

    def pairs(self):
        """Yield (token, file_a, file_b) for every within-piece image pair.

        Only ever drawn from `groups` (filename-SKU-verified, and further
        variant-cross-checked when variant_skus was supplied) -- never from
        `unverified`. This is the load-bearing guarantee: a pair emitted here
        is physical-piece-verified, not merely listing-verified.
        """
        for token, files in self.groups.items():
            if len(files) < 2:
                continue
            for a, b in combinations(sorted(files), 2):
                yield token, a, b


def group_listing_images(handle: str, image_filenames, variant_skus=None) -> GroupResult:
    """Group one product listing's image filenames by physical-piece SKU token.

    Args:
        handle: product handle/slug, for bookkeeping only.
        image_filenames: iterable of filenames (or full src URLs -- basename
            is taken) as they appear in the listing's images[] array.
        variant_skus: optional iterable of this listing's own variants[].sku
            values. When provided, a filename-derived token is only trusted
            if it case-insensitively matches one of the listing's real
            variant SKUs -- protects against the regex matching something
            SKU-shaped that isn't actually this listing's identity token
            (e.g. a barcode fragment, or a coincidental camera filename).
            When omitted, the token is trusted on filename shape alone (used
            for isolated unit tests / early scoping where variant data isn't
            fetched).

    Returns:
        GroupResult with `.groups` (token -> verified same-piece image list),
        `.unverified` (everything that must NOT be auto-paired), and
        `.unmatched_variant_tokens` (diagnostic: SKU-shaped tokens that had
        no variant match, folded into unverified).
    """
    variant_set = {s.strip().upper() for s in (variant_skus or []) if s}
    groups = defaultdict(list)
    unverified = []
    unmatched = []

    for fname in image_filenames:
        stem = _stem(fname)
        if IMG_RE.match(stem):
            unverified.append(fname)
            continue
        m = SKU_TOKEN_RE.match(stem)
        if not m:
            unverified.append(fname)
            continue
        token = m.group("token").upper()
        if variant_set and token not in variant_set:
            unmatched.append(token)
            unverified.append(fname)
            continue
        groups[token].append(fname)

    return GroupResult(
        handle=handle,
        groups=dict(groups),
        unverified=unverified,
        unmatched_variant_tokens=unmatched,
    )


def classify_listing(result: GroupResult) -> str:
    """One-line bucket for census reporting, per report 041 SS2.2's table."""
    if result.convention == "sku_named" and result.is_multi_piece:
        return "multi_piece_verified"
    if result.convention == "sku_named" and result.piece_count == 1:
        return "single_piece_verified"
    if result.convention == "mixed":
        return "mixed_convention"
    if result.convention == "camera_roll":
        return "unverified_camera_roll"
    return "unverified_other"
