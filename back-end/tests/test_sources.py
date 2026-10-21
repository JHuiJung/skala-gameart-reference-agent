import asyncio
import json

import httpx
import pytest

from app.agent.references import merge_candidates
from app.agent.sources.base import classify_license
from app.agent.sources.openverse import OpenverseSource
from app.agent.sources.tavily import TavilySource
from app.agent.sources.wikimedia import WikimediaSource
from app.agent.state import Candidate


def cand(url, license="confirmed", title="", tags=()):
    return Candidate(id=url, image_url=url, source_url=url, license=license, title=title, tags=list(tags))


@pytest.mark.parametrize("name, expected", [
    ("cc0", "confirmed"), ("pdm", "confirmed"), ("by 2.0", "confirmed"), ("by-sa", "confirmed"),
    ("CC BY-SA 4.0", "confirmed"), ("Public domain", "confirmed"),
    ("by-nc", "restricted"), ("CC BY-NC-SA 3.0", "restricted"), ("Fair use", "restricted"),
    ("by-nd", "unclear"), ("GFDL", "unclear"), ("", "unclear"),
])
def test_classify_license(name, expected):
    assert classify_license(name) == expected


def test_merge_removes_duplicates_and_excluded():
    a = [cand("u1"), cand("u2", title="Cute cartoon wolf")]
    b = [cand("u1"), cand("u3", tags=["cartoon"])]
    merged = merge_candidates([a, b], exclude_terms=["cartoon"], seen=set(), limit=10)
    assert [c.image_url for c in merged] == ["u1"]


def test_merge_puts_confirmed_first_and_interleaves():
    a = [cand("a1", "unclear"), cand("a2")]
    b = [cand("b1"), cand("b2", "restricted")]
    merged = merge_candidates([a, b], exclude_terms=[], seen=set(), limit=10)
    # 번갈아 섞은 뒤(a1, b1, a2, b2) 라이선스가 확실한 것을 앞으로 (순서 유지)
    assert [c.image_url for c in merged] == ["b1", "a2", "a1", "b2"]


def test_merge_reserves_slots_for_unconfirmed_web_results():
    confirmed = [cand(f"c{i}") for i in range(10)]
    web = [cand(f"w{i}", "unclear") for i in range(5)]
    merged = merge_candidates([confirmed, web], [], set(), limit=8, web_slots=3)
    urls = [c.image_url for c in merged]
    assert len(urls) == 8
    assert urls[:5] == ["c0", "c1", "c2", "c3", "c4"]  # 확실한 후보가 앞
    assert urls[5:] == ["w0", "w1", "w2"]  # 웹 검색 결과 자리가 보장된다


def test_merge_default_web_slots_scale_with_limit():
    confirmed = [cand(f"c{i}") for i in range(20)]
    web = [cand(f"w{i}", "unclear") for i in range(20)]
    # limit 9 → 웹 검색 결과 자리 3개, limit 2 → 최소 1개는 보장
    assert sum(c.license == "unclear" for c in merge_candidates([confirmed, web], [], set(), limit=9)) == 3
    assert sum(c.license == "unclear" for c in merge_candidates([confirmed, web], [], set(), limit=2)) == 1


def test_merge_fills_with_unconfirmed_when_confirmed_run_out():
    merged = merge_candidates([[cand("c0")], [cand(f"w{i}", "unclear") for i in range(6)]], [], set(), limit=8, web_slots=3)
    assert [c.image_url for c in merged] == ["c0", "w0", "w1", "w2", "w3", "w4", "w5"]


async def _search(source, payload, query):
    """가짜 HTTP 응답(payload)으로 출처 어댑터를 실행한다. 실제 네트워크는 사용하지 않는다."""
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as client:
        return await source.search(client, query, 5)


def test_openverse_maps_fields():
    payload = {"results": [{
        "url": "https://img/1.jpg", "thumbnail": "https://img/t.jpg", "foreign_landing_url": "https://flickr/1",
        "title": "Mossy wall", "creator": "kim", "license": "by", "license_version": "2.0",
        "source": "flickr", "tags": [{"name": "moss"}],
    }]}
    [c] = asyncio.run(_search(OpenverseSource(), payload, "mossy wall"))
    assert (c.license, c.license_detail, c.creator) == ("confirmed", "CC BY 2.0", "kim")
    assert c.source_name == "Openverse (flickr)" and c.source_url == "https://flickr/1"
    assert c.tags == ["moss"] and c.reason == "검색어: mossy wall"


def test_wikimedia_skips_non_images_and_strips_html():
    def page(index, mime, title):
        return {"title": title, "index": index, "imageinfo": [{
            "url": f"https://u/{index}", "thumburl": "https://t", "descriptionurl": f"https://d/{index}", "mime": mime,
            "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}, "Artist": {"value": '<a href="x">Lee</a>  Min'}},
        }]}
    payload = {"query": {"pages": {"2": page(2, "image/jpeg", "File:B.jpg"), "1": page(1, "image/svg+xml", "File:A.svg")}}}
    results = asyncio.run(_search(WikimediaSource(), payload, "wall"))
    assert [c.title for c in results] == ["B.jpg"]  # svg 제외, "File:" 접두어 제거
    assert results[0].creator == "Lee Min" and results[0].license == "confirmed"


def test_merge_shares_seen_across_categories_and_respects_limit():
    seen = set()
    first = merge_candidates([[cand("u1"), cand("u2")]], [], seen, limit=1)
    second = merge_candidates([[cand("u1"), cand("u3")]], [], seen, limit=10)  # u1 은 앞 카테고리에서 이미 사용됨
    assert [c.image_url for c in first] == ["u1"]
    assert [c.image_url for c in second] == ["u3"]


def _tavily_payload():
    return {"images": [
        {"url": "https://www.dreamstime.com/a.jpg", "title": "Winter monster stock", "description": "blue monster in coat"},
        {"url": "https://blog.example.com/b.jpg", "title": "", "description": "cozy knit scarf"},
        {"url": "https://x.com/c.jpg", "title": "t", "description": "d"},
        "https://plain.example.com/d.jpg",  # 설명 없이 URL 문자열만 오는 경우
    ]}


def test_tavily_maps_images_and_marks_stock_sites_restricted(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    results = asyncio.run(_search(TavilySource(), _tavily_payload(), "winter coat"))

    stock, blog, _, plain = results
    assert (stock.license, stock.license_detail) == ("restricted", "유료 스톡 이미지 (워터마크 가능)")
    assert stock.source_name == "웹 검색 (dreamstime.com)"  # www. 는 제거
    assert (blog.license, blog.title) == ("unclear", "cozy knit scarf")  # 제목이 없으면 설명을 사용
    assert blog.tags == ["cozy knit scarf"] and blog.source_url == blog.image_url
    assert plain.image_url == "https://plain.example.com/d.jpg" and plain.title == ""


def test_tavily_respects_limit(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=_tavily_payload()))

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await TavilySource().search(client, "q", 2)

    assert len(asyncio.run(run())) == 2


def test_tavily_sends_key_and_query(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.read())
        return httpx.Response(200, json={"images": []})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await TavilySource().search(client, "winter coat", 5)

    asyncio.run(run())
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["query"] == "winter coat"
    assert seen["body"]["include_images"] is True


def test_tavily_without_key_is_skipped(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    called = []
    transport = httpx.MockTransport(lambda request: called.append(1) or httpx.Response(200, json={}))

    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            return await TavilySource().search(client, "q", 5)

    assert asyncio.run(run()) == []
    assert called == []  # 키가 없으면 요청 자체를 보내지 않는다
