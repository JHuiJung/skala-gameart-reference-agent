import base64
import json
from contextlib import contextmanager
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

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


STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}  # 중간에서 응답을 모아 두지 않게 한다


async def _read_upload(form: UploadForm, image: UploadFile) -> dict:
    """업로드된 이미지를 검증하고 에이전트의 시작 상태로 만든다."""
    if not (image.content_type or "").startswith("image/"):
        raise HTTPException(status_code=415, detail="이미지 파일만 업로드할 수 있습니다.")
    data = await image.read()
    return {
        "text": form.text,
        "image_b64": base64.b64encode(data).decode(),
        "image_mime": image.content_type,
    }


@contextmanager
def _resume_errors():
    """이어서 실행할 수 없는 경우를 알맞은 HTTP 오류로 바꾼다."""
    try:
        yield
    except runner.ThreadNotWaiting:
        raise HTTPException(status_code=409, detail="답변을 기다리는 작업이 없습니다. 처음부터 다시 시도해주세요.")
    except runner.WrongAnswerKind as e:
        raise HTTPException(status_code=422, detail=f"지금은 '{e}' 에 대한 답을 기다리고 있습니다.")


async def _sse(events):
    """(이벤트 이름, 데이터)를 Server-Sent Events 형식으로 바꾼다."""
    async for event, data in events:
        yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/upload", response_model=AgentResponse)
async def upload(form: Annotated[UploadForm, Depends(get_upload_form)], image: UploadFile = File(...)):
    """새 작업 시작. 필수 항목이 부족하면 status=needs_input 과 질문 목록을 돌려준다."""
    return await runner.start(await _read_upload(form, image))


@app.post("/answer", response_model=AgentResponse)
async def answer(body: AnswerRequest):
    """질문 답변 또는 확정한 카테고리를 받아 멈춘 작업을 이어서 실행한다."""
    with _resume_errors():
        return await runner.resume(body)


@app.post("/upload/stream")
async def upload_stream(form: Annotated[UploadForm, Depends(get_upload_form)], image: UploadFile = File(...)):
    """/upload 와 같지만 진행 상황을 실시간으로(SSE) 보낸다. 이벤트: step, detail, result, error"""
    state = await _read_upload(form, image)
    return StreamingResponse(_sse(runner.stream_start(state)), media_type="text/event-stream", headers=STREAM_HEADERS)


@app.post("/answer/stream")
async def answer_stream(body: AnswerRequest):
    """/answer 와 같지만 진행 상황을 실시간으로(SSE) 보낸다."""
    # 스트리밍은 응답을 시작한 뒤에는 상태 코드를 바꿀 수 없으므로, 재개 가능 여부는 시작하기 전에 확인한다
    with _resume_errors():
        value = await runner.prepare_resume(body)
    return StreamingResponse(
        _sse(runner.stream_resume(body.thread_id, value)), media_type="text/event-stream", headers=STREAM_HEADERS
    )
