import asyncio
import os

import modal


def _lookup_modal(app_name: str, fn_name: str) -> modal.Function:
    """
    Looks up a deployed Modal function.

    You deploy it from `modal/sam2_app.py` and then the backend calls it by name.
    """
    return modal.Function.lookup(app_name, fn_name)


class SAMService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._encode_fn: modal.Function | None = None
        self._segment_fn: modal.Function | None = None

    def load(self) -> None:
        # Lazy Modal lookup; keeps startup fast and avoids failing if Modal isn't available yet.
        self._encode_fn = None
        self._segment_fn = None

    async def encode(self, image_bytes: bytes) -> str:
        async with self._lock:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._encode_sync, image_bytes)

    async def segment(self, session_id: str, box: tuple[float, float, float, float]) -> list[list[int]]:
        async with self._lock:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._segment_sync, session_id, box)

    def _encode_sync(self, image_bytes: bytes) -> str:
        if self._encode_fn is None:
            app_name = os.environ.get("VITRAUX_MODAL_APP", "vitraux-sam2")
            self._encode_fn = _lookup_modal(app_name, "encode")
        return self._encode_fn.remote(image_bytes)

    def _segment_sync(self, session_id: str, box: tuple[float, float, float, float]) -> list[list[int]]:
        if self._segment_fn is None:
            app_name = os.environ.get("VITRAUX_MODAL_APP", "vitraux-sam2")
            fn_name = os.environ.get("VITRAUX_MODAL_FN", "segment_box")
            self._segment_fn = _lookup_modal(app_name, fn_name)
        return self._segment_fn.remote(session_id, box)
