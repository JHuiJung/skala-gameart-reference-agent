"""그래프의 각 단계(노드) 함수. 노드는 상태를 받아 자기 단계가 채우는 필드만 반환한다."""
from app.agent.checklist import CHECKLISTS, TYPE_LABELS, UNDECIDED
from app.agent.llm import ANALYSIS_MODEL, ROUTER_MODEL, get_client
from app.agent.retriever import search_guidelines
from app.agent.state import AgentState, GuidelineRouting, InputAnalysis

ANALYSIS_PROMPT = """너는 게임 아트팀의 레퍼런스 조사를 돕는 분석가다.
사용자의 설명(과 첨부 이미지)을 읽고, 아트 레퍼런스 검색에 필요한 요구사항을 구조화해라.

첨부 이미지는 역할이 다를 수 있다. 텍스트의 지시를 보고 판단해라.
- 바꿀 원본: "이걸 ~ 버전으로 바꾸고 싶다" → 이미지의 현재 모습은 변경 전이다.
- 맥락 자료: "여기에 어울리는 ~를 디자인해줘" → 이미지(예: 배경)에 어울리는 새 대상을 만드는 것이다.
- 분위기·형태 참고: 이미지의 느낌을 따라간다.

각 항목은 이미지의 현재 모습이 아니라 **사용자가 최종적으로 원하는 결과** 기준으로 채워라.
- goal: 사용자가 원하는 것을 한 문장으로. 변경·변형 요구와 이미지의 역할을 반드시 포함해라.
  (예: "따뜻한 지역의 몬스터를 차가운 지역에서 사는 버전으로 바꾼다")
- subject: 최종적으로 만들려는 대상
- mood / materials / colors: 최종 결과의 분위기, 재질, 색상 키워드 (변경 요구가 있으면 변경된 모습 기준)
- composition: 구도·시점 (알 수 없으면 빈 문자열)
- exclude: 사용자가 원하지 않는다고 말한 요소
- summary: 이미지가 있으면 이미지의 현재 모습을 2~3문장으로 요약, 없으면 빈 문자열
입력에 없는 내용을 지어내지 말고, 모르는 항목은 비워둬라."""

ROUTER_PROMPT = """사용자 요청을 보고, 참고해야 할 내부 가이드 카테고리를 골라라.
- 기획(확정된 내용): world(세계관·시대·지역), mood(분위기·아트 방향), background(배경·공간), monster(몬스터), costume(의상·소재), prop(소품·아이템)
- 회사 규정(제작 제한): color(색상), modeling(폴리곤·LOD), texture(해상도·용량), naming(네이밍·납품)
요청과 직접 관련된 카테고리만 골라라. 대상이 몬스터·캐릭터·건물처럼 3D 제작물이면 규정 카테고리(color, modeling, texture)도 포함해라."""

def _with_intake(state: AgentState) -> str:
    """사용자 입력 뒤에 확인된 에셋 종류와 필수 항목을 붙인다. ('미정' 항목은 제외)"""
    lines = [state["text"]]
    asset_type = state.get("asset_type")
    if asset_type in TYPE_LABELS:
        lines.append(f"\n[에셋 종류] {TYPE_LABELS[asset_type]}")
        for item in CHECKLISTS[asset_type]:
            value = state.get("details", {}).get(item.key)
            if value and value != UNDECIDED:
                lines.append(f"- {item.label}: {value}")
    return "\n".join(lines)


async def analyze_input(state: AgentState) -> dict:
    """[1단계] 텍스트/이미지 입력을 멀티모달 LLM 으로 분석해 InputAnalysis 로 만든다."""
    content: list[dict] = [{"type": "text", "text": _with_intake(state)}]
    if state.get("image_b64"):
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{state['image_mime']};base64,{state['image_b64']}"},
        })

    completion = await get_client().chat.completions.parse(
        model=ANALYSIS_MODEL,
        messages=[
            {"role": "system", "content": ANALYSIS_PROMPT},
            {"role": "user", "content": content},
        ],
        response_format=InputAnalysis,
    )
    return {"analysis": completion.choices[0].message.parsed, "current_step": "입력 분석"}


async def retrieve_guidelines(state: AgentState) -> dict:
    """[2단계] 분석 결과에 맞는 카테고리를 고른 뒤, 그 범위 안에서 내부 가이드를 검색한다 (RAG)."""
    a = state["analysis"]
    query = " ".join([a.subject, *a.mood, *a.materials, *a.colors, a.composition, state["text"]])

    routing = await get_client().chat.completions.parse(
        model=ROUTER_MODEL,
        messages=[
            {"role": "system", "content": ROUTER_PROMPT},
            {"role": "user", "content": query},
        ],
        response_format=GuidelineRouting,
    )
    categories = routing.choices[0].message.parsed.categories

    guidelines = await search_guidelines(query, categories)
    return {"guidelines": guidelines, "current_step": "내부 가이드 검색"}
