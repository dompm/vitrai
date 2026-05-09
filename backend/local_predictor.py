from __future__ import annotations

import asyncio
import hashlib
import io
from typing import Any

LOCAL_MODEL_ID = "facebook/sam2.1-hiera-tiny"


class LocalSAMService:
    """Runs SAM2-tiny on CPU for local development without Modal."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._predictor = None
        self._generator = None
        self._cache: dict[str, dict] = {}

    def _ensure_loaded(self) -> None:
        if self._predictor is not None:
            return
        from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator
        from sam2.sam2_image_predictor import SAM2ImagePredictor

        self._predictor = SAM2ImagePredictor.from_pretrained(LOCAL_MODEL_ID, device="cpu")
        self._generator = SAM2AutomaticMaskGenerator(self._predictor.model)

    def _decode_rgb(self, image_bytes: bytes) -> Any:
        import numpy as np
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        return np.array(img)

    def _serialize_features(self) -> bytes:
        import torch

        buf = io.BytesIO()
        torch.save(self._predictor._features, buf)  # type: ignore[attr-defined]
        return buf.getvalue()

    def _load_features(self, payload: bytes) -> Any:
        import torch

        buf = io.BytesIO(payload)
        return torch.load(buf, map_location="cpu", weights_only=False)

    def _mask_to_polygon(self, mask: Any) -> list[list[int]]:
        import cv2

        mask_u8 = (mask.astype("uint8")) * 255
        contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return []
        c = max(contours, key=cv2.contourArea)
        eps = 0.005 * cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, eps, True)
        return approx.reshape(-1, 2).tolist()

    async def encode(self, image_bytes: bytes) -> str:
        async with self._lock:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._encode_sync, image_bytes)

    async def segment(
        self,
        session_id: str,
        box: tuple[float, float, float, float] | None,
        points: list[tuple[float, float, int]] | None,
    ) -> list[list[int]]:
        async with self._lock:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._segment_sync, session_id, box, points)

    async def auto_segment(
        self,
        session_id: str,
        crop: tuple[int, int, int, int] | None,
    ) -> list[list[list[int]]]:
        async with self._lock:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._auto_segment_sync, session_id, crop)

    def _encode_sync(self, image_bytes: bytes) -> str:
        self._ensure_loaded()
        session_id = hashlib.sha256(image_bytes).hexdigest()[:16]
        if session_id in self._cache and "image_bytes" in self._cache[session_id]:
            return session_id

        img = self._decode_rgb(image_bytes)
        self._predictor.set_image(img)  # type: ignore[union-attr]

        orig_hw = tuple(self._predictor._orig_hw[0])  # type: ignore[union-attr,attr-defined]
        self._cache[session_id] = {
            "orig_hw": (int(orig_hw[0]), int(orig_hw[1])),
            "features": self._serialize_features(),
            "image_bytes": image_bytes,
        }
        return session_id

    def _segment_sync(
        self,
        session_id: str,
        box: tuple[float, float, float, float] | None,
        points: list[tuple[float, float, int]] | None,
    ) -> list[list[int]]:
        import numpy as np

        self._ensure_loaded()
        if session_id not in self._cache:
            raise KeyError(session_id)

        cached = self._cache[session_id]
        pred = self._predictor  # type: ignore[union-attr]
        pred.reset_predictor()
        pred._orig_hw = [cached["orig_hw"]]  # type: ignore[attr-defined]
        pred._features = self._load_features(cached["features"])  # type: ignore[attr-defined]
        pred._is_image_set = True  # type: ignore[attr-defined]
        pred._is_batch = False  # type: ignore[attr-defined]

        kwargs: dict = {"multimask_output": False}
        if box is not None:
            kwargs["box"] = np.array([[box[0], box[1], box[2], box[3]]], dtype=np.float32)
        if points:
            kwargs["point_coords"] = np.array([[p[0], p[1]] for p in points], dtype=np.float32)
            kwargs["point_labels"] = np.array([p[2] for p in points], dtype=np.int32)

        masks, _, _ = pred.predict(**kwargs)
        return self._mask_to_polygon(masks[0])

    def _auto_segment_sync(
        self,
        session_id: str,
        crop: tuple[int, int, int, int] | None,
    ) -> list[list[list[int]]]:
        self._ensure_loaded()
        if session_id not in self._cache:
            raise KeyError(session_id)

        cached = self._cache[session_id]
        img = self._decode_rgb(cached["image_bytes"])

        offset_x, offset_y = 0, 0
        if crop is not None:
            top, bottom, left, right = crop
            h, w = img.shape[:2]
            valid_top = max(0, min(top, h - 1))
            valid_bottom = max(0, min(bottom, h - 1))
            valid_left = max(0, min(left, w - 1))
            valid_right = max(0, min(right, w - 1))

            if valid_top < h - valid_bottom and valid_left < w - valid_right:
                img = img[valid_top : h - valid_bottom, valid_left : w - valid_right]
                offset_x, offset_y = valid_left, valid_top

        masks = self._generator.generate(img)  # type: ignore[union-attr]

        polygons = []
        for mask_dict in masks:
            poly = self._mask_to_polygon(mask_dict["segmentation"])
            if poly and len(poly) >= 3:
                if offset_x > 0 or offset_y > 0:
                    poly = [[x + offset_x, y + offset_y] for x, y in poly]
                polygons.append(poly)

        return polygons
