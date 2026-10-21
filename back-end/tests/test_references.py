import asyncio

from app.agent import references
from app.agent.state import (
    Candidate,
    CategoryExpansion,
    Guideline,
    InputAnalysis,
    ReferenceCategory,
    ReferencePlan,
)
from tests.fakes import FakeClient

WINTER = ReferenceCategory(name="겨울 설원 배경", reason="서식지", queries=["snowy field", "winter forest"])
COCOA = ReferenceCategory(name="코코아 소품", reason="들고 있는 소품", queries=["hot cocoa mug"])


def test_plan_categories_includes_analysis_and_guidelines_in_prompt(monkeypatch):
    plan = ReferencePlan(categories=[WINTER], exclude_terms=["cartoon"])
    client = FakeClient(plan)
    monkeypatch.setattr(references, "get_client", lambda: client)

    guide = Guideline(text="주요 색상은 최대 5색", source_type="company_rules", category="color",
                      file="01_color_rules.md", section="1. 팔레트 제한")
    state = {"analysis": InputAnalysis(subject="버섯 몬스터"), "guidelines": [guide]}
    out = asyncio.run(references.plan_categories(state))

    user_message = client.calls[0]["messages"][1]["content"]
    assert "버섯 몬스터" in user_message  # 사용자 요구사항
    assert "주요 색상은 최대 5색" in user_message  # 내부 가이드
    assert "01_color_rules.md > 1. 팔레트 제한" in user_message  # 출처 표기
    assert out["reference_plan"] is plan


def test_finalize_keeps_proposed_queries_and_expands_only_new_names(monkeypatch):
    new = ReferenceCategory(name="눈 덮인 가로등", reason="추가", queries=["snowy street lamp"])
    client = FakeClient(CategoryExpansion(categories=[new]))
    monkeypatch.setattr(references, "get_client", lambda: client)

    state = {
        "analysis": InputAnalysis(subject="버섯"),
        "reference_plan": ReferencePlan(categories=[WINTER, COCOA]),
        "confirmed_names": ["코코아 소품", "눈 덮인 가로등"],  # 겨울 설원 배경은 사용자가 뺌
    }
    out = asyncio.run(references.finalize_categories(state))

    assert [c.name for c in out["final_categories"]] == ["코코아 소품", "눈 덮인 가로등"]
    assert out["final_categories"][0].queries == ["hot cocoa mug"]  # 기존 검색어 유지
    assert out["final_categories"][1].queries == ["snowy street lamp"]
    assert "눈 덮인 가로등" in client.calls[0]["messages"][1]["content"]
    assert "코코아 소품" not in client.calls[0]["messages"][1]["content"]  # 이미 있는 카테고리는 LLM 에 보내지 않는다


def test_finalize_skips_llm_when_nothing_new(monkeypatch):
    client = FakeClient(None)
    monkeypatch.setattr(references, "get_client", lambda: client)

    state = {
        "analysis": InputAnalysis(subject="버섯"),
        "reference_plan": ReferencePlan(categories=[WINTER, COCOA]),
        "confirmed_names": ["겨울 설원 배경", "겨울 설원 배경"],  # 중복 입력도 한 번만
    }
    out = asyncio.run(references.finalize_categories(state))

    assert [c.name for c in out["final_categories"]] == ["겨울 설원 배경"]
    assert client.calls == []


def test_finalize_falls_back_to_name_when_llm_omits_category(monkeypatch):
    client = FakeClient(CategoryExpansion(categories=[]))  # LLM 이 새 카테고리를 빠뜨림
    monkeypatch.setattr(references, "get_client", lambda: client)

    state = {
        "analysis": InputAnalysis(subject="버섯"),
        "reference_plan": ReferencePlan(categories=[WINTER]),
        "confirmed_names": ["snowman"],
    }
    out = asyncio.run(references.finalize_categories(state))

    assert out["final_categories"][0].queries == ["snowman"]  # 이름 자체를 검색어로 사용


class FakeSource:
    def __init__(self, name, results):
        self.name = name
        self._results = results  # {검색어: [Candidate]}

    async def search(self, client, query, limit):
        if self._results is None:
            raise TimeoutError
        return self._results.get(query, [])


def cand(url, license="confirmed", title=""):
    return Candidate(id=url, image_url=url, source_url=url, license=license, title=title)


def test_search_images_groups_by_category_and_survives_failing_source(monkeypatch):
    good = FakeSource("Good", {
        "snowy field": [cand("a1"), cand("a2")],
        "hot cocoa mug": [cand("a1"), cand("c1")],  # a1 은 첫 카테고리에서 이미 사용됨
    })
    bad = FakeSource("Bad", None)
    monkeypatch.setattr(references, "DEFAULT_SOURCES", [good, bad])

    state = {
        "final_categories": [WINTER, COCOA],
        "reference_plan": ReferencePlan(categories=[WINTER, COCOA]),
    }
    out = asyncio.run(references.search_images(state))

    assert [(c.topic, c.image_url) for c in out["candidates"]] == [
        ("겨울 설원 배경", "a1"), ("겨울 설원 배경", "a2"), ("코코아 소품", "c1"),
    ]
    assert out["source_errors"] == ["Bad: TimeoutError"]  # 실패한 출처를 알려준다


def test_search_images_applies_exclude_terms(monkeypatch):
    src = FakeSource("S", {"snowy field": [cand("a1", title="Cartoon snow"), cand("a2", title="Snow field")]})
    monkeypatch.setattr(references, "DEFAULT_SOURCES", [src])

    state = {
        "final_categories": [WINTER],
        "reference_plan": ReferencePlan(categories=[WINTER], exclude_terms=["cartoon"]),
    }
    out = asyncio.run(references.search_images(state))

    assert [c.image_url for c in out["candidates"]] == ["a2"]
