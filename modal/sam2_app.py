from __future__ import annotations

# pyright: reportMissingImports=false

import io
from typing import Any, TypedDict

import modal

APP_NAME = "vitraux-sam2-v2"
MODEL_ID = "facebook/sam2.1-hiera-small"

embeddings = modal.Dict.from_name("vitraux-sam2-embeddings", create_if_missing=True)

def download_model():
    from huggingface_hub import snapshot_download
    snapshot_download("facebook/sam2.1-hiera-small")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        # SAM2 + runtime deps
        "sam2==1.1.0",
        "torch>=2.5.1",
        "opencv-python-headless==4.10.0.84",
        "pillow==10.4.0",
        "numpy==2.0.2",
        "huggingface_hub",
    )
    .run_function(download_model)
)

app = modal.App(APP_NAME)

class CachedEmbeddings(TypedDict):
    orig_hw: tuple[int, int]
    features: bytes
    image_bytes: bytes


@app.cls(
    image=image,
    gpu="A10G",
    timeout=60 * 10,
    scaledown_window=60 * 5,
)
class Sam2BoxSegmenter:
    @modal.enter()
    def setup_predictor(self) -> None:
        from sam2.sam2_image_predictor import SAM2ImagePredictor
        from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator
        
        self.predictor = SAM2ImagePredictor.from_pretrained(MODEL_ID)
        self.model = self.predictor.model
        self.generator = SAM2AutomaticMaskGenerator(self.model)

    def _decode_rgb(self, image_bytes: bytes) -> Any:
        from PIL import Image
        import numpy as np

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        return np.array(img)

    def _serialize_features(self) -> bytes:
        import torch
        buf = io.BytesIO()
        torch.save(self.predictor._features, buf)  # type: ignore[attr-defined]
        return buf.getvalue()

    def _load_features(self, payload: bytes) -> Any:
        import torch
        buf = io.BytesIO(payload)
        feats = torch.load(buf, map_location="cpu", weights_only=False)

        def to_device(x: Any) -> Any:
            if torch.is_tensor(x):
                return x.to(self.predictor.device)
            if isinstance(x, list):
                return [to_device(v) for v in x]
            if isinstance(x, dict):
                return {k: to_device(v) for k, v in x.items()}
            return x

        return to_device(feats)

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

    @modal.method()
    def encode(self, image_bytes: bytes) -> str:
        import hashlib

        session_id = hashlib.sha256(image_bytes).hexdigest()[:16]
        if session_id in embeddings:
            cached = embeddings[session_id]
            if "image_bytes" in cached:
                return session_id

        img = self._decode_rgb(image_bytes)
        self.predictor.set_image(img)

        orig_hw = tuple(self.predictor._orig_hw[0])  # type: ignore[attr-defined]
        embeddings[session_id] = {
            "orig_hw": (int(orig_hw[0]), int(orig_hw[1])),
            "features": self._serialize_features(),
            "image_bytes": image_bytes,
        }
        return session_id

    @modal.method()
    def segment(self, session_id: str, box: tuple[float, float, float, float] | None, points: list[tuple[float, float, int]] | None) -> list[list[int]]:
        import numpy as np
        if session_id not in embeddings:
            raise KeyError(session_id)

        cached: CachedEmbeddings = embeddings[session_id]  # type: ignore[assignment]

        self.predictor.reset_predictor()
        self.predictor._orig_hw = [cached["orig_hw"]]  # type: ignore[attr-defined]
        self.predictor._features = self._load_features(cached["features"])  # type: ignore[attr-defined]
        self.predictor._is_image_set = True  # type: ignore[attr-defined]
        self.predictor._is_batch = False  # type: ignore[attr-defined]

        kwargs = {"multimask_output": False}
        if box is not None:
            kwargs["box"] = np.array([[box[0], box[1], box[2], box[3]]], dtype=np.float32)
        if points is not None and len(points) > 0:
            kwargs["point_coords"] = np.array([[p[0], p[1]] for p in points], dtype=np.float32)
            kwargs["point_labels"] = np.array([p[2] for p in points], dtype=np.int32)

        masks, _, _ = self.predictor.predict(**kwargs)
        return self._mask_to_polygon(masks[0])

    @modal.method()
    def auto_segment(self, session_id: str, crop: tuple[int, int, int, int] | None = None) -> list[list[list[int]]]:
        if session_id not in embeddings:
            raise KeyError(session_id)
            
        cached: CachedEmbeddings = embeddings[session_id]  # type: ignore[assignment]
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
                img = img[valid_top:h-valid_bottom, valid_left:w-valid_right]
                offset_x, offset_y = valid_left, valid_top
        
        masks = self.generator.generate(img)
        
        polygons = []
        for mask_dict in masks:
            poly = self._mask_to_polygon(mask_dict["segmentation"])
            if poly and len(poly) >= 3:
                if offset_x > 0 or offset_y > 0:
                    poly = [[x + offset_x, y + offset_y] for x, y in poly]
                polygons.append(poly)
                
        return polygons

