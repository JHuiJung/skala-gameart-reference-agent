import asyncio

from app.agent import retriever


def test_categories_are_routed_to_matching_source_type(monkeypatch):
    calls = []

    def fake_search(query, source_type, categories, n_results):
        calls.append((source_type, categories, n_results))
        return []

    monkeypatch.setattr(retriever, "_search", fake_search)
    asyncio.run(retriever.search_guidelines("q", ["monster", "color"], plan_k=4, rule_k=3))

    assert sorted(calls) == [
        ("company_rules", ["color"], 3),
        ("confirmed_plans", ["monster"], 4),
    ]


def test_rules_are_always_searched_even_without_rule_category(monkeypatch):
    calls = []
    monkeypatch.setattr(retriever, "_search", lambda q, st, cats, n: calls.append((st, cats)) or [])

    asyncio.run(retriever.search_guidelines("q", ["monster"]))

    # 규정 카테고리를 고르지 않아도 규정 전체에서 검색한다 (5색 제한 같은 규정이 빠지지 않도록)
    assert ("company_rules", []) in calls
