"""LangGraph 에이전트가 노드 사이에서 주고받는 상태(State) 정의.
  입력 → analysis → guidelines → search_plan → candidates → selected_ids → 결과 파일
각 노드는 자기 단계의 필드만 채워서 반환하고, LangGraph 가 나머지 필드와 합쳐 준다.
"""
from typing import Literal, TypedDict

from pydantic import BaseModel, Field


class InputAnalysis(BaseModel):
    """[1단계 결과] 멀티모달 LLM 이 사용자 입력(텍스트/이미지)을 구조화한 내용."""

    subject: str = Field(description="만들려는 대상 (예: 숲속 목조 마을)")
    mood: list[str] = Field(default_factory=list, description="분위기 키워드")
    materials: list[str] = Field(default_factory=list, description="재질")
    colors: list[str] = Field(default_factory=list, description="색상")
    composition: str = Field(default="", description="구도·시점")
    exclude: list[str] = Field(default_factory=list, description="제외할 요소")
    summary: str = Field(default="", description="이미지가 있을 때 시각적 특징 요약")


class Guideline(BaseModel):
    """[2단계 결과] RAG 로 찾은 내부 가이드 한 조각 (vector_db 의 청크 하나)."""

    text: str = Field(description="가이드 본문")
    source_type: str = Field(description="confirmed_plans(확정된 기획) | company_rules(회사 규정)")
    category: str = Field(description="world, monster, color, modeling 등")
    file: str = Field(description="출처 문서 파일명")
    section: str = Field(description="문서 안의 섹션 제목")


class GuidelineRouting(BaseModel):
    """[2단계 중간 결과] 입력에 관련된 내부 가이드 카테고리를 LLM 이 고른 것."""

    categories: list[Literal["world", "mood", "background", "monster", "color", "modeling", "texture", "naming"]] = Field(
        description="검색할 가이드 카테고리"
    )


class SearchPlan(BaseModel):
    """[3단계 결과] 분석 내용과 가이드를 반영한 웹 이미지 검색 계획."""

    queries: list[str] = Field(description="검색 키워드(영문 권장)")
    exclude_terms: list[str] = Field(default_factory=list, description="검색에서 제외할 단어")
    topics: list[str] = Field(default_factory=list, description="결과를 분류할 주제 폴더 후보")


class Candidate(BaseModel):
    """[4~5단계 결과] 웹에서 찾은 레퍼런스 이미지 후보 하나."""

    id: str = Field(description="후보 식별자 (사용자가 선택할 때 사용)")
    image_url: str = Field(description="이미지 주소")
    source_url: str = Field(description="이미지가 있던 페이지 주소")
    source_name: str = Field(default="", description="출처 사이트 이름")
    license: Literal["confirmed", "unclear", "restricted"] = Field(
        default="unclear", description="라이선스 확인 상태 (unclear 는 검토 대상으로 표시)"
    )
    topic: str = Field(default="", description="분류된 주제 (폴더명)")
    tags: list[str] = Field(default_factory=list, description="태그")
    reason: str = Field(default="", description="선정 이유")
    score: float = Field(default=0.0, description="요구사항·가이드와의 관련성 점수 (0~1)")


class AgentState(TypedDict, total=False):
    """그래프 전체가 공유하는 상태. total=False 라서 아직 채워지지 않은 필드는 없어도 된다."""

    # ── 입력 (POST /upload 에서 채움) ──────────────────────────
    text: str  # 사용자가 입력한 설명
    image_b64: str | None  # 첨부 이미지(base64). 없으면 None (텍스트만 입력)
    image_mime: str | None  # 첨부 이미지 MIME 타입 (예: image/png)

    # ── 처리 중간 결과 ───────────────────────────────────────
    analysis: InputAnalysis  # 입력 분석 결과
    guidelines: list[Guideline]  # RAG 로 찾은 내부 가이드
    search_plan: SearchPlan  # 웹 검색 계획
    candidates: list[Candidate]  # 사용자에게 보여줄 후보 이미지

    # ── 사용자 선택 (후보 확인 후 이어서 실행할 때 채움) ──────────
    selected_ids: list[str]  # 사용자가 승인한 후보 id

    # ── 최종 결과 ────────────────────────────────────────────
    output_dir: str  # 저장된 레퍼런스 폴더 경로
    brief_path: str  # 생성된 지시서.md 경로
    zip_path: str  # 결과 ZIP 경로

    # ── 진행 상태 ───────────────────────────────────────────
    current_step: str  # 지금 하고 있는 일 (화면 진행 표시에 사용)
    error: str | None  # 실패 시 오류 메시지
