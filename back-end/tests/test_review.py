import asyncio

import httpx
import pytest

from app.agent import review
from app.agent.state import (
    Candidate,
    ImageReview,
    ImageVerdict,
    InputAnalysis,
    ReferenceCategory,
    ReferencePlan,
)
from tests.fakes import FakeClient

CAT = ReferenceCategory(name="겨울 의상", reason="방한", queries=["winter cloak"], applied_rules=["현대 의류 금지"])


def cand(n, license="confirmed", topic="겨울 의상"):
    return Candidate(id=f"c{n}", image_url=f"https://img/{n}.jpg", source_url=f"https://s/{n}", license=license,
                     topic=topic, reason="검색어: winter cloak")


def verdicts(*scores):
    return ImageReview(verdicts=[ImageVerdict(index=i, score=s, reason=f"이유{i}") for i, s in enumerate(scores, start=1)])


def state(candidates, per_category=5, categories=(CAT,)):
    return {
        "text": "방한 의상", "analysis": InputAnalysis(goal="차가운 지역 버전", subject="몬스터"),
        "reference_plan": ReferencePlan(categories=list(categories), exclude_terms=["modern"]),
        "final_categories": list(categories), "candidates": candidates, "per_category": per_category,
    }


@pytest.fixture
def fake_review(monkeypatch):
    def install(client, unloadable=()):
        monkeypatch.setattr(review, "get_client", lambda: client)

        async def download(http, gate, candidate):
            return None if candidate.id in unloadable else "data:image/png;base64,AAAA"

        monkeypatch.setattr(review, "_to_data_url", download)
        return client

    return install


def test_keeps_only_passing_images_best_first_and_up_to_requested_count(fake_review):
    client = fake_review(FakeClient(verdicts(7, 3, 9, 6)))
    out = asyncio.run(review.review_images(state([cand(1), cand(2), cand(3), cand(4)], per_category=2)))

    # 3번(9점), 1번(7점)만 남는다. 4번(6점)은 통과했지만 개수 제한으로, 2번(3점)은 부적합으로 빠진다
    assert [c.id for c in out["candidates"]] == ["c3", "c1"]
    assert [c.score for c in out["candidates"]] == [0.9, 0.7]
    assert out["candidates"][0].review == "이유3"
    assert [(c.id, c.review) for c in out["rejected_candidates"]] == [("c2", "이유2")]  # 부적합만 이유와 함께 기록


def test_prompt_contains_goal_category_rules_and_images(fake_review):
    client = fake_review(FakeClient(verdicts(8)))
    asyncio.run(review.review_images(state([cand(1)])))

    content = client.calls[0]["messages"][1]["content"]
    header = content[0]["text"]
    assert "차가운 지역 버전" in header and "겨울 의상" in header and "현대 의류 금지" in header and "modern" in header
    assert content[1] == {"type": "text", "text": "[이미지 1] 검색어: winter cloak"}
    assert content[2]["image_url"] == {"url": "data:image/png;base64,AAAA", "detail": "low"}  # 비용을 줄이는 저해상도 검토


def test_unloadable_images_are_rejected_without_calling_the_model(fake_review):
    client = fake_review(FakeClient(verdicts(8)), unloadable={"c1"})
    out = asyncio.run(review.review_images(state([cand(1), cand(2)])))

    assert [c.id for c in out["candidates"]] == ["c2"]
    assert out["rejected_candidates"][0].id == "c1" and out["rejected_candidates"][0].review == review.NOT_LOADED
    assert len(client.calls) == 1 and len(client.calls[0]["messages"][1]["content"]) == 3  # 불러온 이미지 1장만 보냄


def test_images_are_reviewed_in_batches(fake_review, monkeypatch):
    monkeypatch.setattr(review, "BATCH_SIZE", 2)
    client = fake_review(FakeClient(verdicts(8, 8)))
    out = asyncio.run(review.review_images(state([cand(i) for i in range(1, 5)], per_category=10)))

    assert len(client.calls) == 2  # 4장을 2장씩
    assert len(out["candidates"]) == 4


def test_review_failure_keeps_images_instead_of_losing_them(fake_review):
    class Boom:
        calls = []

        class chat:
            class completions:
                @staticmethod
                async def parse(**kwargs):
                    raise TimeoutError

    fake_review(Boom)
    out = asyncio.run(review.review_images(state([cand(1), cand(2), cand(3)], per_category=2)))

    # 검토를 못 했어도 후보를 버리지 않고 개수만큼 보여주며, 못 했다는 사실을 알린다
    assert [c.id for c in out["candidates"]] == ["c1", "c2"]
    assert all(c.score is None and c.review == review.NOT_REVIEWED for c in out["candidates"])
    assert out["rejected_candidates"] == []
    assert out["source_errors"] == ["이미지 검토: TimeoutError"]


def test_missing_verdict_is_treated_as_not_reviewed(fake_review):
    fake_review(FakeClient(verdicts(9)))  # 이미지는 2장인데 결과가 1장 분량만 옴
    out = asyncio.run(review.review_images(state([cand(1), cand(2)])))

    assert [c.id for c in out["candidates"]] == ["c1", "c2"]
    assert out["candidates"][1].review == review.NOT_REVIEWED


def test_each_category_gets_its_own_count(fake_review):
    other = ReferenceCategory(name="겨울 배경", queries=["snow"])
    fake_review(FakeClient(verdicts(8, 8, 8)))
    cands = [cand(1), cand(2), cand(3), cand(4, topic="겨울 배경"), cand(5, topic="겨울 배경")]
    out = asyncio.run(review.review_images(state(cands, per_category=1, categories=(CAT, other))))

    assert [(c.topic, c.id) for c in out["candidates"]] == [("겨울 의상", "c1"), ("겨울 배경", "c4")]


def test_download_converts_to_data_url_and_rejects_bad_responses():
    def handler(request):
        url = str(request.url)
        if url.endswith("ok.png"):
            return httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png; charset=binary"})
        if url.endswith("page.html"):
            return httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"})
        if url.endswith("big.png"):
            return httpx.Response(200, content=b"x" * (review.MAX_IMAGE_BYTES + 1), headers={"content-type": "image/png"})
        return httpx.Response(404)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            gate = asyncio.Semaphore(2)
            return [
                await review._to_data_url(http, gate, Candidate(id=n, image_url=f"https://x/{n}", source_url="s"))
                for n in ("ok.png", "page.html", "big.png", "missing.png")
            ]

    ok, html, big, missing = asyncio.run(run())
    assert ok == "data:image/png;base64,iVBORw==" and html is None and big is None and missing is None


def test_prompt_judges_only_the_given_category():
    # 회귀 테스트: 색감·배경 이미지가 '몬스터가 없다'는 이유로 감점되던 문제 (카테고리 단위로만 평가해야 한다)
    assert "오직 이 카테고리 하나" in review.REVIEW_PROMPT
    assert "감점하지 마라" in review.REVIEW_PROMPT


def test_download_falls_back_to_original_when_thumbnail_fails():
    def handler(request):
        if "thumb" in str(request.url):
            return httpx.Response(424)  # Openverse 썸네일이 간헐적으로 실패하는 경우
        return httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})

    c = Candidate(id="a", image_url="https://x/original.png", thumbnail_url="https://x/thumb/", source_url="s")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await review._to_data_url(http, asyncio.Semaphore(1), c)

    assert asyncio.run(run()) == "data:image/png;base64,iVBORw=="


def test_download_gives_up_when_both_fail():
    c = Candidate(id="a", image_url="https://x/original.png", thumbnail_url="https://x/thumb/", source_url="s")
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(429)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await review._to_data_url(http, asyncio.Semaphore(1), c)

    assert asyncio.run(run()) is None and calls == ["https://x/thumb/", "https://x/original.png"]
