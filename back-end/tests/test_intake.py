import asyncio

import pytest

from app.agent import intake, nodes, references, runner
from app.agent.checklist import CHECKLISTS, UNDECIDED
from app.agent.state import (
    AssetClassification,
    ExtractedDetails,
    ExtractedField,
    Guideline,
    GuidelineRouting,
    Candidate,
    InputAnalysis,
    ReferenceCategory,
    ReferencePlan,
)
from tests.fakes import FakeClient


CATEGORY = ReferenceCategory(name="배경", reason="r", queries=["snowy field"])


def extracted(**values):
    return ExtractedDetails(items=[ExtractedField(key=k, value=v) for k, v in values.items()])


def test_every_type_has_unique_checklist_keys():
    assert set(CHECKLISTS) == {"character", "background", "prop", "ui"}
    for items in CHECKLISTS.values():
        keys = [i.key for i in items]
        assert items and len(keys) == len(set(keys))


def test_route_after_classify():
    assert intake.route_after_classify({"asset_type": "unknown"}) == "ask_type"
    assert intake.route_after_classify({"asset_type": "prop"}) == "extract_details"


def test_missing_items_and_route_after_extract():
    state = {"asset_type": "prop", "details": {"scale": "허리 높이", "function": "", "interaction": ""}}
    assert [i.key for i in intake.missing_items(state)] == ["function", "interaction"]
    assert intake.route_after_extract(state) == "ask_details"

    state["details"] = {"scale": "a", "function": "b", "interaction": "c"}
    assert intake.route_after_extract(state) == "analyze_input"


def test_extract_details_drops_unknown_keys_and_fills_missing(monkeypatch):
    # LLM 이 체크리스트에 없는 key 를 만들어 내고 일부 항목은 빠뜨려도 결과는 체크리스트 기준이어야 한다
    client = FakeClient(extracted(scale="허리 높이", made_up="무시되어야 함"))
    monkeypatch.setattr(intake, "get_client", lambda: client)

    out = asyncio.run(intake.extract_details({"text": "소품", "asset_type": "prop"}))

    assert out["details"] == {"scale": "허리 높이", "function": "", "interaction": ""}
    # 프롬프트에는 해당 종류의 항목만 들어간다
    assert "상호작용 여부" in client.calls[0]["messages"][0]["content"]


# ── 그래프 전체 흐름 (OpenAI 는 대역, interrupt/resume 은 실제 동작) ──────────────

@pytest.fixture
def fake_llm(monkeypatch):
    def install(classification, details):
        client = FakeClient({
            AssetClassification: AssetClassification(asset_type=classification),
            type(details): details,
            InputAnalysis: InputAnalysis(subject="테스트 대상"),
            GuidelineRouting: GuidelineRouting(categories=["monster"]),
            ReferencePlan: ReferencePlan(categories=[CATEGORY], exclude_terms=["cartoon"]),
        })
        monkeypatch.setattr(intake, "get_client", lambda: client)
        monkeypatch.setattr(nodes, "get_client", lambda: client)
        monkeypatch.setattr(references, "get_client", lambda: client)

        async def fake_search(query, categories):
            return [Guideline(text="t", source_type="company_rules", category="color", file="f.md", section="s")]

        monkeypatch.setattr(nodes, "search_guidelines", fake_search)

        class FakeSource:
            name = "Fake"

            async def search(self, http, query, limit):
                return [Candidate(id=query, image_url=f"https://img/{query}", source_url="https://s")]

        monkeypatch.setattr(references, "DEFAULT_SOURCES", [FakeSource()])
        return client

    return install


def start_state():
    return {"text": "입력", "image_b64": None, "image_mime": None}


def test_complete_input_goes_straight_to_category_proposal(fake_llm):
    fake_llm("prop", extracted(scale="a", function="b", interaction="c"))
    result = asyncio.run(runner.start(start_state()))

    # 필수 항목 질문 없이 분석·가이드 검색을 거쳐 카테고리 확인에서 멈춘다
    assert result.status == "needs_input" and result.kind == "confirm_categories"
    assert result.asset_type == "prop"
    assert [c.name for c in result.proposed_categories] == ["배경"]


def test_missing_items_are_asked_then_unanswered_become_undecided(fake_llm):
    fake_llm("prop", extracted(scale="허리 높이"))

    async def flow():
        first = await runner.start(start_state())
        second = await runner.resume(first.thread_id, {"function": "조명"}, None)  # interaction 은 답하지 않음
        return first, second

    first, second = asyncio.run(flow())

    assert first.kind == "questions" and [q.key for q in first.questions] == ["function", "interaction"]
    assert second.kind == "confirm_categories"  # 질문 답변 후 다음 단계(카테고리 제안)로 진행
    assert second.details == {"scale": "허리 높이", "function": "조명", "interaction": UNDECIDED}


def test_unknown_type_asks_type_first(fake_llm):
    fake_llm("unknown", extracted(scale="a", function="b", interaction="c"))

    async def flow():
        first = await runner.start(start_state())
        second = await runner.resume(first.thread_id, {"asset_type": "prop"}, None)
        return first, second

    first, second = asyncio.run(flow())

    assert first.status == "needs_input" and first.asset_type == "unknown"
    assert [q.key for q in first.questions] == ["asset_type"]
    assert {o.value for o in first.questions[0].options} == {"character", "background", "prop", "ui"}
    assert second.asset_type == "prop" and second.kind == "confirm_categories"


def test_full_flow_confirm_categories_then_search(fake_llm):
    fake_llm("prop", extracted(scale="a", function="b", interaction="c"))

    async def flow():
        first = await runner.start(start_state())
        return await runner.resume(first.thread_id, {}, ["배경"])

    done = asyncio.run(flow())

    assert done.status == "done"
    assert done.analysis.subject == "테스트 대상"
    assert [c.name for c in done.categories] == ["배경"]
    assert [(c.topic, c.image_url) for c in done.candidates] == [("배경", "https://img/snowy field")]
    assert done.exclude_terms == ["cartoon"]


def test_wrong_answer_kind_is_rejected(fake_llm):
    fake_llm("prop", extracted(scale="a", function="b", interaction="c"))

    async def flow(answers, categories):
        first = await runner.start(start_state())  # 카테고리 확정을 기다리는 상태
        await runner.resume(first.thread_id, answers, categories)

    with pytest.raises(runner.WrongAnswerKind):
        asyncio.run(flow({"scale": "x"}, None))  # 질문 답변을 보냄


def test_resume_twice_is_rejected(fake_llm):
    fake_llm("prop", extracted(scale="a", function="b", interaction="c"))

    async def flow():
        first = await runner.start(start_state())
        await runner.resume(first.thread_id, {}, ["배경"])  # 끝까지 실행됨
        await runner.resume(first.thread_id, {}, ["배경"])  # 이미 끝난 작업

    with pytest.raises(runner.ThreadNotWaiting):
        asyncio.run(flow())
