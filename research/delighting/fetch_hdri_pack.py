#!/usr/bin/env python3
"""fetch_hdri_pack.py -- one-time pre-fetch of the CC0 HDRI pack for
generate_synthetic.py --hdri-dir.

Report render-at-scale (docs/RENDER_AT_SCALE.md sec "HDRI strategy"): at 20k
samples the historical single downloaded HDRI (sunflowers) is a lighting-
diversity bottleneck, and a live polyhaven.org fetch at render time is a
single point of failure on marketplace nodes. Fetch this pack ONCE (bake it
into the node image / rsync it up with the job), then run the generator with
--hdri-dir pointing at it -- zero render-time network.

All assets are Poly Haven, license CC0 (https://polyhaven.com/license).
Slugs verified against https://dl.polyhaven.org (HTTP 200, 2026-07-10).
Curated for the sheet-photo use case: mostly natural-light environments a
person would actually photograph a glass sheet in -- overcast/soft outdoor
(the "held up against the sky" capture), sunny/golden outdoor, window-lit
interiors and workshops, plus a few studio setups. Deliberately excludes
night scenes and artificial-only club/bar lighting.

Usage:
    python3 fetch_hdri_pack.py --out hdri_pack           # 1k (default, ~2 MB each)
    python3 fetch_hdri_pack.py --out hdri_pack --res 2k
"""
import argparse
import os
import sys
import urllib.request

# (slug, category note) -- category from api.polyhaven.com asset tags
HDRI_PACK = [
    # -- outdoor, overcast / soft, low contrast (closest to the diffuse
    #    backlight of a sheet held against a bright sky) --
    ("belfast_open_field",           "outdoor overcast field, low contrast"),
    ("abandoned_slipway",            "outdoor overcast urban waterside"),
    ("ahornsteig",                   "outdoor overcast forest path"),
    ("autumn_crossing",              "outdoor overcast nature"),
    ("autumn_hockey",                "outdoor overcast field"),
    ("blaubeuren_outskirts",         "outdoor overcast village outskirts"),
    ("binnenalster",                 "outdoor overcast urban lakefront"),
    # -- outdoor, clear / sunny / partly cloudy (hard-light regime) --
    ("sunflowers",                   "outdoor sunny field -- the legacy default, kept for continuity"),
    ("autumn_field_puresky",         "outdoor clear pure sky, high contrast"),
    ("autumn_park",                  "outdoor clear park, high contrast"),
    ("abandoned_parking",            "outdoor partly cloudy, high contrast"),
    ("air_museum_playground",        "outdoor partly cloudy"),
    ("blau_river",                   "outdoor partly cloudy riverside"),
    ("bismarckturm_hillside",        "outdoor partly cloudy hillside, low contrast"),
    ("approaching_storm",            "outdoor dramatic partly-cloudy sky"),
    # -- outdoor, golden hour --
    ("belfast_sunset_puresky",       "outdoor sunset pure sky, warm low sun"),
    # -- indoor, natural window light (workshop/room capture regime) --
    ("artist_workshop",              "indoor workshop, midday window light, low contrast"),
    ("abandoned_greenhouse",         "indoor greenhouse, overcast diffuse -- glass-roof light"),
    ("abandoned_factory_canteen_01", "indoor hall, window light, low contrast"),
    ("abandoned_games_room_01",      "indoor room, midday window light"),
    ("aircraft_workshop_01",         "indoor hangar, natural light"),
    # -- studio (controlled softbox-like) --
    ("brown_photostudio_02",         "photo studio, soft even light"),
    ("blue_photo_studio",            "photo studio, cool soft light"),
]

BASE = "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/{res}/{slug}_{res}.hdr"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True, help="Directory to download the pack into")
    p.add_argument("--res", default="1k", choices=["1k", "2k", "4k"],
                   help="HDRI resolution (1k matches the generator's historical default)")
    args = p.parse_args()
    os.makedirs(args.out, exist_ok=True)

    failed = []
    for slug, note in HDRI_PACK:
        dest = os.path.join(args.out, f"{slug}_{args.res}.hdr")
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            print(f"  have  {slug} ({note})")
            continue
        url = BASE.format(res=args.res, slug=slug)
        print(f"  fetch {slug} ({note})")
        try:
            urllib.request.urlretrieve(url, dest)
        except Exception as e:  # noqa: BLE001 -- report and continue, retry pass below
            print(f"    FAILED: {e}")
            failed.append(slug)
            if os.path.exists(dest):
                os.remove(dest)

    if failed:
        print(f"\n{len(failed)} download(s) failed: {failed} -- re-run to retry.")
        sys.exit(1)
    print(f"\nPack complete: {len(HDRI_PACK)} HDRIs in {os.path.abspath(args.out)}")
    print("Use with: generate_synthetic.py ... --hdri-dir " + os.path.abspath(args.out))


if __name__ == "__main__":
    main()
