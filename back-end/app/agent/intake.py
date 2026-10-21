"""입력 확인 단계: 에셋 종류를 분류하고, 종류별 필수 항목이 입력에 있는지 점검해 없으면 사용자에게 되묻는다.

흐름: classify_input → (unknown 이면 ask_type) → extract_details → (부족하면 ask_details) → 이후 단계
되묻는 노드는 LangGraph 의 interrupt 로 그래프를 멈추고, 사용자의 답을 받으면 이어서 실행된다.
"""
from langgraph.types import interrupt

from app.agent.checklist import CHECKLISTS, TYPE_LABELS, UNDECIDED
from app.agent.llm import INTAKE_MODEL, get_client
from app.agent.state import AgentState, AssetClassification, ExtractedDetails, Option, Question

CLASSIFY_PROMPT = """사용자가 만들려는 게임 아트 에셋의 종류를 분류해라.
- character: 인물, 몬스터, NPC 등 생명체 캐릭터
- background: 맵, 지형, 마을, 건축물 등 공간·배경
- prop: 소품, 아이템, 장비 등 단독 오브젝트
- ui: 버튼, 아이콘, HUD, 메뉴 등 인터페이스
텍스트에서 종류를 알 수 있는 단서(대상, 용도)가 없으면 unknown 으로 답해라.
분위기·색감만 말한 입력이나 이미지 하나만으로는 종류를 단정하지 마라. 추측하지 마라."""

EXTRACT_PROMPT = """사용자 입력(텍스트와 첨부 이미지)에서 아래 항목에 해당하는 내용을 찾아라.
- 입력에 명시되었거나 이미지에서 분명히 보이는 내용만 적어라. 추측하거나 지어내지 마라.
- 해당 내용이 없으면 value 는 빈 문자열로 둬라.
- 모든 항목을 빠짐없이 items 에 포함해라.

항목(key: 이름 - 설명):
{checklist}"""


def _user_content(state: AgentState) -> list[dict]:
    """텍스트와 (있으면) 이미지를 LLM 입력 형식으로 만든다."""
    content: list[dict] = [{"type": "text", "text": state["text"]}]
    if state.get("image_b64"):
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{state['image_mime']};base64,{state['image_b64']}"},
        })
    return content


async def classify_input(state: AgentState) -> dict:
    """[0-1단계] 입력이 캐릭터/배경/소품/UI 중 무엇인지 분류한다."""
    completion = await get_client().chat.completions.parse(
        model=INTAKE_MODEL,
        messages=[
            {"role": "system", "content": CLASSIFY_PROMPT},
            {"role": "user", "content": _user_content(state)},
        ],
        response_format=AssetClassification,
    )
    return {"asset_type": completion.choices[0].message.parsed.asset_type, "current_step": "에셋 종류 분류"}


def route_after_classify(state: AgentState) -> str:
    """분류가 안 됐으면 사용자에게 종류를 묻고, 됐으면 바로 항목 추출로 간다."""
    return "ask_type" if state["asset_type"] == "unknown" else "extract_details"


def ask_type(state: AgentState) -> dict:
    """[0-1단계] 종류를 판단하지 못했을 때 사용자에게 고르게 한다."""
    question = Question(
        key="asset_type",
        label="에셋 종류",
        question="어떤 종류의 에셋을 만들까요?",
        options=[Option(value=k, label=v) for k, v in TYPE_LABELS.items()],
    )
    while True:  # 선택지 밖의 답이 오면 다시 묻는다 (사용자가 답해야만 다음으로 진행)
        answers = interrupt({"kind": "questions", "questions": [question.model_dump()]})
        chosen = (answers.get("asset_type") or "").strip()
        if chosen in TYPE_LABELS:
            return {"asset_type": chosen, "current_step": "에셋 종류 확인"}


async def extract_details(state: AgentState) -> dict:
    """[0-2단계] 종류별 필수 항목이 입력에 있는지 찾아서 채운다. 못 찾은 항목은 값이 비어 있다."""
    items = CHECKLISTS[state["asset_type"]]
    checklist = "\n".join(f"- {i.key}: {i.label} - {i.hint}" for i in items)
    completion = await get_client().chat.completions.parse(
        model=INTAKE_MODEL,
        messages=[
            {"role": "system", "content": EXTRACT_PROMPT.format(checklist=checklist)},
            {"role": "user", "content": _user_content(state)},
        ],
        response_format=ExtractedDetails,
    )
    found = {f.key: f.value.strip() for f in completion.choices[0].message.parsed.items}
    # 체크리스트에 없는 key 는 버린다 (LLM 이 임의로 만든 항목 방지)
    details = {i.key: found.get(i.key, "") for i in items}
    return {"details": details, "current_step": "필수 항목 확인"}


def missing_items(state: AgentState):
    """입력에서 값을 찾지 못한 체크리스트 항목."""
    return [i for i in CHECKLISTS[state["asset_type"]] if not state["details"].get(i.key)]


def route_after_extract(state: AgentState) -> str:
    """빠진 항목이 있으면 사용자에게 묻고, 없으면 다음 단계(입력 분석)로 간다."""
    return "ask_details" if missing_items(state) else "analyze_input"


def ask_details(state: AgentState) -> dict:
    """[0-3단계] 빠진 항목을 사용자에게 되묻는다. 답하지 않은 항목은 '미정'으로 표시하고 계속 진행한다."""
    missing = missing_items(state)
    questions = [
        Question(key=i.key, label=i.label, question=i.question, hint=i.hint) for i in missing
    ]
    answers = interrupt({"kind": "questions", "questions": [q.model_dump() for q in questions]})

    details = dict(state["details"])
    for i in missing:
        details[i.key] = (answers.get(i.key) or "").strip() or UNDECIDED
    return {"details": details, "current_step": "필수 항목 입력"}
