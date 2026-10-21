import asyncio
import json

import httpx
import pytest

from app.agent import storage
from app.agent.state import Candidate, InputAnalysis, ReferenceCategory, ReferencePlan

CAT_A = ReferenceCategory(name="겨울 외피", queries=["fur cloak"], applied_rules=["중세 복식"])
CAT_B = ReferenceCategory(name="배경/설원", queries=["snow"])


def cand(id, topic="겨울 외피", license="confirmed", title="Fur Cloak", **kw):
    return Candidate(id=id, image_url=f"https://img/{id}.jpg", thumbnail_url=f"https://img/{id}_t.jpg",
                     source_url=f"https://src/{id}", topic=topic, license=license, title=title, **kw)


def state(candidates, selected, categories=(CAT_A, CAT_B), save_unverified=False):
    return {
        "analysis": InputAnalysis(goal="g", subject="s"), "asset_type": "character",
        "reference_plan": ReferencePlan(categories=list(categories), exclude_terms=["modern"]),
        "final_categories": list(categories), "candidates": candidates, "selected_ids": selected,
        "save_unverified": save_unverified,
    }


def test_output_dirs_are_numbered_from_the_next_free_number(tmp_path):
    assert storage.create_output_dir(tmp_path / "result").name == "artBrief_001"
    assert storage.create_output_dir(tmp_path / "result").name == "artBrief_002"
    (tmp_path / "result" / "artBrief_007").mkdir()  # 번호가 비어 있어도 가장 큰 번호 다음으로
    (tmp_path / "result" / "memo").mkdir()  # 상관없는 폴더는 무시
    assert storage.create_output_dir(tmp_path / "result").name == "artBrief_008"


@pytest.mark.parametrize("text, expected", [
    ("Fur Cloak", "Fur_Cloak"),
    ("겨울 외피", "겨울_외피"),
    ('a/b\\c:d*e?"f<g>h|i', "abcdefghi"),  # 경로를 깨는 문자 제거
    ("../../etc/passwd", "etcpasswd"),  # 상위 폴더로 빠져나가지 못하게
    ("   ", "fallback"),
    ("x" * 100, "x" * 40),
])
def test_slugify(text, expected):
    assert storage.slugify(text, "fallback") == expected


@pytest.mark.parametrize("license, save_unverified, allowed", [
    ("confirmed", False, True), ("confirmed", True, True),
    ("unclear", False, False), ("unclear", True, True),     # 확인 안 된 이미지는 사용자가 허용했을 때만 저장
    ("restricted", False, False), ("restricted", True, False),  # 제한된 이미지는 허용해도 저장하지 않음
])
def test_storage_decision(license, save_unverified, allowed):
    ok, reason = storage.storage_decision(cand("a", license=license), save_unverified)
    assert ok is allowed and (reason == "") is allowed


def downloader(handler):
    async def run(candidate):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            return await storage.download_image(http, candidate)

    return lambda c: asyncio.run(run(c))


def test_download_retries_rate_limit_then_succeeds(monkeypatch):
    monkeypatch.setattr(storage, "RETRY_DELAY", 0)
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if len(calls) < 3:
            return httpx.Response(429)
        return httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})

    assert downloader(handler)(cand("a")) == (b"\x89PNG", "image/png")
    assert calls == ["https://img/a.jpg"] * 3  # 같은 주소로 다시 시도


def test_download_falls_back_to_thumbnail(monkeypatch):
    monkeypatch.setattr(storage, "RETRY_DELAY", 0)

    def handler(request):
        if str(request.url).endswith("_t.jpg"):
            return httpx.Response(200, content=b"thumb", headers={"content-type": "image/jpeg"})
        return httpx.Response(403)

    assert downloader(handler)(cand("a")) == (b"thumb", "image/jpeg")


@pytest.mark.parametrize("response", [
    httpx.Response(200, content=b"<html>", headers={"content-type": "text/html"}),
    httpx.Response(200, content=b"x" * (storage.MAX_IMAGE_BYTES + 1), headers={"content-type": "image/png"}),
    httpx.Response(404),
])
def test_download_rejects_non_images_oversized_and_errors(monkeypatch, response):
    monkeypatch.setattr(storage, "RETRY_DELAY", 0)
    assert downloader(lambda request: response)(cand("a")) is None


def test_save_selected_writes_files_in_numbered_category_folders(tmp_path, monkeypatch):
    async def fake_download(http, candidate):
        return (b"BAD", "image/png") if candidate.id == "bad" else (f"data-{candidate.id}".encode(), "image/jpeg")

    monkeypatch.setattr(storage, "download_image", fake_download)
    cands = [
        cand("a1", title="Fur Cloak"), cand("a2", license="unclear", title="Wool"),
        cand("b1", topic="배경/설원", title=""), cand("skip", title="선택 안 함"),
    ]
    st = state(cands, ["a1", "a2", "b1"])
    progress = []

    saved = asyncio.run(storage.save_selected(st, tmp_path, lambda done, total: progress.append((done, total))))

    by_id = {r.candidate.id: r for r in saved}
    assert by_id["a1"].status == "saved" and by_id["a1"].file == "01_겨울_외피/01_Fur_Cloak.jpg"
    assert (tmp_path / by_id["a1"].file).read_bytes() == b"data-a1"
    assert by_id["a2"].status == "link_only" and by_id["a2"].file is None and "라이선스" in by_id["a2"].note
    assert by_id["b1"].file == "02_배경설원/01_image_1.jpg"  # 제목이 없으면 image_N, 카테고리 이름의 '/' 는 제거
    assert "skip" not in by_id  # 선택하지 않은 이미지는 건드리지 않는다
    assert sorted(p.name for p in tmp_path.iterdir()) == ["01_겨울_외피", "02_배경설원"]
    assert progress[-1] == (3, 3)


def test_save_selected_records_failures_and_honors_save_unverified(tmp_path, monkeypatch):
    async def fake_download(http, candidate):
        return None if candidate.id == "bad" else (b"x", "image/png")

    monkeypatch.setattr(storage, "download_image", fake_download)
    cands = [cand("bad"), cand("u", license="unclear"), cand("r", license="restricted")]

    saved = asyncio.run(storage.save_selected(state(cands, ["bad", "u", "r"], save_unverified=True), tmp_path))

    status = {r.candidate.id: r.status for r in saved}
    assert status == {"bad": "failed", "u": "saved", "r": "link_only"}  # 허용하면 확인 안 된 것도 저장, 제한된 것은 여전히 링크만


def test_references_json_records_source_license_and_status(tmp_path, monkeypatch):
    async def fake_download(http, candidate):
        return b"x", "image/png"

    monkeypatch.setattr(storage, "download_image", fake_download)
    c = cand("a1", creator="kim", license_detail="CC BY 2.0", source_name="Openverse (flickr)", score=0.9, review="좋음",
             reason="검색어: fur cloak")
    st = state([c], ["a1"])
    saved = asyncio.run(storage.save_selected(st, tmp_path))

    path = storage.write_references_json(st, tmp_path, saved)
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["folder"] == tmp_path.name and data["goal"] == "g" and data["exclude_terms"] == ["modern"]
    [category] = data["categories"]  # 선택한 이미지가 있는 카테고리만 기록
    assert category["name"] == "겨울 외피" and category["folder"] == "01_겨울_외피" and category["applied_rules"] == ["중세 복식"]
    assert category["images"][0] == {
        "id": "a1", "title": "Fur Cloak", "file": "01_겨울_외피/01_Fur_Cloak.png", "status": "saved", "note": "",
        "image_url": "https://img/a1.jpg", "source_url": "https://src/a1", "source_name": "Openverse (flickr)",
        "creator": "kim", "license": "confirmed", "license_detail": "CC BY 2.0", "found_by": "fur cloak",
        "review_score": 0.9, "review": "좋음",
    }


def test_save_selected_sends_user_agent_header(tmp_path, monkeypatch):
    # 회귀 테스트: User-Agent 가 없으면 Wikimedia 가 403 으로 막아서 라이선스가 확인된 이미지도 저장에 실패했다
    seen = []

    def handler(request):
        seen.append(request.headers.get("user-agent"))
        return httpx.Response(200, content=b"x", headers={"content-type": "image/png"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(storage.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))

    saved = asyncio.run(storage.save_selected(state([cand("a1")], ["a1"]), tmp_path))

    assert saved[0].status == "saved" and seen == [storage.USER_AGENT]
