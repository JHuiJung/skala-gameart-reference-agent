from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from app.dependencies import get_upload_form
from app.schemas import UploadForm, UploadResponse

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/upload", response_model=UploadResponse)
async def upload(form: Annotated[UploadForm, Depends(get_upload_form)], image: UploadFile = File(...)):
    if not (image.content_type or "").startswith("image/"):
        raise HTTPException(status_code=415, detail="이미지 파일만 업로드할 수 있습니다.")

    data = await image.read()
    print(f"텍스트: {form.text}")
    print(f"이미지 이름: {image.filename} ({image.content_type}, {len(data)} bytes)")
    return UploadResponse(
        message="업로드 완료",
        text=form.text,
        image_name=image.filename,
        image_size=len(data),
    )
