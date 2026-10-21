"""FastAPI 라우트에서 Depends() 로 주입해 쓰는 의존성 함수 모음."""
from typing import Annotated

from fastapi import Form, HTTPException
from pydantic import ValidationError

from app.schemas import UploadForm


def get_upload_form(text: Annotated[str, Form()]) -> UploadForm:
    """multipart 폼 필드(text)를 UploadForm 으로 검증·변환한다.

    이미지(File)와 함께 받을 때는 Form 모델을 직접 쓸 수 없어서 이 방식을 쓴다.
    검증에 실패하면 422 로 응답한다.
    """
    try:
        return UploadForm(text=text)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors(include_url=False, include_context=False))
