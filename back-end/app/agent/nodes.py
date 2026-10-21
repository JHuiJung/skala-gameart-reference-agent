"""그래프의 각 단계(노드) 함수. 노드는 상태를 받아 자기 단계가 채우는 필드만 반환한다."""
from openai import AsyncOpenAI

from app.agent.state import AgentState, InputAnalysis

ANALYSIS_MODEL = "gpt-4o-mini"  # 이미지 입력을 지원하는 모델

ANALYSIS_PROMPT = """너는 게임 아트팀의 레퍼런스 조사를 돕는 분석가다.
사용자의 설명(과 첨부 이미지)을 읽고, 아트 레퍼런스 검색에 필요한 요구사항을 구조화해라.
- subject: 만들려는 대상
- mood / materials / colors: 분위기, 재질, 색상 키워드
- composition: 구도·시점 (알 수 없으면 빈 문자열)
- exclude: 사용자가 원하지 않는다고 말한 요소
- summary: 이미지가 있으면 시각적 특징을 2~3문장으로 요약, 없으면 빈 문자열
입력에 없는 내용을 지어내지 말고, 모르는 항목은 비워둬라."""

_client = AsyncOpenAI()  # OPENAI_API_KEY 환경변수 사용


async def analyze_input(state: AgentState) -> dict:
    """[1단계] 텍스트/이미지 입력을 멀티모달 LLM 으로 분석해 InputAnalysis 로 만든다."""
    content: list[dict] = [{"type": "text", "text": state["text"]}]
    if state.get("image_b64"):
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:{state['image_mime']};base64,{state['image_b64']}"},
        })

    completion = await _client.chat.completions.parse(
        model=ANALYSIS_MODEL,
        messages=[
            {"role": "system", "content": ANALYSIS_PROMPT},
            {"role": "user", "content": content},
        ],
        response_format=InputAnalysis,
    )
    return {"analysis": completion.choices[0].message.parsed, "current_step": "입력 분석"}
