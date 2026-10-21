import asyncio

import httpx
import pytest

from app.agent.references import merge_candidates
from app.agent.sources.base import classify_license
from app.agent.sources.openverse import OpenverseSource
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
    merged = merge_candidates([a, b], exclude_terms=["cartoon"], seen=set())
    assert [c.image_url for c in merged] == ["u1"]


def test_merge_puts_confirmed_first_and_interleaves():
    a = [cand("a1", "unclear"), cand("a2")]
    b = [cand("b1"), cand("b2", "restricted")]
    merged = merge_candidates([a, b], exclude_terms=[], seen=set())
    # 번갈아 섞은 뒤(a1, b1, a2, b2) 라이선스가 확실한 것을 앞으로 (순서 유지)
    assert [c.image_url for c in merged] == ["b1", "a2", "a1", "b2"]


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
    second = merge_candidates([[cand("u1"), cand("u3")]], [], seen)  # u1 은 앞 카테고리에서 이미 사용됨
    assert [c.image_url for c in first] == ["u1"]
    assert [c.image_url for c in second] == ["u3"]
