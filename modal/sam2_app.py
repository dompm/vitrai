from __future__ import annotations

# pyright: reportMissingImports=false

import io
from typing import Any, TypedDict

import modal

APP_NAME = "vitraux-sam2"
MODEL_ID = "facebook/sam2.1-hiera-small"

embeddings = modal.Dict.from_name("vitraux-sam2-embeddings", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        # SAM2 + runtime deps
        "sam2==1.1.0",
        "torch==2.3.1",
        "opencv-python-headless==4.10.0.84",
        "pillow==10.4.0",
        "numpy==2.0.2",
    )
)

app = modal.App(APP_NAME)

class CachedEmbeddings(TypedDict):
    orig_hw: tuple[int, int]
    features: bytes


@app.cls(
    image=image,
    gpu="A10G",
    timeout=60 * 10,
    scaledown_window=60 * 5,
)
class Sam2BoxSegmenter:
    def __enter__(self) -> None:
        import torch
        import numpy as np
        from sam2.sam2_image_predictor import SAM2ImagePredictor

        # These libs exist in the Modal image, not in the local venv.
        self.torch = torch
        self.np = np
        self.predictor = SAM2ImagePredictor.from_pretrained(MODEL_ID)

    def _decode_rgb(self, image_bytes: bytes) -> Any:
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        return self.np.array(img)

    def _serialize_features(self) -> bytes:
        buf = io.BytesIO()
        self.torch.save(self.predictor._features, buf)  # type: ignore[attr-defined]
        return buf.getvalue()

    def _load_features(self, payload: bytes) -> Any:
        buf = io.BytesIO(payload)
        feats = self.torch.load(buf, map_location="cpu")

        def to_device(x: Any) -> Any:
            if self.torch.is_tensor(x):
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
            return session_id

        img = self._decode_rgb(image_bytes)
        self.predictor.set_image(img)

        orig_hw = tuple(self.predictor._orig_hw[0])  # type: ignore[attr-defined]
        embeddings[session_id] = {
            "orig_hw": (int(orig_hw[0]), int(orig_hw[1])),
            "features": self._serialize_features(),
        }
        return session_id

    @modal.method()
    def segment_box(self, session_id: str, box: tuple[float, float, float, float]) -> list[list[int]]:
        if session_id not in embeddings:
            raise KeyError(session_id)

        cached: CachedEmbeddings = embeddings[session_id]  # type: ignore[assignment]

        self.predictor.reset_predictor()
        self.predictor._orig_hw = [cached["orig_hw"]]  # type: ignore[attr-defined]
        self.predictor._features = self._load_features(cached["features"])  # type: ignore[attr-defined]
        self.predictor._is_image_set = True  # type: ignore[attr-defined]
        self.predictor._is_batch = False  # type: ignore[attr-defined]

        masks, _, _ = self.predictor.predict(
            box=self.np.array([[box[0], box[1], box[2], box[3]]], dtype=self.np.float32),
            multimask_output=False,
        )
        return self._mask_to_polygon(masks[0])

