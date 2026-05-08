import modal
import io
import asyncio
from PIL import Image

async def main():
    img = Image.new('RGB', (100, 100), color = 'black')
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    img_bytes = buf.getvalue()
    
    cls = modal.Cls.from_name("vitraux-sam2", "Sam2BoxSegmenter")
    print("Calling remote...")
    print(cls().encode.remote(img_bytes))

if __name__ == "__main__":
    asyncio.run(main())
