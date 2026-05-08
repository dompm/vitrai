import modal
try:
    cls = modal.Cls.from_name("vitraux-sam2", "Sam2BoxSegmenter")
    print(cls().encode)
    print("Method access works")
except Exception as e:
    print("Error:", e)
