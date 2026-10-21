"""API 요청/응답 데이터 구조를 정의하는 Pydantic 스키마 모음."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.agent.state import Candidate, Guideline, InputAnalysis, Question, ReferenceCategory


class UploadForm(BaseModel):
    """[요청] POST /upload 에서 이미지와 함께 받는 텍스트 입력.

    이미지 파일은 Pydantic 이 아니라 FastAPI 의 UploadFile 로 따로 받는다.
    """

    # 사용자가 원하는 내용을 설명한 문장 (빈 값 불가, 최대 2000자)
    text: str = Field(min_length=1, max_length=2000, description="사용자 설명 텍스트")


class AnswerRequest(BaseModel):
    """[요청] POST /answer 에서 에이전트의 질문에 대한 사용자 답변."""

    thread_id: str  # 질문을 받았던 응답의 thread_id (어느 작업을 이어갈지)
    # kind=questions 에 대한 답: 질문의 key -> 사용자가 입력한 답. 비워 둔 항목은 "미정"으로 처리된다
    answers: dict[str, str] = {}
    # kind=confirm_categories 에 대한 답: 사용자가 확정한 카테고리 이름 (제안에서 뺀 것은 제외, 새로 추가한 것은 포함)
    categories: list[str] | None = None
    # kind=confirm_categories 와 함께 보내는, 카테고리당 보여줄 이미지 수 (1~10)
    per_category: int = Field(default=5, ge=1, le=10)

    @field_validator("categories")
    @classmethod
    def clean_categories(cls, names):
        if names is None:
            return None
        cleaned = [n.strip() for n in names if n.strip()]
        if not 1 <= len(cleaned) <= 8:
            raise ValueError("카테고리는 1~8개여야 합니다.")
        if any(len(n) > 40 for n in cleaned):
            raise ValueError("카테고리 이름은 40자 이하여야 합니다.")
        return cleaned


class AgentResponse(BaseModel):
    """[응답] /upload, /answer 공통 응답.

    status 가 needs_input 이면 questions 에 답해야 할 질문이 있고,
    done 이면 처리가 끝나 아래 결과 필드가 채워져 있다.
    """

    status: Literal["needs_input", "done"]
    kind: Literal["questions", "confirm_categories"] | None = None  # (needs_input) 어떤 종류의 답을 기다리는지
    thread_id: str  # 이 작업의 식별자. 질문에 답할 때 /answer 로 다시 보낸다
    asset_type: str | None = None  # character | background | prop | ui | unknown
    details: dict[str, str] = {}  # 지금까지 확인된 필수 항목 값 (key -> 값)
    detail_labels: dict[str, str] = {}  # 필수 항목 key -> 화면에 보여줄 이름

    questions: list[Question] = []  # (kind=questions) 사용자에게 되묻는 질문
    proposed_categories: list[ReferenceCategory] = []  # (kind=confirm_categories) AI 가 제안한 레퍼런스 카테고리
    goal: str = ""  # (kind=confirm_categories) AI 가 이해한 사용자의 최종 목표 - 잘못 이해했는지 확인용

    # (done) 처리 결과
    analysis: InputAnalysis | None = None  # 입력 분석 결과
    guidelines: list[Guideline] = []  # RAG 로 찾은 관련 내부 가이드
    categories: list[ReferenceCategory] = []  # 사용자가 확정한 레퍼런스 카테고리 (candidates 의 topic 과 같은 이름)
    exclude_terms: list[str] = []  # 검색에서 제외한 단어
    candidates: list[Candidate] = []  # 카테고리별로 찾아 검토를 통과한 레퍼런스 이미지 (topic 이 카테고리 이름)
    rejected_candidates: list[Candidate] = []  # 검토에서 부적합으로 걸러진 이미지 (review 에 이유)
    source_errors: list[str] = []  # 응답하지 않은 검색 출처
