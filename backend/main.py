from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from predictor import SAMService

service = SAMService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    service.load()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/encode")
async def encode(file: UploadFile = File(...)):
    data = await file.read()
    image_id = await service.encode(data)
    return {"image_id": image_id}


class Point(BaseModel):
    x: float
    y: float
    label: int

class SegmentRequest(BaseModel):
    image_id: str
    box: list[float] | None = None  # [x1, y1, x2, y2]
    points: list[Point] | None = None


@app.post("/segment")
async def segment(req: SegmentRequest):
    try:
        box_tuple = tuple(req.box) if req.box else None
        points_list = [(p.x, p.y, p.label) for p in req.points] if req.points else None
        polygon = await service.segment(req.image_id, box_tuple, points_list)
        return {"polygon": polygon}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class AutoSegmentRequest(BaseModel):
    image_id: str
    crop: list[int] | None = None # [top, bottom, left, right]

@app.post("/auto_segment")
async def auto_segment(req: AutoSegmentRequest):
    try:
        crop_tuple = tuple(req.crop) if req.crop else None
        polygons = await service.auto_segment(req.image_id, crop_tuple)
        return {"polygons": polygons}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/warp")
async def warp_image(
    file: UploadFile = File(...),
    corners: str = Form(...),  # JSON: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
):
    import base64
    import json

    import cv2
    import numpy as np

    try:
        data = await file.read()
        corners_list = json.loads(corners)
        if len(corners_list) != 4:
            raise ValueError("exactly 4 corners required")

        img_array = np.frombuffer(data, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("failed to decode image")

        pts = np.array(corners_list, dtype=np.float32)
        # Sort corners: TL (min x+y), TR (min x-y), BR (max x+y), BL (max x-y)
        s = pts.sum(axis=1)
        d = pts[:, 0] - pts[:, 1]
        tl = pts[np.argmin(s)]
        br = pts[np.argmax(s)]
        tr = pts[np.argmin(d)]
        bl = pts[np.argmax(d)]
        src = np.array([tl, tr, br, bl], dtype=np.float32)

        w = max(
            float(np.linalg.norm(tr - tl)),
            float(np.linalg.norm(br - bl)),
        )
        h = max(
            float(np.linalg.norm(bl - tl)),
            float(np.linalg.norm(br - tr)),
        )
        dst = np.array(
            [[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32
        )

        M = cv2.getPerspectiveTransform(src, dst)
        warped = cv2.warpPerspective(img, M, (int(w), int(h)))

        _, buf = cv2.imencode(".jpg", warped, [cv2.IMWRITE_JPEG_QUALITY, 95])
        b64 = base64.b64encode(buf).decode()
        return {
            "warped_image": f"data:image/jpeg;base64,{b64}",
            "width": int(w),
            "height": int(h),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
