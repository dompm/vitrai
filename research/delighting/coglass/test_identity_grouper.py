#!/usr/bin/env python3
"""Unit tests for the iteration-044 SKU-token identity grouper.

Every fixture below is a real listing fetched read-only via coglassworks.com's
documented JSON API (one GET per listing, 2026-07-13) -- not synthesized --
so these tests are a precondition check against report 041's own claims, not
just internal self-consistency.

Run: python3 -m pytest research/delighting/coglass/test_identity_grouper.py -q
 or: python3 research/delighting/coglass/test_identity_grouper.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from identity_grouper import group_listing_images, classify_listing  # noqa: E402


def test_multi_piece_listing_report_worked_example():
    # Report 041 SS2.2's own headline example: two physical pieces (RA395,
    # RA396) bundled under one listing. Must split into two verified groups,
    # never one four-image group.
    handle = "white-mottled-oceana-ra395"
    images = ["RA395.jpg", "RA395_2.jpg", "RA396.jpg", "RA396_2.jpg"]
    variants = ["RA395", "RA396"]

    result = group_listing_images(handle, images, variant_skus=variants)

    assert result.piece_count == 2
    assert result.is_multi_piece
    assert set(result.groups.keys()) == {"RA395", "RA396"}
    assert sorted(result.groups["RA395"]) == ["RA395.jpg", "RA395_2.jpg"]
    assert sorted(result.groups["RA396"]) == ["RA396.jpg", "RA396_2.jpg"]
    assert result.unverified == []
    assert classify_listing(result) == "multi_piece_verified"

    pairs = list(result.pairs())
    assert len(pairs) == 2  # one pair per piece (2 photos -> C(2,2)=1 each)
    tokens_in_pairs = {p[0] for p in pairs}
    assert tokens_in_pairs == {"RA395", "RA396"}
    # No pair may cross pieces.
    for token, a, b in pairs:
        assert token in a and token in b


def test_single_piece_sku_named_listing():
    handle = "amber-white-wispy-rk950"
    images = ["RK950.jpg", "RK950_2.jpg"]
    variants = ["RK950"]

    result = group_listing_images(handle, images, variant_skus=variants)

    assert result.piece_count == 1
    assert not result.is_multi_piece
    assert result.groups == {"RK950": ["RK950.jpg", "RK950_2.jpg"]}
    assert result.unverified == []
    assert classify_listing(result) == "single_piece_verified"
    assert len(list(result.pairs())) == 1


def test_camera_roll_listing_is_fully_unverified():
    # 11 IMG_#### frames, variants are SP-prefixed SKUs with zero filename
    # overlap -- this is the "SKU not recoverable from filename at all" case
    # from report 041 SS1/SS2.2. None of these images may enter a pair group.
    handle = "light-amber-white-wispy-vintage-spectrum"
    images = [
        "IMG_8303_5567a1d5-b19f-4556-a6e8-32b3fc485d5f.jpg",
        "IMG_8304_1e1592e6-3a3b-444b-af44-4bbee7e661ad.jpg",
        "IMG_8299_e5739e85-0e57-413e-9c37-267587b7a5d1.jpg",
        "IMG_8300_84dc3324-2399-4385-a599-6dad7b7f4f3b.jpg",
        "IMG_8320_3bced1ab-de23-4422-b4e3-84c210f0efce.jpg",
        "IMG_8321_ac0c5694-79be-48af-bf48-ca27f23a8748.jpg",
        "IMG_8658.jpg",
        "IMG_8659_a7191402-2024-497e-ba30-0953691f0d38.jpg",
        "IMG_8660_51d6f637-efbc-412a-99e8-5766d117a234.jpg",
        "IMG_8483_73f64ce0-2373-4e42-8b92-09d57be7a483.jpg",
        "IMG_8482_20ebf823-35c2-424b-a442-983c38fef4d6.jpg",
    ]
    variants = ["SP-24676141", "SP-19236653", "SP-19269421", "SP-19203885", "SP-24643373"]

    result = group_listing_images(handle, images, variant_skus=variants)

    assert result.piece_count == 0
    assert not result.is_multi_piece
    assert result.groups == {}
    assert len(result.unverified) == 11
    assert classify_listing(result) == "unverified_camera_roll"
    assert list(result.pairs()) == []


def test_sku_shaped_but_no_variant_match_falls_to_unverified():
    # A filename that LOOKS SKU-shaped (letters+digits) but doesn't match any
    # of this listing's actual variant SKUs must not be trusted as an
    # identity token -- guards against coincidental filename collisions.
    handle = "made-up-listing"
    images = ["RA100.jpg", "RA100_2.jpg"]
    variants = ["RB200"]  # deliberately does not include RA100

    result = group_listing_images(handle, images, variant_skus=variants)

    assert result.groups == {}
    assert result.unverified == ["RA100.jpg", "RA100_2.jpg"]
    assert result.unmatched_variant_tokens == ["RA100", "RA100"]
    assert classify_listing(result) == "unverified_camera_roll"


def test_mixed_convention_listing():
    # Report 041 SS2.2: 1.7% of listings mix both conventions. The SKU-named
    # half should still group; the camera-roll half must not silently join
    # that group.
    handle = "mixed-example"
    images = ["RA700.jpg", "RA700_2.jpg", "IMG_9001.jpg"]
    variants = ["RA700"]

    result = group_listing_images(handle, images, variant_skus=variants)

    assert result.groups == {"RA700": ["RA700.jpg", "RA700_2.jpg"]}
    assert result.unverified == ["IMG_9001.jpg"]
    assert classify_listing(result) == "mixed_convention"


def test_no_variant_hint_trusts_filename_shape():
    # When variant SKUs aren't available (e.g. early scoping without full
    # product JSON), grouping falls back to filename-shape trust alone.
    handle = "no-variants-known"
    images = ["RK111.jpg", "RK111_2.jpg", "RK111_3.jpg"]

    result = group_listing_images(handle, images, variant_skus=None)

    assert result.groups == {"RK111": ["RK111.jpg", "RK111_2.jpg", "RK111_3.jpg"]}
    assert len(list(result.pairs())) == 3  # C(3,2)


def _run_all():
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    _run_all()
