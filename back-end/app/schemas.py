"""API 요청/응답 데이터 구조를 정의하는 Pydantic 스키마 모음."""
from pydantic import BaseModel, Field

from app.agent.state import Guideline, InputAnalysis, SearchPlan


class UploadForm(BaseModel):
    """[요청] POST /upload 에서 이미지와 함께 받는 텍스트 입력.

    이미지 파일은 Pydantic 이 아니라 FastAPI 의 UploadFile 로 따로 받는다.
    """

    # 사용자가 원하는 내용을 설명한 문장 (빈 값 불가, 최대 2000자)
    text: str = Field(min_length=1, max_length=2000, description="사용자 설명 텍스트")


class UploadResponse(BaseModel):
    """[응답] POST /upload 처리 결과."""

    message: str  # 처리 결과 메시지 (예: "업로드 완료")
    text: str  # 서버가 받은 텍스트 (입력 그대로)
    image_name: str  # 업로드된 이미지의 원본 파일명
    image_size: int  # 업로드된 이미지의 크기 (bytes)
    analysis: InputAnalysis  # 에이전트의 입력 분석 결과
    guidelines: list[Guideline]  # RAG 로 찾은 관련 내부 가이드
    search_plan: SearchPlan  # 웹 이미지 검색 계획
