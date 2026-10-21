import base64
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.agent.graph import graph
from app.dependencies import get_upload_form
from app.schemas import UploadForm, UploadResponse

load_dotenv()  # 로컬 실행 시 프로젝트 루트의 .env 로드 (Docker 는 env_file 사용)

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
    result = await graph.ainvoke({
        "text": form.text,
        "image_b64": base64.b64encode(data).decode(),
        "image_mime": image.content_type,
    })
    return UploadResponse(
        message="분석 완료",
        text=form.text,
        image_name=image.filename,
        image_size=len(data),
        analysis=result["analysis"],
        guidelines=result["guidelines"],
    )
