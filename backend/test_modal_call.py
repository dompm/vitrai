import asyncio
from predictor import SAMService

async def main():
    service = SAMService()
    service.load()
    
    with open("../data/orange.png", "rb") as f:
        img_bytes = f.read()
    
    print("Calling encode...")
    try:
        session_id = await service.encode(img_bytes)
        print("Encode success. Session ID:", session_id)
        
        print("Calling segment...")
        box = (10, 10, 50, 50)
        polygon = await service.segment(session_id, box)
        print("Segment success. Polygon length:", len(polygon))
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
