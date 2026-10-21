import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.agent import runner
from app.agent.progress import emit_detail
from app.main import app
from tests.graph_fakes import ans, extracted, start_state


def collect(events):
    async def run():
        return [e async for e in events]

    return asyncio.run(run())


def labels(events):
    return [data["label"] for name, data in events if name == "step"]


def test_emit_detail_outside_graph_is_a_noop():
    emit_detail("그래프 밖에서 호출해도 오류가 나면 안 된다")


def test_stream_reports_steps_in_order_and_stops_at_confirmation(fake_llm):
    fake_llm("prop", extracted(scale="a", function="b", interaction="c"))
    events = collect(runner.stream_start(start_state()))

    # 사용자 확인 전까지의 작업 단계가 순서대로 나오고, 되묻는 노드는 단계로 나오지 않는다
    assert labels(events) == [
        "에셋 종류 분류", "필수 항목 확인", "입력 분석", "내부 가이드 검색", "레퍼런스 카테고리 제안", "세계관 가이드 반영",
    ]
    name, result = events[-1]
    assert name == "result" and result["status"] == "needs_input" and result["kind"] == "confirm_categories"
    assert result["thread_id"]


def test_stream_resume_reports_search_review_and_detail_progress(fake_llm):
    fake_llm("prop", extracted(scale="a", function="b", interaction="c"))

    async def flow():
        first = [e async for e in runner.stream_start(start_state())]
        thread_id = first[-1][1]["thread_id"]
        value = await runner.prepare_resume(ans(thread_id, categories=["배경"], per_category=3))
        return [e async for e in runner.stream_resume(thread_id, value)]

    events = asyncio.run(flow())

    assert labels(events) == ["카테고리 검색어 준비", "웹 이미지 검색", "이미지 적합성 검토"]
    details = [data["detail"] for name, data in events if name == "detail"]
    assert details == ["'배경' 검색 완료 (1/1)", "'배경' 검토 완료 (1/1)"]  # 검색·검토 단계 안의 세부 진행
    name, result = events[-1]
    # 이미지 검토까지 끝나면 사용자가 이미지를 고를 때까지 멈춘다 (이미지와 검토 결과가 함께 온다)
    assert name == "result" and result["status"] == "needs_input" and result["kind"] == "select_images"
    assert result["candidates"][0]["review"] == "눈 덮인 들판이 분명함"


def test_stream_covers_brief_steps_and_reports_saving_progress(fake_llm):
    fake_llm("prop", extracted(scale="a", function="b", interaction="c"))

    async def resume(thread_id, **fields):
        value = await runner.prepare_resume(ans(thread_id, **fields))
        return [e async for e in runner.stream_resume(thread_id, value)]

    async def flow():
        first = [e async for e in runner.stream_start(start_state())]
        thread_id = first[-1][1]["thread_id"]
        await resume(thread_id, categories=["배경"], per_category=3)
        planned = await resume(thread_id, selected_ids=["snowy field"])
        confirm = planned[-1][1]
        approved = await resume(thread_id, brief_sections=confirm["brief_sections"])
        return planned, approved

    planned, approved = asyncio.run(flow())

    assert labels(planned) == ["지시서 작성 계획 수립"]
    assert planned[-1][1]["kind"] == "confirm_brief"
    assert labels(approved) == ["레퍼런스 이미지 저장", "지시서 작성"]
    assert [d["detail"] for n, d in approved if n == "detail"] == ["이미지 저장 1/1"]
    name, result = approved[-1]
    assert name == "result" and result["status"] == "done" and result["output"]["folder"].endswith("artBrief_001")


def test_stream_turns_failures_into_error_event(monkeypatch):
    async def boom(*args, **kwargs):
        raise TimeoutError
        yield  # pragma: no cover  (비동기 제너레이터로 만들기 위한 코드)

    monkeypatch.setattr(runner.graph, "astream", boom)
    events = collect(runner.stream_start(start_state()))

    assert events == [("error", {"message": "서버에서 오류가 발생했어요 (TimeoutError)"})]  # 내부 정보는 노출하지 않는다


# ── HTTP 엔드포인트 ──────────────────────────────────────────────────────────

def parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((lines["event"], json.loads(lines["data"])))
    return events


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_upload_stream_endpoint_returns_sse(client, fake_llm, png_bytes):
    fake_llm("prop", extracted(scale="a", function="b", interaction="c"))
    r = client.post("/upload/stream", data={"text": "소품"}, files={"image": ("a.png", png_bytes, "image/png")})

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["cache-control"] == "no-cache"
    events = parse_sse(r.text)
    assert events[0] == ("step", {"label": "에셋 종류 분류"})
    assert events[-1][0] == "result" and events[-1][1]["kind"] == "confirm_categories"


def test_full_conversation_over_streaming_endpoints(client, fake_llm, png_bytes):
    fake_llm("prop", extracted(scale="a", function="b", interaction="c"))

    def post(body):
        return parse_sse(client.post("/answer/stream", json=body).text)[-1][1]

    first = parse_sse(
        client.post("/upload/stream", data={"text": "소품"}, files={"image": ("a.png", png_bytes, "image/png")}).text
    )[-1][1]
    tid = first["thread_id"]

    selecting = post({"thread_id": tid, "categories": ["배경"], "per_category": 2})
    assert selecting["kind"] == "select_images" and [c["topic"] for c in selecting["candidates"]] == ["배경"]

    planning = post({"thread_id": tid, "selected_ids": ["snowy field"], "save_unverified": False})
    assert planning["kind"] == "confirm_brief"

    done = post({"thread_id": tid, "brief_sections": planning["brief_sections"], "brief_notes": "차갑게"})
    assert done["status"] == "done" and done["output"]["saved"] == 1


def test_answer_stream_rejects_before_streaming_starts(client):
    # 스트림을 시작하기 전에 검사하므로 일반 HTTP 오류 코드로 응답한다
    assert client.post("/answer/stream", json={"thread_id": "nope", "answers": {}}).status_code == 409
    assert client.post("/answer/stream", json={"thread_id": "t", "categories": []}).status_code == 422


def test_answer_stream_rejects_wrong_answer_kind(client, fake_llm, png_bytes):
    fake_llm("prop", extracted(scale="a", function="b", interaction="c"))
    first = parse_sse(
        client.post("/upload/stream", data={"text": "소품"}, files={"image": ("a.png", png_bytes, "image/png")}).text
    )[-1][1]  # 카테고리 확정을 기다리는 상태

    r = client.post("/answer/stream", json={"thread_id": first["thread_id"], "answers": {"scale": "x"}})
    assert r.status_code == 422


def test_upload_stream_rejects_non_image(client):
    r = client.post("/upload/stream", data={"text": "a"}, files={"image": ("a.txt", b"x", "text/plain")})
    assert r.status_code == 415
