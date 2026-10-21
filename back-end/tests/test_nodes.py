import asyncio
from app.agent import nodes
from tests.fakes import FakeClient
from app.agent.state import Guideline, GuidelineRouting, InputAnalysis


def test_analyze_input_sends_image_when_present(monkeypatch):
    analysis = InputAnalysis(subject="숲속 마을")
    client = FakeClient(analysis)
    monkeypatch.setattr(nodes, "get_client", lambda: client)

    out = asyncio.run(nodes.analyze_input({"text": "숲", "image_b64": "AAAA", "image_mime": "image/png"}))

    content = client.calls[0]["messages"][1]["content"]
    assert [part["type"] for part in content] == ["text", "image_url"]
    assert content[1]["image_url"]["url"] == "data:image/png;base64,AAAA"
    assert out["analysis"] is analysis


def test_analyze_input_text_only(monkeypatch):
    client = FakeClient(InputAnalysis(subject="숲"))
    monkeypatch.setattr(nodes, "get_client", lambda: client)

    asyncio.run(nodes.analyze_input({"text": "숲", "image_b64": None, "image_mime": None}))

    content = client.calls[0]["messages"][1]["content"]
    assert [part["type"] for part in content] == ["text"]


def test_retrieve_guidelines_uses_routed_categories(monkeypatch):
    client = FakeClient(GuidelineRouting(categories=["monster", "color"]))
    monkeypatch.setattr(nodes, "get_client", lambda: client)

    found = [Guideline(text="t", source_type="company_rules", category="color", file="f.md", section="s")]
    seen = {}

    async def fake_search(query, categories):
        seen["categories"] = categories
        return found

    monkeypatch.setattr(nodes, "search_guidelines", fake_search)

    state = {"text": "늑대 몬스터", "analysis": InputAnalysis(subject="늑대", mood=["어두운"])}
    out = asyncio.run(nodes.retrieve_guidelines(state))

    assert seen["categories"] == ["monster", "color"]
    assert out["guidelines"] == found


def test_analysis_prompt_separates_goal_from_current_image():
    # 이미지의 역할(바꿀 원본 / 맥락 자료)과 최종 목표 기준으로 채우라는 지시가 프롬프트에 있어야 한다
    assert "goal" in nodes.ANALYSIS_PROMPT
    assert "최종적으로 원하는 결과" in nodes.ANALYSIS_PROMPT
    assert "바꿀 원본" in nodes.ANALYSIS_PROMPT and "맥락 자료" in nodes.ANALYSIS_PROMPT
