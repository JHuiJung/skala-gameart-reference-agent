import asyncio
from types import SimpleNamespace

from app.agent import nodes
from app.agent.state import Guideline, GuidelineRouting, InputAnalysis, SearchPlan


class FakeClient:
    """OpenAI 클라이언트 대역. 호출 인자를 기록하고 미리 정한 결과를 돌려준다."""

    def __init__(self, parsed):
        self.calls = []
        self._parsed = parsed
        self.chat = SimpleNamespace(completions=SimpleNamespace(parse=self._parse))

    async def _parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=self._parsed))])


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


def test_plan_search_includes_analysis_and_guidelines_in_prompt(monkeypatch):
    plan = SearchPlan(queries=["moss wolf"], exclude_terms=["cartoon"], topics=["anatomy"])
    client = FakeClient(plan)
    monkeypatch.setattr(nodes, "get_client", lambda: client)

    guide = Guideline(text="주요 색상은 최대 5색", source_type="company_rules", category="color",
                      file="01_color_rules.md", section="1. 팔레트 제한")
    state = {"analysis": InputAnalysis(subject="이끼 늑대"), "guidelines": [guide]}
    out = asyncio.run(nodes.plan_search(state))

    user_message = client.calls[0]["messages"][1]["content"]
    assert "이끼 늑대" in user_message  # 사용자 요구사항
    assert "주요 색상은 최대 5색" in user_message  # 내부 가이드
    assert "01_color_rules.md > 1. 팔레트 제한" in user_message  # 출처 표기
    assert out["search_plan"] is plan


def test_plan_search_works_without_guidelines(monkeypatch):
    client = FakeClient(SearchPlan(queries=["forest"]))
    monkeypatch.setattr(nodes, "get_client", lambda: client)

    out = asyncio.run(nodes.plan_search({"analysis": InputAnalysis(subject="숲")}))

    assert out["search_plan"].queries == ["forest"]
