import asyncio
import os

import modal


class SAMService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._cls = None

    def load(self) -> None:
        # Lazy Modal lookup; keeps startup fast and avoids failing if Modal isn't available yet.
        self._cls = None

    async def encode(self, image_bytes: bytes) -> str:
        async with self._lock:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._encode_sync, image_bytes)

    async def segment(self, session_id: str, box: tuple[float, float, float, float] | None, points: list[tuple[float, float, int]] | None) -> list[list[int]]:
        async with self._lock:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._segment_sync, session_id, box, points)

    def _get_cls(self):
        if self._cls is None:
            app_name = os.environ.get("VITRAUX_MODAL_APP", "vitraux-sam2-v2")
            cls_name = os.environ.get("VITRAUX_MODAL_CLS", "Sam2BoxSegmenter")
            self._cls = modal.Cls.from_name(app_name, cls_name)
        return self._cls

    def _encode_sync(self, image_bytes: bytes) -> str:
        cls = self._get_cls()
        return cls().encode.remote(image_bytes)

    def _segment_sync(self, session_id: str, box: tuple[float, float, float, float] | None, points: list[tuple[float, float, int]] | None) -> list[list[int]]:
        cls = self._get_cls()
        return cls().segment.remote(session_id, box, points)
