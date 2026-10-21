import asyncio

from app.agent import references
from app.agent.state import (
    Candidate,
    CategoryExpansion,
    GroundedCategories,
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
    state = {
        "text": "차가운 지역 버전으로 바꾸고 싶어",
        "analysis": InputAnalysis(goal="차가운 지역 버전으로 변경", subject="버섯 몬스터"),
        "guidelines": [guide],
    }
    out = asyncio.run(references.plan_categories(state))

    user_message = client.calls[0]["messages"][1]["content"]
    assert "차가운 지역 버전으로 바꾸고 싶어" in user_message  # 사용자 요청 원문 (분석 과정에서 지시가 사라지지 않도록)
    assert "차가운 지역 버전으로 변경" in user_message  # 최종 목표
    assert "버섯 몬스터" in user_message  # 분석된 요구사항
    assert "주요 색상은 최대 5색" in user_message  # 내부 가이드
    assert "01_color_rules.md > 1. 팔레트 제한" in user_message  # 출처 표기
    assert out["reference_plan"] is plan


def test_confirm_payload_includes_goal_and_applied_rules(monkeypatch):
    captured = {}

    def fake_interrupt(payload):
        captured.update(payload)
        return {"categories": ["겨울 설원 배경"]}

    monkeypatch.setattr(references, "interrupt", fake_interrupt)
    state = {
        "analysis": InputAnalysis(goal="차가운 지역 버전으로 변경", subject="x"),
        "reference_plan": ReferencePlan(categories=[WINTER.model_copy(update={"applied_rules": ["중세 후기 복식"]})]),
    }
    out = references.confirm_categories(state)

    assert captured["goal"] == "차가운 지역 버전으로 변경"  # 사용자가 AI 의 이해를 확인할 수 있다
    assert captured["categories"] == [
        {"name": "겨울 설원 배경", "reason": "서식지", "applied_rules": ["중세 후기 복식"]}  # 검색어는 확인 화면에 보내지 않는다
    ]
    assert out["confirmed_names"] == ["겨울 설원 배경"]


def test_finalize_keeps_proposed_queries_and_expands_only_new_names(monkeypatch):
    new = ReferenceCategory(name="눈 덮인 가로등", reason="추가", queries=["snowy street lamp"])
    client = FakeClient({CategoryExpansion: CategoryExpansion(categories=[new]),
                         GroundedCategories: GroundedCategories(categories=[new])})
    monkeypatch.setattr(references, "get_client", lambda: client)
    monkeypatch.setattr(references, "search_scoped", fake_scoped([]))

    state = {
        "analysis": InputAnalysis(subject="버섯"),
        "reference_plan": ReferencePlan(categories=[WINTER, COCOA]),
        "confirmed_names": ["코코아 소품", "눈 덮인 가로등"],  # 겨울 설원 배경은 사용자가 뺌
    }
    out = asyncio.run(references.finalize_categories(state))

    assert [c.name for c in out["final_categories"]] == ["코코아 소품", "눈 덮인 가로등"]
    assert out["final_categories"][0].queries == ["hot cocoa mug"]  # 기존 검색어 유지
    assert out["final_categories"][1].queries == ["snowy street lamp"]
    expand_prompt = client.calls[0]["messages"][1]["content"]
    assert "눈 덮인 가로등" in expand_prompt
    assert "코코아 소품" not in expand_prompt  # 이미 있는 카테고리는 LLM 에 보내지 않는다


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


def test_finalize_keeps_only_queries_that_will_be_used(monkeypatch):
    many = ReferenceCategory(name="의상", queries=["a", "b", "c", "d"])
    monkeypatch.setattr(references, "get_client", lambda: FakeClient(None))

    state = {
        "analysis": InputAnalysis(subject="x"),
        "reference_plan": ReferencePlan(categories=[many]),
        "confirmed_names": ["의상"],
    }
    out = asyncio.run(references.finalize_categories(state))

    # 화면에 보여주는 검색어와 실제 검색에 쓴 검색어가 같아야 한다
    assert out["final_categories"][0].queries == ["a", "b"][: references.QUERIES_PER_CATEGORY]


def test_finalize_falls_back_to_name_when_llm_omits_category(monkeypatch):
    client = FakeClient({CategoryExpansion: CategoryExpansion(categories=[]),  # LLM 이 새 카테고리를 빠뜨림
                         GroundedCategories: GroundedCategories(categories=[])})
    monkeypatch.setattr(references, "get_client", lambda: client)
    monkeypatch.setattr(references, "search_scoped", fake_scoped([]))

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


# ── 세계관 반영(RAG) ──────────────────────────────────────────────────────────

def guide(file, section, text):
    return Guideline(text=text, source_type="confirmed_plans", category="world", file=file, section=section)


def fake_scoped(calls):
    """search_scoped 대역: world/mood 는 세계관 공통 가이드를, 그 외는 카테고리별 가이드를 돌려준다."""

    async def search(query, source_type, categories, n_results=3):
        calls.append((query, source_type, categories, n_results))
        if categories in (["world", "mood"], ["world"]):
            return [guide("01_world_setting.md", "7. 검색 키워드 가이드", "시대 기준: 중세 후기. 현대 소재 금지")]
        return [guide("07_costume_and_materials.md", "3. 추운 지역 의상", "두꺼운 울 망토, 모피 안감 후드")]

    return search


def test_ground_rewrites_queries_with_world_and_category_guides(monkeypatch):
    draft = ReferenceCategory(name="겨울 의상", reason="방한", queries=["winter jacket", "puffer coat"])
    grounded = GroundedCategories(
        categories=[ReferenceCategory(name="겨울 의상", queries=["medieval wool cloak", "fur-lined hood"],
                                      applied_rules=["중세 후기 복식 기준"])],
        era_keyword="medieval",
        exclude_terms=["modern", "zipper"],
    )
    client = FakeClient(grounded)
    calls = []
    monkeypatch.setattr(references, "get_client", lambda: client)
    monkeypatch.setattr(references, "search_scoped", fake_scoped(calls))

    state = {"text": "방한 의상", "analysis": InputAnalysis(goal="차가운 지역 버전", subject="몬스터")}
    out = asyncio.run(references.ground_categories({**state, "reference_plan": ReferencePlan(categories=[draft], exclude_terms=["cartoon"])}))

    plan = out["reference_plan"]
    assert plan.categories[0].queries == ["medieval wool cloak", "fur-lined hood"]  # 검색어가 세계관에 맞게 바뀜
    assert plan.categories[0].applied_rules == ["중세 후기 복식 기준"]
    assert plan.categories[0].reason == "방한"  # 이유는 유지
    assert plan.exclude_terms == ["cartoon", "modern", "zipper"]  # 기존 제외어 + 가이드가 금지한 것
    # 세계관 공통 2번(요청 기반 + 시대·키워드 가이드) + 카테고리별 2번(이름 / 이름+이유), 모두 '확정된 기획'에서만 찾는다
    assert sorted(map(tuple, (c[2] for c in calls))) == [(), (), ("world",), ("world", "mood")]
    assert {c[1] for c in calls} == {"confirmed_plans"}
    queries = [c[0] for c in calls]
    assert "겨울 의상" in queries and "겨울 의상. 방한" in queries  # 짧은 질의와 이유를 붙인 질의
    assert any("검색 키워드 가이드" in q for q in queries)
    prompt = client.calls[0]["messages"][1]["content"]
    assert "중세 후기" in prompt and "모피 안감 후드" in prompt and "차가운 지역 버전" in prompt


def test_ensure_era_adds_keyword_only_when_missing():
    # LLM 이 시대 키워드를 빠뜨려도 코드가 보장한다
    assert references._ensure_era(["fur-lined cloak", "wool mantle"], "medieval") == ["medieval fur-lined cloak", "wool mantle"]
    assert references._ensure_era(["Medieval cloak", "wool mantle"], "medieval") == ["Medieval cloak", "wool mantle"]  # 이미 있으면 그대로
    assert references._ensure_era(["a", "b"], "") == ["a", "b"]  # 시대 키워드가 없는 세계관이면 건드리지 않는다


def test_ground_applies_era_keyword_to_every_category(monkeypatch):
    drafts = [ReferenceCategory(name="의상", queries=["coat"]), ReferenceCategory(name="배경", queries=["snow"])]
    grounded = GroundedCategories(
        categories=[ReferenceCategory(name="의상", queries=["fur coat", "wool mantle"]),
                    ReferenceCategory(name="배경", queries=["late medieval snowy keep"])],
        era_keyword="medieval",
    )
    monkeypatch.setattr(references, "get_client", lambda: FakeClient(grounded))
    monkeypatch.setattr(references, "search_scoped", fake_scoped([]))

    state = {"text": "x", "analysis": InputAnalysis(subject="x"), "reference_plan": ReferencePlan(categories=drafts)}
    out = asyncio.run(references.ground_categories(state))

    assert out["reference_plan"].categories[0].queries == ["medieval fur coat", "wool mantle"]  # 빠져 있어서 붙임
    assert out["reference_plan"].categories[1].queries == ["late medieval snowy keep"]  # 이미 있어서 그대로


def test_ground_keeps_original_category_when_llm_omits_it(monkeypatch):
    draft = ReferenceCategory(name="겨울 의상", queries=["winter coat"])
    monkeypatch.setattr(references, "get_client", lambda: FakeClient(GroundedCategories(categories=[])))
    monkeypatch.setattr(references, "search_scoped", fake_scoped([]))

    state = {"text": "x", "analysis": InputAnalysis(subject="x"), "reference_plan": ReferencePlan(categories=[draft])}
    out = asyncio.run(references.ground_categories(state))

    assert out["reference_plan"].categories[0] == draft


def test_finalize_grounds_user_added_categories_too(monkeypatch):
    expansion = CategoryExpansion(categories=[ReferenceCategory(name="눈 덮인 가로등", reason="추가", queries=["street lamp"])])
    grounded = GroundedCategories(
        categories=[ReferenceCategory(name="눈 덮인 가로등", queries=["medieval iron lantern", "snow lantern post"],
                                      applied_rules=["조명은 횃불·기름 램프"])],
        exclude_terms=["electric"],
    )
    client = FakeClient({CategoryExpansion: expansion, GroundedCategories: grounded})
    monkeypatch.setattr(references, "get_client", lambda: client)
    monkeypatch.setattr(references, "search_scoped", fake_scoped([]))

    state = {
        "text": "x", "analysis": InputAnalysis(subject="x"),
        "reference_plan": ReferencePlan(categories=[WINTER], exclude_terms=["cartoon"]),
        "confirmed_names": ["겨울 설원 배경", "눈 덮인 가로등"],
    }
    out = asyncio.run(references.finalize_categories(state))

    added = out["final_categories"][1]
    assert added.queries == ["medieval iron lantern", "snow lantern post"] and added.applied_rules == ["조명은 횃불·기름 램프"]
    assert out["final_categories"][0].queries == ["snowy field", "winter forest"]  # 제안된 카테고리는 이미 반영돼 있어 다시 쓰지 않는다
    assert out["reference_plan"].exclude_terms == ["cartoon", "electric"]  # 새 카테고리에서 나온 제외어도 합쳐진다


def test_drop_conflicting_excludes_removes_terms_used_in_queries():
    cats = [ReferenceCategory(name="음료", queries=["warm milk", "herbal tea"]), ReferenceCategory(name="몬스터", queries=["blue tinted orange"])]
    kept = references._drop_conflicting_excludes(["warm", "orange", "Modern", "tropical"], cats)
    # warm / orange 는 자기 검색어에 있어서 제외하면 모순이 된다
    assert kept == ["Modern", "tropical"]


def test_finalize_drops_excludes_that_conflict_with_final_queries(monkeypatch):
    monkeypatch.setattr(references, "get_client", lambda: FakeClient(None))
    cocoa = ReferenceCategory(name="음료", queries=["warm milk"])
    state = {
        "analysis": InputAnalysis(subject="x"),
        "reference_plan": ReferencePlan(categories=[cocoa], exclude_terms=["warm", "plastic"]),
        "confirmed_names": ["음료"],
    }
    out = asyncio.run(references.finalize_categories(state))
    assert out["reference_plan"].exclude_terms == ["plastic"]


def test_search_images_collects_a_larger_pool_than_requested(monkeypatch):
    # 이미지 검토에서 탈락하는 것을 감안해 보여줄 개수(per_category)의 2배(최소 6)를 모은다
    results = {"snowy field": [cand(f"a{i}") for i in range(30)]}
    monkeypatch.setattr(references, "DEFAULT_SOURCES", [FakeSource("S", results)])
    state = {"final_categories": [WINTER], "reference_plan": ReferencePlan(categories=[WINTER])}

    sizes = {n: len(asyncio.run(references.search_images({**state, "per_category": n}))["candidates"]) for n in (1, 4, 10)}
    assert sizes == {1: 6, 4: 8, 10: 20}  # 최소 6, 2배, 상한 20


def test_confirm_returns_chosen_count(monkeypatch):
    monkeypatch.setattr(references, "interrupt", lambda payload: {"categories": ["a"], "per_category": 7})
    state = {"analysis": InputAnalysis(subject="x"), "reference_plan": ReferencePlan(categories=[WINTER])}
    assert references.confirm_categories(state)["per_category"] == 7
