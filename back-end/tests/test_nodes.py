import asyncio
from types import SimpleNamespace

from app.agent import nodes
from app.agent.state import Guideline, GuidelineRouting, InputAnalysis


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
