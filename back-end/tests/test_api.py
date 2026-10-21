import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# 아래 두 테스트는 검증 단계에서 끝나므로 그래프(OpenAI)를 호출하지 않는다
def test_upload_rejects_non_image(client):
    r = client.post("/upload", data={"text": "a"}, files={"image": ("a.txt", b"x", "text/plain")})
    assert r.status_code == 415


def test_upload_requires_text(client, png_bytes):
    r = client.post("/upload", data={}, files={"image": ("a.png", png_bytes, "image/png")})
    assert r.status_code == 422


def test_answer_without_waiting_thread_returns_409(client):
    r = client.post("/answer", json={"thread_id": "nope", "answers": {}})
    assert r.status_code == 409


def test_answer_rejects_empty_categories(client):
    r = client.post("/answer", json={"thread_id": "t", "categories": []})
    assert r.status_code == 422


@pytest.mark.integration
def test_upload_full_flow_includes_company_rules(client, png_bytes):
    """실제 OpenAI + vector_db + 이미지 검색 출처를 사용하는 전체 흐름. 문장이 아니라 구조만 검사한다."""
    r = client.post(
        "/upload",
        data={"text": "주황 버섯 몬스터가 겨울 지역에 살아서 따뜻한 외피를 입고 코코아를 든 모습"},
        files={"image": ("a.png", png_bytes, "image/png")},
    )
    body = r.json()
    # 에이전트가 되물으면 임의의 답을 보내 끝까지 진행한다 (되묻는 내용은 LLM 판단에 따라 달라진다)
    for _ in range(4):
        if body["status"] != "needs_input":
            break
        if body["kind"] == "confirm_categories":
            payload = {"thread_id": body["thread_id"], "categories": [c["name"] for c in body["proposed_categories"]]}
        else:
            answers = {q["key"]: "prop" if q["key"] == "asset_type" else "테스트 답변" for q in body["questions"]}
            payload = {"thread_id": body["thread_id"], "answers": answers}
        body = client.post("/answer", json=payload).json()

    assert body["status"] == "done"
    assert body["asset_type"] in {"character", "background", "prop", "ui"}
    assert body["analysis"]["subject"]
    assert {g["source_type"] for g in body["guidelines"]} == {"confirmed_plans", "company_rules"}
    assert body["categories"] and body["candidates"]
    names = {c["name"] for c in body["categories"]}
    assert {c["topic"] for c in body["candidates"]} <= names  # 모든 후보가 확정된 카테고리에 속한다
