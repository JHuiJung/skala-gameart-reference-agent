from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/upload")
async def upload(image: UploadFile = File(...)):
    data = await image.read()
    print(f"이미지 업로드됨: {image.filename} ({image.content_type}, {len(data)} bytes)")
    return {"message": "업로드 완료", "filename": image.filename, "size": len(data)}
