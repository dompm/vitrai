#!/usr/bin/env python3
"""Audit Bullseye catalog images against labeled cold/fired technical photos.

This is deliberately read-only with respect to the swatch library. It joins:

* Bullseye's Shopify product/gallery JSON;
* Bullseye's WordPress "About Our Glass" posts, whose figures are captioned
  "Unfired Sheet" and "Fired Tile"; and
* Vitrai's registry plus canonical clean manifest.

The result is a weakly paired, manufacturer-labeled material-state dataset and
an estimate of how often the current first-image convention selects fired color
for a product that stained-glass artists normally encounter cold.
"""

from __future__ import annotations

import argparse
import io
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import numpy as np
import requests
from bs4 import BeautifulSoup, Tag
from PIL import Image, ImageDraw, ImageFont, ImageOps


SHOP_ROOT = "https://shop.bullseyeglass.com"
TECH_ROOT = "https://www.bullseyeglass.com"
USER_AGENT = "Vitrai material-state research audit/1.0"
SHEET_SIZE_TOKENS = ("1010", "HALF", "FULL")
FORMULA_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
GAUGE_RE = re.compile(r"-(0030|0050)(?:-|\b)", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    here = Path(__file__).resolve().parent.parent
    workspace = here.parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        type=Path,
        default=workspace / "frontend/public/assets/glass_swatch_registry.json",
        help="Vitrai swatch registry (the ignored main-workspace copy is fine)",
    )
    parser.add_argument(
        "--clean-manifest",
        type=Path,
        default=here / "results/corpus/clean_manifest.json",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=here / "results/cold_state_audit_032",
    )
    parser.add_argument(
        "--max-eval",
        type=int,
        default=0,
        help="Limit image-based comparisons after joins (0 means all)",
    )
    parser.add_argument(
        "--max-thickness-eval",
        type=int,
        default=0,
        help="Limit 2 mm/3 mm cold-sheet comparisons (0 means all)",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args()


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    adapter = requests.adapters.HTTPAdapter(max_retries=3)
    session.mount("https://", adapter)
    return session


def fetch_json(session: requests.Session, url: str, timeout: float) -> Any:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def fetch_shop_products(
    session: requests.Session,
    timeout: float,
    collection: str | None = None,
) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    base = f"{SHOP_ROOT}/products.json"
    if collection:
        base = f"{SHOP_ROOT}/collections/{collection}/products.json"
    for page in range(1, 25):
        payload = fetch_json(
            session,
            f"{base}?page={page}&limit=250",
            timeout,
        )
        batch = payload.get("products", [])
        if not batch:
            break
        products.extend(batch)
    return products


def fetch_technical_posts(
    session: requests.Session,
    timeout: float,
) -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
    fields = "id,slug,link,title,content"
    for page in range(1, 30):
        url = (
            f"{TECH_ROOT}/wp-json/wp/v2/posts"
            f"?per_page=100&page={page}&_fields={fields}"
        )
        response = session.get(url, timeout=timeout)
        if response.status_code == 400 and "rest_post_invalid_page_number" in response.text:
            break
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        posts.extend(batch)
        total_pages = int(response.headers.get("X-WP-TotalPages", page))
        if page >= total_pages:
            break
    return posts


def formula_from_sku(sku: str) -> str | None:
    match = FORMULA_RE.search(sku or "")
    return match.group(1) if match else None


def product_sheet_formulas(product: dict[str, Any]) -> set[str]:
    formulas: set[str] = set()
    for variant in product.get("variants", []):
        sku = (variant.get("sku") or "").upper()
        if "-F-" not in sku or not any(token in sku for token in SHEET_SIZE_TOKENS):
            continue
        formula = formula_from_sku(sku)
        if formula:
            formulas.add(formula)
    return formulas


def is_sheet_product(product: dict[str, Any]) -> bool:
    return bool(product_sheet_formulas(product))


def image_gauge(text: str) -> str | None:
    match = GAUGE_RE.search(text or "")
    return match.group(1) if match else None


def compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def choose_srcset_thumbnail(image: Tag, max_width: int = 480) -> str:
    src = image.get("src", "")
    candidates: list[tuple[int, str]] = []
    for item in (image.get("srcset") or "").split(","):
        fields = item.strip().split()
        if len(fields) != 2 or not fields[1].endswith("w"):
            continue
        try:
            width = int(fields[1][:-1])
        except ValueError:
            continue
        candidates.append((width, fields[0]))
    under = [candidate for candidate in candidates if candidate[0] <= max_width]
    if under:
        return max(under)[1]
    if candidates:
        return min(candidates)[1]
    return src


def section_text(heading: Tag | None) -> str:
    if heading is None:
        return ""
    parts: list[str] = []
    for sibling in heading.next_siblings:
        if isinstance(sibling, Tag) and sibling.name in {"h2", "h3", "h4", "h5"}:
            break
        if isinstance(sibling, Tag) and sibling.name == "p":
            value = compact_text(sibling.get_text(" ", strip=True))
            if value:
                parts.append(value)
    return " ".join(parts)


def parse_technical_post(post: dict[str, Any]) -> dict[str, Any] | None:
    slug = post.get("slug", "")
    formula = formula_from_sku(slug)
    if formula is None or not slug.startswith(formula):
        return None

    content = post.get("content", {}).get("rendered", "")
    soup = BeautifulSoup(content, "html.parser")
    title = compact_text(
        BeautifulSoup(post.get("title", {}).get("rendered", ""), "html.parser").get_text()
    )
    striker = soup.find(id="h-striker") is not None
    reactive = soup.find(id="h-reactive-potential") is not None

    images: list[dict[str, Any]] = []
    for details in soup.find_all("details"):
        summary = details.find("summary")
        if summary is None or "sheet glass" not in summary.get_text(" ", strip=True).lower():
            continue
        for figure in details.find_all("figure"):
            image = figure.find("img")
            if image is None:
                continue
            caption_tag = figure.find("figcaption")
            caption = compact_text(
                caption_tag.get_text(" ", strip=True) if caption_tag else image.get("alt", "")
            )
            heading = figure.find_previous(["h4", "h5"])
            heading_text = compact_text(heading.get_text(" ", strip=True) if heading else "")
            role_text = f"{heading_text} {caption}".lower()
            if "unfired" in role_text or "cold characteristics" in role_text:
                role = "cold_sheet"
            elif "fired" in role_text or "fused tile" in role_text:
                role = "fired_tile"
            else:
                role = "unknown_sheet_figure"
            images.append(
                {
                    "role": role,
                    "caption": caption,
                    "section": heading_text,
                    "gauge": image_gauge(f"{caption} {image.get('src', '')}"),
                    "url": image.get("src", ""),
                    "thumbnail_url": choose_srcset_thumbnail(image),
                    "alt": image.get("alt", ""),
                }
            )

    cold_heading = soup.find(id="h-cold-characteristics")
    working_heading = soup.find(id="h-working-notes")
    return {
        "formula": formula,
        "title": title,
        "url": post.get("link", ""),
        "striker": striker,
        "reactive": reactive,
        "cold_characteristics": section_text(cold_heading),
        "working_notes": section_text(working_heading),
        "images": images,
    }


def pick_technical_image(
    images: Iterable[dict[str, Any]], role: str, gauge: str = "0030"
) -> dict[str, Any] | None:
    candidates = [image for image in images if image["role"] == role]
    exact = [image for image in candidates if image.get("gauge") == gauge]
    if exact:
        return exact[0]
    return candidates[0] if candidates else None


def choose_store_product(
    products: Iterable[dict[str, Any]], formula: str, gauge: str = "0030"
) -> dict[str, Any] | None:
    candidates = [product for product in products if formula in product_sheet_formulas(product)]
    if not candidates:
        return None

    def score(product: dict[str, Any]) -> tuple[int, int, str]:
        skus = [(variant.get("sku") or "").upper() for variant in product.get("variants", [])]
        has_gauge = any(f"-{gauge}-" in sku for sku in skus)
        return (0 if has_gauge else 1, -len(product.get("images", [])), product.get("handle", ""))

    return sorted(candidates, key=score)[0]


def with_width(url: str, width: int = 480) -> str:
    if "cdn.shopify.com" not in url and "/cdn/shop/" not in url:
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["width"] = str(width)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


class ImageFetcher:
    def __init__(self, session: requests.Session, timeout: float):
        self.session = session
        self.timeout = timeout
        self.cache: dict[str, Image.Image] = {}

    def get(self, url: str) -> Image.Image:
        if url not in self.cache:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content)).convert("RGB")
            self.cache[url] = ImageOps.exif_transpose(image)
        return self.cache[url].copy()


def center_crop(image: Image.Image, fraction: float = 0.54) -> Image.Image:
    width, height = image.size
    crop_width = max(1, int(width * fraction))
    crop_height = max(1, int(height * fraction))
    left = (width - crop_width) // 2
    top = (height - crop_height) // 2
    return image.crop((left, top, left + crop_width, top + crop_height))


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    values = np.asarray(rgb, dtype=np.float64) / 255.0
    linear = srgb_to_linear(values)
    xyz = np.array(
        [
            0.4124564 * linear[0] + 0.3575761 * linear[1] + 0.1804375 * linear[2],
            0.2126729 * linear[0] + 0.7151522 * linear[1] + 0.0721750 * linear[2],
            0.0193339 * linear[0] + 0.1191920 * linear[1] + 0.9503041 * linear[2],
        ]
    )
    xyz /= np.array([0.95047, 1.0, 1.08883])
    delta = 6.0 / 29.0
    f = np.where(xyz > delta**3, np.cbrt(xyz), xyz / (3 * delta**2) + 4.0 / 29.0)
    return np.array([116 * f[1] - 16, 500 * (f[0] - f[1]), 200 * (f[1] - f[2])])


def srgb_to_linear(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    return np.where(
        values <= 0.04045,
        values / 12.92,
        ((values + 0.055) / 1.055) ** 2.4,
    )


def robust_lab(image: Image.Image) -> list[float]:
    crop = center_crop(image).resize((160, 160), Image.Resampling.LANCZOS)
    pixels = np.asarray(crop, dtype=np.uint8).reshape(-1, 3)
    low = np.quantile(pixels, 0.10, axis=0)
    high = np.quantile(pixels, 0.90, axis=0)
    mask = np.all((pixels >= low) & (pixels <= high), axis=1)
    selected = pixels[mask] if int(mask.sum()) >= 100 else pixels
    median_rgb = np.median(selected, axis=0)
    return [float(value) for value in srgb_to_lab(median_rgb)]


def delta_e(lab_a: Iterable[float], lab_b: Iterable[float]) -> float:
    a = np.asarray(list(lab_a), dtype=np.float64)
    b = np.asarray(list(lab_b), dtype=np.float64)
    return float(np.linalg.norm(a - b))


def transmission_descriptor(image: Image.Image) -> dict[str, list[float]]:
    """Estimate center-sheet transmittance using the white surround as incident light.

    Bullseye's cold-sheet reference photos use a repeatable frame: the sheet fills the
    left/center and a white light-table surround remains visible around it. The fixed
    left-center crop avoids the product label and clamps. A high image-wide quantile is
    the white-reference estimate. This is intentionally a probe, not a claim of camera
    calibration.
    """

    resized = image.convert("RGB").resize((360, 360), Image.Resampling.LANCZOS)
    values = np.asarray(resized, dtype=np.float64) / 255.0
    sheet = values[54:306, 36:234].reshape(-1, 3)
    sheet_srgb = np.median(sheet, axis=0)
    white_srgb = np.quantile(values.reshape(-1, 3), 0.995, axis=0)
    white_linear = np.maximum(srgb_to_linear(white_srgb), 1e-4)
    transmission = np.clip(srgb_to_linear(sheet_srgb) / white_linear, 1e-4, 1.0)
    return {
        "sheet_srgb": [float(value) for value in sheet_srgb],
        "white_srgb": [float(value) for value in white_srgb],
        "transmission_linear": [float(value) for value in transmission],
    }


def thickness_metrics(t2: Iterable[float], t3: Iterable[float]) -> dict[str, Any]:
    transmission_2 = np.clip(np.asarray(list(t2), dtype=np.float64), 1e-4, 1.0)
    transmission_3 = np.clip(np.asarray(list(t3), dtype=np.float64), 1e-4, 1.0)
    optical_depth_2 = -np.log(transmission_2)
    optical_depth_3 = -np.log(transmission_3)
    valid = (optical_depth_2 >= 0.03) & (optical_depth_3 >= 0.03)
    predicted_3 = transmission_2**1.5
    if int(valid.sum()) == 0:
        return {
            "valid_channels": 0,
            "beer_lambert_mae": None,
            "same_thickness_mae": None,
            "beer_lambert_wins": None,
            "optical_depth_ratio_3mm_over_2mm": None,
            "absorption_coefficient_relative_error": None,
            "predicted_3mm_transmission": [float(value) for value in predicted_3],
        }
    beer_mae = float(np.mean(np.abs(transmission_3[valid] - predicted_3[valid])))
    same_mae = float(np.mean(np.abs(transmission_3[valid] - transmission_2[valid])))
    ratio = float(np.median(optical_depth_3[valid] / optical_depth_2[valid]))
    alpha_2 = optical_depth_2[valid] / 2.0
    alpha_3 = optical_depth_3[valid] / 3.0
    alpha_relative_error = float(
        np.mean(np.abs(alpha_3 - alpha_2) / np.maximum(0.5 * (alpha_3 + alpha_2), 1e-4))
    )
    return {
        "valid_channels": int(valid.sum()),
        "beer_lambert_mae": beer_mae,
        "same_thickness_mae": same_mae,
        "beer_lambert_wins": beer_mae < same_mae,
        "optical_depth_ratio_3mm_over_2mm": ratio,
        "absorption_coefficient_relative_error": alpha_relative_error,
        "predicted_3mm_transmission": [float(value) for value in predicted_3],
    }


def summarize_thickness(
    rows: list[dict[str, Any]], *, distinct_only: bool = False
) -> dict[str, Any]:
    if distinct_only:
        rows = [row for row in rows if not row.get("decoded_exact_duplicate", False)]
    valid = [row for row in rows if row["valid_channels"] > 0]
    ratios = [row["optical_depth_ratio_3mm_over_2mm"] for row in valid]
    alpha_errors = [row["absorption_coefficient_relative_error"] for row in valid]
    beer_mae = [row["beer_lambert_mae"] for row in valid]
    same_mae = [row["same_thickness_mae"] for row in valid]
    wins = sum(bool(row["beer_lambert_wins"]) for row in valid)
    return {
        "rows": len(rows),
        "valid_rows": len(valid),
        "beer_lambert_wins": wins,
        "beer_lambert_win_fraction": round(wins / max(1, len(valid)), 4),
        "median_optical_depth_ratio_3mm_over_2mm": round_or_none(percentile(ratios, 0.5)),
        "expected_optical_depth_ratio": 1.5,
        "median_absorption_coefficient_relative_error": round_or_none(percentile(alpha_errors, 0.5)),
        "median_beer_lambert_mae": round_or_none(percentile(beer_mae, 0.5)),
        "median_same_thickness_mae": round_or_none(percentile(same_mae, 0.5)),
    }


def decoded_pair_difference(image_a: Image.Image, image_b: Image.Image) -> dict[str, Any]:
    size = (256, 256)
    array_a = np.asarray(
        image_a.convert("RGB").resize(size, Image.Resampling.LANCZOS), dtype=np.int16
    )
    array_b = np.asarray(
        image_b.convert("RGB").resize(size, Image.Resampling.LANCZOS), dtype=np.int16
    )
    difference = np.abs(array_a - array_b)
    return {
        "decoded_exact_duplicate": bool(np.array_equal(array_a, array_b)),
        "decoded_pair_mae_srgb_255": float(np.mean(difference)),
        "decoded_pair_p99_abs_srgb_255": float(np.quantile(difference, 0.99)),
    }


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    return float(np.quantile(np.asarray(values, dtype=np.float64), q))


def round_or_none(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(float(value), digits)


def formula_from_registry_id(registry_id: str) -> str | None:
    match = re.match(r"bullseye-(\d{6})", registry_id or "")
    return match.group(1) if match else None


def load_json(path: Path) -> Any:
    with path.open() as handle:
        return json.load(handle)


def font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def fit_square(image: Image.Image, size: int) -> Image.Image:
    fitted = ImageOps.contain(image.convert("RGB"), (size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (size, size), "white")
    canvas.paste(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2))
    return canvas


def draw_contact_sheet(
    rows: list[dict[str, Any]],
    fetcher: ImageFetcher,
    output: Path,
    max_rows: int = 8,
) -> None:
    rows = rows[:max_rows]
    tile = 280
    gutter = 18
    label_height = 92
    header_height = 94
    row_height = tile + label_height
    width = 3 * tile + 4 * gutter
    height = header_height + len(rows) * row_height + gutter
    sheet = Image.new("RGB", (width, height), (246, 244, 236))
    draw = ImageDraw.Draw(sheet)
    draw.text((gutter, 14), "Bullseye material-state audit", fill=(30, 30, 28), font=font(28, True))
    headings = ("CURRENT CORPUS CHOICE", "COLD 3 MM SHEET", "FIRED TILE")
    for column, heading in enumerate(headings):
        x = gutter + column * (tile + gutter)
        draw.text((x, 57), heading, fill=(72, 65, 48), font=font(15, True))

    for index, row in enumerate(rows):
        y = header_height + index * row_height
        urls = (row["store_first_url"], row["cold_url"], row["fired_url"])
        for column, url in enumerate(urls):
            x = gutter + column * (tile + gutter)
            try:
                image = fit_square(fetcher.get(url), tile)
            except Exception:
                image = Image.new("RGB", (tile, tile), (220, 220, 220))
            sheet.paste(image, (x, y))
        title = f"{row['formula']}  {row['title']}"
        metrics = (
            f"cold↔fired ΔE {row['cold_fired_delta_e']:.1f}   "
            f"choice: {row['store_first_classification'].replace('_', ' ')}"
        )
        draw.text((gutter, y + tile + 10), title[:92], fill=(28, 28, 26), font=font(17, True))
        draw.text((gutter, y + tile + 38), metrics, fill=(78, 72, 57), font=font(15))
        draw.line((gutter, y + row_height - 8, width - gutter, y + row_height - 8), fill=(210, 205, 191), width=1)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=90, optimize=True)


def main() -> None:
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    session = make_session()

    store_products = fetch_shop_products(session, args.timeout)
    striker_products = fetch_shop_products(session, args.timeout, collection="strikers")
    striker_handles = {product.get("handle", "") for product in striker_products}
    technical_posts_raw = fetch_technical_posts(session, args.timeout)
    technical_posts = [
        parsed
        for post in technical_posts_raw
        if (parsed := parse_technical_post(post)) is not None
    ]
    technical_by_formula = {post["formula"]: post for post in technical_posts}

    sheet_products = [product for product in store_products if is_sheet_product(product)]
    store_by_formula: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for product in sheet_products:
        for formula in product_sheet_formulas(product):
            store_by_formula[formula].append(product)

    striker_sheet_products = [
        product for product in sheet_products if product.get("handle", "") in striker_handles
    ]
    striker_formulas = {
        formula
        for product in striker_sheet_products
        for formula in product_sheet_formulas(product)
    }

    registry = load_json(args.registry)
    clean_manifest = load_json(args.clean_manifest)
    registry_by_formula: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in registry:
        formula = formula_from_registry_id(item.get("id", ""))
        if formula:
            registry_by_formula[formula].append(item)
    clean_by_formula: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in clean_manifest.get("images", []):
        formula = formula_from_registry_id(item.get("registry_id", ""))
        if formula:
            clean_by_formula[formula].append(item)

    candidates: list[dict[str, Any]] = []
    for formula in sorted(striker_formulas):
        technical = technical_by_formula.get(formula)
        if not technical:
            continue
        cold = pick_technical_image(technical["images"], "cold_sheet", "0030")
        fired = pick_technical_image(technical["images"], "fired_tile", "0030")
        store = choose_store_product(store_by_formula.get(formula, []), formula, "0030")
        if not cold or not fired or not store or not store.get("images"):
            continue
        candidates.append(
            {
                "formula": formula,
                "title": re.sub(r"^\d{6}\s+", "", technical["title"]),
                "technical_url": technical["url"],
                "store_url": f"{SHOP_ROOT}/products/{store.get('handle', '')}",
                "store_handle": store.get("handle", ""),
                "store_image_count": len(store.get("images", [])),
                "store_first_url": with_width(store["images"][0]["src"]),
                "cold_url": cold.get("thumbnail_url") or cold["url"],
                "cold_full_url": cold["url"],
                "cold_caption": cold["caption"],
                "fired_url": fired.get("thumbnail_url") or fired["url"],
                "fired_full_url": fired["url"],
                "fired_caption": fired["caption"],
                "cold_characteristics": technical["cold_characteristics"],
                "working_notes": technical["working_notes"],
                "registry_ids": sorted(item["id"] for item in registry_by_formula.get(formula, [])),
                "clean_files": sorted(item["file"] for item in clean_by_formula.get(formula, [])),
            }
        )

    if args.max_eval > 0:
        candidates = candidates[: args.max_eval]

    fetcher = ImageFetcher(session, args.timeout)
    evaluated: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for index, candidate in enumerate(candidates, start=1):
        try:
            store_image = fetcher.get(candidate["store_first_url"])
            cold_image = fetcher.get(candidate["cold_url"])
            fired_image = fetcher.get(candidate["fired_url"])
            store_lab = robust_lab(store_image)
            cold_lab = robust_lab(cold_image)
            fired_lab = robust_lab(fired_image)
            store_to_cold = delta_e(store_lab, cold_lab)
            store_to_fired = delta_e(store_lab, fired_lab)
            cold_to_fired = delta_e(cold_lab, fired_lab)
            margin = store_to_cold - store_to_fired
            if margin >= 4.0:
                classification = "fired_closer"
            elif margin <= -4.0:
                classification = "cold_closer"
            else:
                classification = "ambiguous"
            row = dict(candidate)
            row.update(
                {
                    "store_first_lab": [round(value, 3) for value in store_lab],
                    "cold_lab": [round(value, 3) for value in cold_lab],
                    "fired_lab": [round(value, 3) for value in fired_lab],
                    "store_to_cold_delta_e": round(store_to_cold, 3),
                    "store_to_fired_delta_e": round(store_to_fired, 3),
                    "cold_fired_delta_e": round(cold_to_fired, 3),
                    "fired_closer_margin_delta_e": round(margin, 3),
                    "store_first_classification": classification,
                }
            )
            evaluated.append(row)
            if index % 20 == 0:
                print(f"evaluated {index}/{len(candidates)} labeled striker triples", flush=True)
        except Exception as error:
            failures.append({"formula": candidate["formula"], "error": str(error)})

    classifications = Counter(row["store_first_classification"] for row in evaluated)
    cold_fired = [row["cold_fired_delta_e"] for row in evaluated]
    fired_closer_rows = [row for row in evaluated if row["store_first_classification"] == "fired_closer"]
    affected_formulas = {row["formula"] for row in fired_closer_rows}
    affected_clean_rows = [
        item
        for formula in affected_formulas
        for item in clean_by_formula.get(formula, [])
    ]

    thickness_candidates: list[dict[str, Any]] = []
    for technical in sorted(technical_posts, key=lambda post: post["formula"]):
        formula = technical["formula"]
        cold_3mm = pick_technical_image(technical["images"], "cold_sheet", "0030")
        cold_2mm = pick_technical_image(technical["images"], "cold_sheet", "0050")
        if not cold_3mm or not cold_2mm or formula not in clean_by_formula:
            continue
        categories = Counter(
            item.get("category", "Unknown") for item in registry_by_formula.get(formula, [])
        )
        category = categories.most_common(1)[0][0] if categories else "Unknown"
        thickness_candidates.append(
            {
                "formula": formula,
                "title": re.sub(r"^\d{6}\s+", "", technical["title"]),
                "category": category,
                "technical_url": technical["url"],
                "striker": technical["striker"],
                "cold_2mm_url": cold_2mm.get("thumbnail_url") or cold_2mm["url"],
                "cold_2mm_full_url": cold_2mm["url"],
                "cold_2mm_caption": cold_2mm["caption"],
                "cold_3mm_url": cold_3mm.get("thumbnail_url") or cold_3mm["url"],
                "cold_3mm_full_url": cold_3mm["url"],
                "cold_3mm_caption": cold_3mm["caption"],
                "clean_files": sorted(item["file"] for item in clean_by_formula[formula]),
            }
        )
    if args.max_thickness_eval > 0:
        thickness_candidates = thickness_candidates[: args.max_thickness_eval]

    thickness_rows: list[dict[str, Any]] = []
    thickness_failures: list[dict[str, str]] = []
    for index, candidate in enumerate(thickness_candidates, start=1):
        try:
            image_2mm = fetcher.get(candidate["cold_2mm_url"])
            image_3mm = fetcher.get(candidate["cold_3mm_url"])
            descriptor_2mm = transmission_descriptor(image_2mm)
            descriptor_3mm = transmission_descriptor(image_3mm)
            metrics = thickness_metrics(
                descriptor_2mm["transmission_linear"],
                descriptor_3mm["transmission_linear"],
            )
            pair_difference = decoded_pair_difference(image_2mm, image_3mm)
            row = dict(candidate)
            row.update(
                {
                    "cold_2mm_descriptor": {
                        key: [round(value, 5) for value in values]
                        for key, values in descriptor_2mm.items()
                    },
                    "cold_3mm_descriptor": {
                        key: [round(value, 5) for value in values]
                        for key, values in descriptor_3mm.items()
                    },
                    **{
                        key: round(value, 5) if isinstance(value, float) else value
                        for key, value in metrics.items()
                    },
                    **{
                        key: round(value, 5) if isinstance(value, float) else value
                        for key, value in pair_difference.items()
                    },
                }
            )
            thickness_rows.append(row)
            if index % 40 == 0:
                print(
                    f"evaluated {index}/{len(thickness_candidates)} cold thickness pairs",
                    flush=True,
                )
        except Exception as error:
            thickness_failures.append({"formula": candidate["formula"], "error": str(error)})

    thickness_by_category = {
        category: {
            "all": summarize_thickness(
                [row for row in thickness_rows if row["category"] == category]
            ),
            "distinct_images": summarize_thickness(
                [row for row in thickness_rows if row["category"] == category],
                distinct_only=True,
            ),
        }
        for category in sorted({row["category"] for row in thickness_rows})
    }

    technical_striker_formulas = {
        post["formula"] for post in technical_posts if post["striker"]
    }
    technical_cold_formulas = {
        post["formula"]
        for post in technical_posts
        if pick_technical_image(post["images"], "cold_sheet")
    }
    technical_fired_formulas = {
        post["formula"]
        for post in technical_posts
        if pick_technical_image(post["images"], "fired_tile")
    }
    technical_pair_formulas = {
        post["formula"]
        for post in technical_posts
        if pick_technical_image(post["images"], "cold_sheet")
        and pick_technical_image(post["images"], "fired_tile")
    }
    technical_thickness_pair_formulas = {
        post["formula"]
        for post in technical_posts
        if pick_technical_image(post["images"], "cold_sheet", "0030")
        and pick_technical_image(post["images"], "cold_sheet", "0050")
    }
    cold_anchor_rows: list[dict[str, Any]] = []
    for formula in sorted(set(clean_by_formula) & technical_cold_formulas):
        technical = technical_by_formula[formula]
        cold_3mm = pick_technical_image(technical["images"], "cold_sheet", "0030")
        cold_2mm = pick_technical_image(technical["images"], "cold_sheet", "0050")
        fallback = pick_technical_image(technical["images"], "cold_sheet")
        categories = Counter(
            item.get("category", "Unknown") for item in registry_by_formula.get(formula, [])
        )
        cold_anchor_rows.append(
            {
                "formula": formula,
                "title": re.sub(r"^\d{6}\s+", "", technical["title"]),
                "category": categories.most_common(1)[0][0] if categories else "Unknown",
                "striker": technical["striker"],
                "technical_url": technical["url"],
                "cold_characteristics": technical["cold_characteristics"],
                "cold_3mm": cold_3mm,
                "cold_2mm": cold_2mm,
                "cold_fallback": fallback,
                "clean_files": sorted(item["file"] for item in clean_by_formula[formula]),
            }
        )

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "shop_products": f"{SHOP_ROOT}/products.json",
            "striker_collection": f"{SHOP_ROOT}/collections/strikers",
            "technical_api": f"{TECH_ROOT}/wp-json/wp/v2/posts",
            "registry": str(args.registry.resolve()),
            "clean_manifest": str(args.clean_manifest.resolve()),
        },
        "store": {
            "all_products": len(store_products),
            "sheet_products": len(sheet_products),
            "sheet_image_count_histogram": {
                str(key): value
                for key, value in sorted(Counter(len(product.get("images", [])) for product in sheet_products).items())
            },
            "multi_image_sheet_products": sum(len(product.get("images", [])) > 1 for product in sheet_products),
            "striker_sheet_products": len(striker_sheet_products),
            "striker_formulas": len(striker_formulas),
        },
        "technical_pages": {
            "all_wordpress_posts_fetched": len(technical_posts_raw),
            "formula_pages": len(technical_posts),
            "striker_formulas": len(technical_striker_formulas),
            "cold_labeled_formulas": len(technical_cold_formulas),
            "fired_labeled_formulas": len(technical_fired_formulas),
            "cold_and_fired_labeled_formula_pairs": len(technical_pair_formulas),
            "cold_2mm_and_3mm_labeled_formula_pairs": len(technical_thickness_pair_formulas),
        },
        "vitrai_overlap": {
            "registry_bullseye_formulas": len(registry_by_formula),
            "clean_manifest_bullseye_formulas": len(clean_by_formula),
            "clean_manifest_bullseye_rows": sum(len(rows) for rows in clean_by_formula.values()),
            "clean_formulas_in_striker_collection": len(set(clean_by_formula) & striker_formulas),
            "clean_rows_in_striker_collection": sum(
                len(clean_by_formula[formula]) for formula in set(clean_by_formula) & striker_formulas
            ),
            "clean_formulas_with_official_cold_anchor": len(cold_anchor_rows),
            "clean_rows_with_official_cold_anchor": sum(
                len(row["clean_files"]) for row in cold_anchor_rows
            ),
            "clean_striker_formulas_with_official_cold_anchor": sum(
                row["striker"] for row in cold_anchor_rows
            ),
            "clean_striker_rows_with_official_cold_anchor": sum(
                len(row["clean_files"]) for row in cold_anchor_rows if row["striker"]
            ),
        },
        "image_state_probe": {
            "candidate_triples": len(candidates),
            "evaluated_triples": len(evaluated),
            "failures": len(failures),
            "classification_counts": dict(sorted(classifications.items())),
            "fired_closer_fraction": round(
                classifications.get("fired_closer", 0) / max(1, len(evaluated)), 4
            ),
            "cold_fired_delta_e": {
                "median": round_or_none(percentile(cold_fired, 0.5)),
                "p75": round_or_none(percentile(cold_fired, 0.75)),
                "p90": round_or_none(percentile(cold_fired, 0.9)),
                "max": round_or_none(max(cold_fired) if cold_fired else None),
                "above_10": sum(value >= 10 for value in cold_fired),
                "above_20": sum(value >= 20 for value in cold_fired),
                "above_40": sum(value >= 40 for value in cold_fired),
            },
            "clean_manifest_formulas_with_fired_closer_choice": len(affected_formulas & set(clean_by_formula)),
            "clean_manifest_rows_with_fired_closer_choice": len(affected_clean_rows),
        },
        "thickness_probe": {
            "candidate_clean_corpus_pairs": len(thickness_candidates),
            "evaluated_pairs": len(thickness_rows),
            "failures": len(thickness_failures),
            "decoded_exact_duplicate_pairs": sum(
                row["decoded_exact_duplicate"] for row in thickness_rows
            ),
            "overall_all_pairs": summarize_thickness(thickness_rows),
            "overall_distinct_images": summarize_thickness(
                thickness_rows, distinct_only=True
            ),
            "by_registry_category": thickness_by_category,
            "interpretation": (
                "A Beer-Lambert win only means the 2 mm image predicts the 3 mm image "
                "better than copying 2 mm unchanged under this white-reference heuristic."
            ),
        },
        "limitations": [
            "Delta-E is computed from robust center-crop median color, not radiometrically calibrated pixels.",
            "The official images can depict different physical sheets and camera setups; labels establish material state, not pixel correspondence.",
            "A four-delta-E nearest-state margin is an audit heuristic, not a learned classifier.",
            "The affected-row count covers evaluated formulas only and is therefore a lower bound.",
            "The thickness probe assumes the brightest image pixels approximate the light-table white reference and does not recover a camera response curve.",
            "Nominal 2 mm/3 mm pairs are different physical sheets; only formula, gauge, and cold material state are shared.",
        ],
    }

    ranked = sorted(
        evaluated,
        key=lambda row: (row["cold_fired_delta_e"], row["fired_closer_margin_delta_e"]),
        reverse=True,
    )
    payload = {
        "summary": summary,
        "rows": ranked,
        "failures": failures,
        "thickness_rows": sorted(
            thickness_rows,
            key=lambda row: (
                row["beer_lambert_wins"] is True,
                -1.0
                if row["absorption_coefficient_relative_error"] is None
                else -row["absorption_coefficient_relative_error"],
            ),
            reverse=True,
        ),
        "thickness_failures": thickness_failures,
        "cold_anchor_rows": cold_anchor_rows,
    }
    with (args.out_dir / "material_state_manifest.json").open("w") as handle:
        json.dump(payload, handle, indent=2)
    with (args.out_dir / "summary.json").open("w") as handle:
        json.dump(summary, handle, indent=2)

    contact_rows = [
        row for row in ranked if row["store_first_classification"] == "fired_closer"
    ]
    if not contact_rows:
        contact_rows = ranked
    draw_contact_sheet(contact_rows, fetcher, args.out_dir / "material_state_contact_sheet.jpg")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
