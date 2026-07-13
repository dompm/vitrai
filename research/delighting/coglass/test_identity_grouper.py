#!/usr/bin/env python3
"""Unit tests for the iteration-044 SKU-token identity grouper.

Every non-synthetic fixture below is a real listing fetched read-only via
coglassworks.com's documented JSON API or taken verbatim from the 044 census
(2026-07-13) -- so these tests are a precondition check against report 041's
own claims, not just internal self-consistency.

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
    assert result.tiers == {"RA395": "variant", "RA396": "variant"}
    assert result.unverified == []
    assert classify_listing(result) == "multi_piece_sku_named"

    pairs = list(result.pairs())
    assert len(pairs) == 2  # one pair per piece (2 photos -> C(2,2)=1 each)
    tokens_in_pairs = {p[0] for p in pairs}
    assert tokens_in_pairs == {"RA395", "RA396"}
    # No pair may cross pieces.
    for token, tier, a, b in pairs:
        assert token in a and token in b
        assert tier == "variant"


def test_single_piece_sku_named_listing():
    handle = "amber-white-wispy-rk950"
    images = ["RK950.jpg", "RK950_2.jpg"]
    variants = ["RK950"]

    result = group_listing_images(handle, images, variant_skus=variants)

    assert result.piece_count == 1
    assert not result.is_multi_piece
    assert result.groups == {"RK950": ["RK950.jpg", "RK950_2.jpg"]}
    assert result.tiers["RK950"] == "variant"
    assert result.unverified == []
    assert classify_listing(result) == "single_piece_sku_named"
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


def test_barcode_style_variant_sku_falls_back_to_handle_tier():
    # Census reality (2024+ listings): variants[].sku is a size+barcode
    # string like "10x8in (YG-56938541)" -- the piece token RA784 appears
    # only in the filenames and the handle. Must still group, at tier
    # "handle", NOT be discarded.
    handle = "blue-clear-stipple-youghiogheny-ra784"
    images = ["RA784.jpg", "RA784_2.jpg"]
    variants = ["10x8in (YG-56938541)"]

    result = group_listing_images(handle, images, variant_skus=variants)

    assert result.groups == {"RA784": ["RA784.jpg", "RA784_2.jpg"]}
    assert result.tiers["RA784"] == "handle"
    assert len(list(result.pairs())) == 1


def test_prefix_sibling_tier_for_unnamed_second_piece():
    # Census reality: multi-piece listing whose handle names only the first
    # piece (ra777); the second piece RA778 appears only in filenames.
    # It must group separately at tier "prefix_sibling" -- and the two
    # pieces must never pair with each other.
    handle = "blue-vintage-iridescent-spectrum-ra777"
    images = ["RA777.jpg", "RA777_2.jpg", "RA778.jpg", "RA778_2.jpg"]
    variants = ["9x2.5in (SP-56315949)", "12.5x3in (SP-56348717)"]

    result = group_listing_images(handle, images, variant_skus=variants)

    assert set(result.groups) == {"RA777", "RA778"}
    assert result.tiers["RA777"] == "handle"
    assert result.tiers["RA778"] == "prefix_sibling"
    for token, tier, a, b in result.pairs():
        assert token in a and token in b


def test_handle_prefix_tier_for_truncated_handle():
    # Census reality: handle tail "rk1" is a truncation of the actual piece
    # tokens RK127..RK131 (five pieces of Lamberts flash under one listing).
    handle = "light-green-gradient-on-clear-lamberts-flash-glass-rk1"
    images = ["RK127.jpg", "RK127_1.jpg", "RK128.jpg", "RK128_1.jpg"]
    variants = []

    result = group_listing_images(handle, images, variant_skus=variants)

    assert set(result.groups) == {"RK127", "RK128"}
    assert result.tiers["RK127"] == "handle_prefix"
    assert result.tiers["RK128"] == "handle_prefix"


def test_shape_only_tier_when_nothing_corroborates():
    # Census reality: J-series tokens under a handle that carries no J token
    # at all. Still grouped (the _n suffix convention holds) but flagged as
    # the weakest tier so downstream can filter or hand-check.
    handle = "light-violet-iridescent-wispy-swirl-wissmach"
    images = ["J25_2.jpg", "J25_3.jpg", "J56_2.jpg", "J56_3.jpg"]
    variants = ["WM-93169453"]

    result = group_listing_images(handle, images, variant_skus=variants)

    assert set(result.groups) == {"J25", "J56"}
    assert result.tiers == {"J25": "shape_only", "J56": "shape_only"}
    # Two distinct pieces: pairs stay within token.
    assert len(list(result.pairs())) == 2


def test_variant_word_boundary_no_substring_false_positive():
    # Token A65 must NOT match inside barcode RA657 (substring trap).
    handle = "some-listing"
    images = ["A65.jpg", "A65_1.jpg"]
    variants = ["RA657"]

    result = group_listing_images(handle, images, variant_skus=variants)

    assert result.tiers["A65"] == "shape_only"  # not "variant"


def test_mixed_convention_listing():
    # Report 041 SS2.2: 1.7% of listings mix both conventions. The SKU-named
    # half should still group; the camera-roll half must not silently join
    # that group.
    handle = "mixed-example-ra700"
    images = ["RA700.jpg", "RA700_2.jpg", "IMG_9001.jpg"]
    variants = ["RA700"]

    result = group_listing_images(handle, images, variant_skus=variants)

    assert result.groups == {"RA700": ["RA700.jpg", "RA700_2.jpg"]}
    assert result.unverified == ["IMG_9001.jpg"]
    assert classify_listing(result) == "mixed_convention"


def test_full_cdn_urls_with_cache_buster_query():
    # The collection JSON's images[].src is a full Shopify CDN URL with a
    # ?v=<epoch> cache buster (live example from the 044 census). The grouper
    # must see through both the path and the query string. Regression test:
    # the first census run silently classified all 1,361 listings as
    # camera-roll because of exactly this.
    handle = "amber-white-wispy-rk950"
    images = [
        "https://cdn.shopify.com/s/files/1/0723/2533/3293/files/RK950.jpg?v=1783407096",
        "https://cdn.shopify.com/s/files/1/0723/2533/3293/files/RK950_2.jpg?v=1783407097",
    ]
    result = group_listing_images(handle, images, variant_skus=["RK950"])
    assert result.piece_count == 1
    assert sorted(result.groups) == ["RK950"]
    assert len(result.groups["RK950"]) == 2
    assert result.unverified == []


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
