from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
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

@app.post("/auto_segment")
async def auto_segment(req: AutoSegmentRequest):
    try:
        polygons = await service.auto_segment(req.image_id)
        return {"polygons": polygons}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
