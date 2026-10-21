"""노드를 연결해 에이전트 그래프를 만든다. 단계가 늘어나면 여기에 노드와 edge 를 추가한다."""
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph

from app.agent.intake import (
    ask_details,
    ask_type,
    classify_input,
    extract_details,
    route_after_classify,
    route_after_extract,
)
from app.agent.nodes import analyze_input, retrieve_guidelines
from app.agent.references import (
    confirm_categories,
    finalize_categories,
    plan_categories,
    search_images,
)
from app.agent.state import AgentState

builder = StateGraph(AgentState)
builder.add_node("classify_input", classify_input)
builder.add_node("ask_type", ask_type)
builder.add_node("extract_details", extract_details)
builder.add_node("ask_details", ask_details)
builder.add_node("analyze_input", analyze_input)
builder.add_node("retrieve_guidelines", retrieve_guidelines)
builder.add_node("plan_categories", plan_categories)
builder.add_node("confirm_categories", confirm_categories)
builder.add_node("finalize_categories", finalize_categories)
builder.add_node("search_images", search_images)

# 입력 확인: 종류 분류 → (불명확하면 질문) → 필수 항목 추출 → (부족하면 질문)
builder.add_edge(START, "classify_input")
builder.add_conditional_edges("classify_input", route_after_classify, ["ask_type", "extract_details"])
builder.add_edge("ask_type", "extract_details")
builder.add_conditional_edges("extract_details", route_after_extract, ["ask_details", "analyze_input"])
builder.add_edge("ask_details", "analyze_input")

# 분석 → 내부 가이드 검색 → 카테고리 제안 → 사용자 확정 → 카테고리별 이미지 검색
builder.add_edge("analyze_input", "retrieve_guidelines")
builder.add_edge("retrieve_guidelines", "plan_categories")
builder.add_edge("plan_categories", "confirm_categories")
builder.add_edge("confirm_categories", "finalize_categories")
builder.add_edge("finalize_categories", "search_images")
builder.add_edge("search_images", END)

# interrupt 로 멈춘 그래프를 이어서 실행하려면 상태를 저장하는 체크포인터가 필요하다.
# InMemorySaver 는 서버를 재시작하면 사라지므로 개발용이다. 배포 시에는 DB 기반 체크포인터로 바꾼다.
# 상태에 담기는 Pydantic 모델은 체크포인트에 저장·복원되므로 허용 목록에 등록한다.
_serde = JsonPlusSerializer(
    allowed_msgpack_modules=[
        ("app.agent.state", name)
        for name in ("InputAnalysis", "Guideline", "ReferencePlan", "ReferenceCategory", "Candidate")
    ]
)
graph = builder.compile(checkpointer=InMemorySaver(serde=_serde))
