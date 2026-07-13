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

Camera-roll images (and anything else without a SKU-shaped stem) go to the
"unverified" bucket and are never auto-paired (report 041 SS6 step 2: skip, or
add a sticker-OCR / VLM same-piece check later; this module only does the
cheap, safe, filename-only half).

Verification tiers (measured on the full 1,361-product census, 2026-07-13):
the naive idea "cross-check the filename token against variants[].sku" turned
out to be too strict on real data -- for most 2024+ listings the variant sku
field holds a size+barcode string like "10x8in (YG-56938541)" while the piece
token (RA784) lives only in the filename and the product handle. So instead of
dropping unmatched tokens, every SKU-shaped token is kept and tagged with how
strongly it is corroborated:

  variant        token matches one of the listing's variants[].sku values
                 (word-boundary match inside the sku string)
  handle         token appears verbatim in the product handle
                 (e.g. white-mottled-oceana-ra395 -> RA395)
  handle_prefix  the handle's trailing SKU-shaped segment is a strict prefix
                 of the token (e.g. ...-lamberts-flash-glass-rk1 -> RK127)
  prefix_sibling same alphabetic prefix as a variant/handle-corroborated
                 token in the SAME listing (multi-piece listings usually name
                 only the first piece in the handle; siblings are sequential
                 intake codes, e.g. RA777 in handle, RA778 only in filenames)
  shape_only     SKU-shaped stem with no corroboration beyond its shape

Downstream consumers choose their own floor; the 044 hand-check measures
precision per tier so that choice is data-driven, not vibes.
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

# Trailing SKU-shaped segment of a product handle, e.g. "-ra395" or "-rk1".
HANDLE_TAIL_RE = re.compile(r"-([A-Za-z]{1,4}\d{1,})$")


def _stem(filename: str) -> str:
    # Accept full CDN URLs: strip query string (Shopify appends ?v=<cache
    # buster> to every images[].src) and fragment before taking the basename.
    base = os.path.basename(filename.split("?")[0].split("#")[0])
    return re.sub(r"\.(jpe?g|png|webp|gif)$", "", base, flags=re.IGNORECASE)


def _alpha_prefix(token: str) -> str:
    m = re.match(r"^[A-Za-z]+", token)
    return m.group(0) if m else ""


@dataclass
class GroupResult:
    handle: str
    groups: dict = field(default_factory=dict)        # token -> [filenames]
    tiers: dict = field(default_factory=dict)         # token -> verification tier
    unverified: list = field(default_factory=list)    # filenames (camera-roll etc)

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
        """Yield (token, tier, file_a, file_b) for every within-piece pair.

        Only ever drawn from `groups` (same filename SKU token) -- never from
        `unverified`. This is the load-bearing guarantee: a pair emitted here
        is physical-piece-verified at its stated tier, not merely
        listing-verified.
        """
        for token, files in self.groups.items():
            if len(files) < 2:
                continue
            for a, b in combinations(sorted(files), 2):
                yield token, self.tiers[token], a, b


def group_listing_images(handle: str, image_filenames, variant_skus=None) -> GroupResult:
    """Group one product listing's image filenames by physical-piece SKU token.

    Args:
        handle: product handle/slug; also used for handle-based tier
            corroboration.
        image_filenames: iterable of filenames or full src URLs (basename is
            taken, query strings stripped) as they appear in images[].
        variant_skus: optional iterable of this listing's variants[].sku
            values, used for tier corroboration (see module docstring).

    Returns:
        GroupResult with `.groups` (token -> same-piece image list), `.tiers`
        (token -> verification tier), and `.unverified` (everything that must
        NOT be auto-paired: camera-roll filenames and non-SKU-shaped stems).
    """
    sku_blob = " ".join(s.strip().upper() for s in (variant_skus or []) if s)
    handle_squash = re.sub(r"[^A-Za-z0-9]", "", handle or "").upper()
    m_tail = HANDLE_TAIL_RE.search(handle or "")
    handle_tail = m_tail.group(1).upper() if m_tail else None

    groups = defaultdict(list)
    unverified = []

    for fname in image_filenames:
        stem = _stem(fname)
        if IMG_RE.match(stem):
            unverified.append(fname)
            continue
        m = SKU_TOKEN_RE.match(stem)
        if not m:
            unverified.append(fname)
            continue
        groups[m.group("token").upper()].append(fname)

    # Tier assignment (two passes: direct corroboration, then siblings).
    tiers = {}
    for token in groups:
        if sku_blob and re.search(r"(?<![A-Z0-9])" + re.escape(token) + r"(?![A-Z0-9])", sku_blob):
            tiers[token] = "variant"
        elif token.replace("-", "") in handle_squash:
            tiers[token] = "handle"
        elif handle_tail and token.startswith(handle_tail) and token != handle_tail:
            tiers[token] = "handle_prefix"
    anchored_prefixes = {_alpha_prefix(t) for t in tiers}
    for token in groups:
        if token in tiers:
            continue
        if _alpha_prefix(token) in anchored_prefixes:
            tiers[token] = "prefix_sibling"
        else:
            tiers[token] = "shape_only"

    return GroupResult(
        handle=handle,
        groups=dict(groups),
        tiers=tiers,
        unverified=unverified,
    )


def classify_listing(result: GroupResult) -> str:
    """One-line bucket for census reporting, per report 041 SS2.2's table."""
    if result.convention == "sku_named" and result.is_multi_piece:
        return "multi_piece_sku_named"
    if result.convention == "sku_named" and result.piece_count == 1:
        return "single_piece_sku_named"
    if result.convention == "mixed":
        return "mixed_convention"
    if result.convention == "camera_roll":
        return "unverified_camera_roll"
    return "unverified_other"
