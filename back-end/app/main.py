import base64
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.agent import runner
from app.dependencies import get_upload_form
from app.schemas import AgentResponse, AnswerRequest, UploadForm

load_dotenv()  # 로컬 실행 시 프로젝트 루트의 .env 로드 (Docker 는 env_file 사용)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/upload", response_model=AgentResponse)
async def upload(form: Annotated[UploadForm, Depends(get_upload_form)], image: UploadFile = File(...)):
    """새 작업 시작. 필수 항목이 부족하면 status=needs_input 과 질문 목록을 돌려준다."""
    if not (image.content_type or "").startswith("image/"):
        raise HTTPException(status_code=415, detail="이미지 파일만 업로드할 수 있습니다.")

    data = await image.read()
    return await runner.start({
        "text": form.text,
        "image_b64": base64.b64encode(data).decode(),
        "image_mime": image.content_type,
    })


@app.post("/answer", response_model=AgentResponse)
async def answer(body: AnswerRequest):
    """질문 답변 또는 확정한 카테고리를 받아 멈춘 작업을 이어서 실행한다."""
    try:
        return await runner.resume(body.thread_id, body.answers, body.categories)
    except runner.ThreadNotWaiting:
        raise HTTPException(status_code=409, detail="답변을 기다리는 작업이 없습니다. 처음부터 다시 시도해주세요.")
    except runner.WrongAnswerKind as e:
        raise HTTPException(status_code=422, detail=f"지금은 '{e}' 에 대한 답을 기다리고 있습니다.")
