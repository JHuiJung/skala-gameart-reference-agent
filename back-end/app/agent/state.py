"""LangGraph 에이전트가 노드 사이에서 주고받는 상태(State) 정의.
  입력 → 종류·필수 항목 확인 → analysis → guidelines → 카테고리 제안·확정 → candidates → 결과 파일
각 노드는 자기 단계의 필드만 채워서 반환하고, LangGraph 가 나머지 필드와 합쳐 준다.
"""
from typing import Literal, TypedDict

from pydantic import BaseModel, Field


class AssetClassification(BaseModel):
    """[0단계 결과] 사용자 입력이 어떤 종류의 에셋을 만들려는 것인지 분류한 결과."""

    asset_type: Literal["character", "background", "prop", "ui", "unknown"] = Field(
        description="character(캐릭터·몬스터·NPC), background(배경·맵·지형), prop(소품·아이템), ui, 판단 불가면 unknown"
    )


class ExtractedField(BaseModel):
    """입력에서 찾아낸 체크리스트 항목 하나."""

    key: str = Field(description="체크리스트 항목 key")
    value: str = Field(description="입력에 명시된 내용. 입력에 없으면 빈 문자열")


class ExtractedDetails(BaseModel):
    """[0단계 결과] 입력 텍스트/이미지에서 종류별 필수 항목을 추출한 결과."""

    items: list[ExtractedField]


class Option(BaseModel):
    """사용자가 고를 수 있는 선택지 하나."""

    value: str
    label: str


class Question(BaseModel):
    """에이전트가 사용자에게 되묻는 질문 하나. (API 응답으로 그대로 전달된다)"""

    key: str = Field(description="답변을 돌려받을 때 쓰는 항목 key")
    label: str = Field(description="항목 이름 (예: 의상)")
    question: str = Field(description="사용자에게 보여줄 질문")
    hint: str = Field(default="", description="무엇을 적으면 되는지 예시")
    options: list[Option] = Field(default_factory=list, description="선택지가 있으면 채운다")


class InputAnalysis(BaseModel):
    """[1단계 결과] 멀티모달 LLM 이 사용자 입력(텍스트/이미지)을 구조화한 내용."""

    goal: str = Field(default="", description="사용자가 이번 작업에서 최종적으로 원하는 것 한 문장 (변경·변형 요구, 이미지의 역할 포함)")
    subject: str = Field(description="최종적으로 만들려는 대상 (예: 숲속 목조 마을)")
    mood: list[str] = Field(default_factory=list, description="분위기 키워드")
    materials: list[str] = Field(default_factory=list, description="재질")
    colors: list[str] = Field(default_factory=list, description="색상")
    composition: str = Field(default="", description="구도·시점")
    exclude: list[str] = Field(default_factory=list, description="제외할 요소")
    summary: str = Field(default="", description="첨부 이미지의 현재 모습 요약 (최종 목표와 다를 수 있음)")


class Guideline(BaseModel):
    """[2단계 결과] RAG 로 찾은 내부 가이드 한 조각 (vector_db 의 청크 하나)."""

    text: str = Field(description="가이드 본문")
    source_type: str = Field(description="confirmed_plans(확정된 기획) | company_rules(회사 규정)")
    category: str = Field(description="world, monster, color, modeling 등")
    file: str = Field(description="출처 문서 파일명")
    section: str = Field(description="문서 안의 섹션 제목")


class GuidelineRouting(BaseModel):
    """[2단계 중간 결과] 입력에 관련된 내부 가이드 카테고리를 LLM 이 고른 것."""

    categories: list[
        Literal["world", "mood", "background", "monster", "costume", "prop", "color", "modeling", "texture", "naming"]
    ] = Field(
        description="검색할 가이드 카테고리"
    )


class ReferenceCategory(BaseModel):
    """[3단계] 레퍼런스를 찾을 카테고리 하나 (예: 겨울 배경, 방한 의상, 코코아 소품)."""

    name: str = Field(description="사용자에게 보여줄 카테고리 이름 (한국어, 짧게)")
    reason: str = Field(default="", description="이 카테고리가 왜 필요한지 한 문장")
    queries: list[str] = Field(default_factory=list, description="이미지 검색 키워드 2~3개 (영문)")
    applied_rules: list[str] = Field(
        default_factory=list, description="검색어에 반영한 세계관·기획 가이드 규칙 (짧은 한국어 문장, 가이드에 있는 내용만)"
    )


class ReferencePlan(BaseModel):
    """[3단계 결과] AI 가 제안하는 레퍼런스 카테고리 목록. 사용자가 확인·수정하기 전의 초안이다."""

    categories: list[ReferenceCategory] = Field(description="레퍼런스 카테고리 4~6개")
    exclude_terms: list[str] = Field(default_factory=list, description="검색에서 제외할 단어 (모든 카테고리 공통)")


class GroundedCategories(BaseModel):
    """[3-1단계 결과] 세계관·기획 가이드를 반영해 다시 쓴 카테고리 검색어와, 가이드가 금지한 제외어."""

    categories: list[ReferenceCategory]
    era_keyword: str = Field(
        default="", description="세계관 공통 가이드의 시대 기준을 나타내는 가장 짧고 일반적인 영문 키워드 하나 (예: medieval). 없으면 빈 문자열"
    )
    exclude_terms: list[str] = Field(default_factory=list, description="가이드가 금지한 요소 (영문 검색 제외어)")


class CategoryExpansion(BaseModel):
    """사용자가 새로 추가한 카테고리에 대해 LLM 이 만든 이유와 검색 키워드."""

    categories: list[ReferenceCategory]


class Candidate(BaseModel):
    """[4~5단계 결과] 웹에서 찾은 레퍼런스 이미지 후보 하나."""

    id: str = Field(description="후보 식별자 (사용자가 선택할 때 사용)")
    image_url: str = Field(description="이미지 주소")
    source_url: str = Field(description="이미지가 있던 페이지 주소")
    source_name: str = Field(default="", description="출처 사이트 이름")
    thumbnail_url: str = Field(default="", description="화면 표시용 작은 이미지 주소")
    license: Literal["confirmed", "unclear", "restricted"] = Field(
        default="unclear", description="라이선스 확인 상태 (unclear 는 검토 대상으로 표시)"
    )
    license_detail: str = Field(default="", description="라이선스 이름 (예: CC BY 2.0, Public domain)")
    creator: str = Field(default="", description="저작자 (표기 의무가 있는 라이선스에 필요)")
    title: str = Field(default="", description="이미지 제목")
    topic: str = Field(default="", description="이 이미지를 찾은 레퍼런스 카테고리 이름")
    tags: list[str] = Field(default_factory=list, description="태그")
    reason: str = Field(default="", description="선정 이유")
    score: float | None = Field(default=None, description="이미지 검토 점수 (0~1). 검토하지 못했으면 None")
    review: str = Field(default="", description="이미지 검토 결과 한 줄 (적합하거나 부적합한 이유)")


class ImageVerdict(BaseModel):
    """이미지 한 장에 대한 검토 결과."""

    index: int = Field(description="입력에서 붙인 이미지 번호")
    score: int = Field(ge=0, le=10, description="적합도 0~10")
    reason: str = Field(description="점수의 이유 한 문장 (한국어)")


class ImageReview(BaseModel):
    """[4-1단계 결과] 비전 모델이 후보 이미지들을 검토한 결과."""

    verdicts: list[ImageVerdict]


class BriefSection(BaseModel):
    """[5단계] 지시서의 한 섹션에 '무엇을 쓸지'에 대한 계획. 사용자가 확인하고 수정할 수 있다."""

    heading: str = Field(description="섹션 제목")
    outline: str = Field(description="이 섹션에 쓸 내용 요약 (2~4줄). 본문이 아니라 계획이다")


class BriefPlan(BaseModel):
    """[5단계 결과] 지시서 작성 계획 (섹션 목록)."""

    sections: list[BriefSection]


class BriefSectionBody(BaseModel):
    """지시서 한 섹션의 본문."""

    heading: str = Field(description="승인된 계획의 섹션 제목 그대로")
    body: str = Field(description="마크다운 본문")


class ImageUsage(BaseModel):
    """선택한 레퍼런스 이미지 한 장을 어떤 목적으로 참고하는지."""

    id: str = Field(description="이미지 id")
    usage: str = Field(description="활용 목적 한 문장 (한국어)")


class BriefDraft(BaseModel):
    """[6단계 결과] LLM 이 쓴 지시서 본문과 이미지별 활용 목적."""

    sections: list[BriefSectionBody]
    image_usage: list[ImageUsage]


class SavedReference(BaseModel):
    """선택한 레퍼런스 이미지 하나의 저장 결과."""

    candidate: Candidate
    file: str | None = Field(default=None, description="저장한 파일의 결과 폴더 기준 상대 경로. 저장하지 않았으면 None")
    status: Literal["saved", "link_only", "failed"] = Field(description="saved 저장됨 / link_only 링크만 기록 / failed 저장 실패")
    note: str = Field(default="", description="파일로 저장하지 않은 이유")
    usage: str = Field(default="", description="활용 목적")


class AgentState(TypedDict, total=False):
    """그래프 전체가 공유하는 상태. total=False 라서 아직 채워지지 않은 필드는 없어도 된다."""

    # ── 입력 (POST /upload 에서 채움) ──────────────────────────
    text: str  # 사용자가 입력한 설명
    image_b64: str | None  # 첨부 이미지(base64). 없으면 None (텍스트만 입력)
    image_mime: str | None  # 첨부 이미지 MIME 타입 (예: image/png)

    # ── 입력 확인 (종류 분류 + 필수 항목 점검) ───────────────────
    asset_type: str  # character | background | prop | ui | unknown(분류 불가, 사용자에게 되묻는다)
    details: dict[str, str]  # 종류별 필수 항목의 값. 사용자가 답하지 않은 항목은 "미정"

    # ── 처리 중간 결과 ───────────────────────────────────────
    analysis: InputAnalysis  # 입력 분석 결과
    guidelines: list[Guideline]  # RAG 로 찾은 내부 가이드
    reference_plan: ReferencePlan  # AI 가 제안한 레퍼런스 카테고리 초안
    confirmed_names: list[str]  # 사용자가 확인·수정해서 확정한 카테고리 이름
    per_category: int  # 사용자가 고른 카테고리당 이미지 수 (1~10)
    final_categories: list[ReferenceCategory]  # 확정된 카테고리 (검색 키워드 포함) - 이것으로 검색한다
    candidates: list[Candidate]  # 사용자에게 보여줄 후보 이미지 (이미지 검토를 통과한 것)
    rejected_candidates: list[Candidate]  # 이미지 검토에서 부적합으로 걸러진 후보 (이유 확인용)
    source_errors: list[str]  # 검색 출처 중 실패한 곳 (일부 실패해도 나머지 결과로 진행)

    # ── 사용자 선택 (후보 확인 후 이어서 실행할 때 채움) ──────────
    selected_ids: list[str]  # 사용자가 클릭해서 고른 후보 id

    # ── 지시서 작성 ───────────────────────────────────────────
    save_unverified: bool  # 라이선스가 확인되지 않은 이미지도 파일로 저장할지 (사용자가 선택)
    rule_guides: list[Guideline]  # 지시서에 반영할 회사 규정
    brief_plan: BriefPlan  # 지시서 작성 계획 (사용자가 승인한 것)
    brief_notes: str  # 사용자가 지시서 작성에 추가로 요청한 내용
    saved_refs: list[SavedReference]  # 선택한 이미지의 저장 결과

    # ── 최종 결과 ────────────────────────────────────────────
    output_dir: str  # 저장된 결과 폴더 경로 (예: .../result/artBrief_001)
    brief_path: str  # 생성된 지시서.md 경로
    brief_markdown: str  # 지시서 내용 (화면 미리보기용)

    # ── 진행 상태 ───────────────────────────────────────────
    current_step: str  # 지금 하고 있는 일 (화면 진행 표시에 사용)
    error: str | None  # 실패 시 오류 메시지
