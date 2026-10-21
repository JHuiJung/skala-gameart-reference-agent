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


def test_answer_rejects_bad_selection_and_brief_payloads(client):
    assert client.post("/answer", json={"thread_id": "t", "selected_ids": []}).status_code == 422
    bad_sections = [{"heading": "a", "outline": "x"}, {"heading": "a", "outline": "y"}]  # 제목 중복
    assert client.post("/answer", json={"thread_id": "t", "brief_sections": bad_sections}).status_code == 422


@pytest.mark.parametrize("count", [0, 11])
def test_answer_rejects_out_of_range_count(client, count):
    r = client.post("/answer", json={"thread_id": "t", "categories": ["a"], "per_category": count})
    assert r.status_code == 422


def test_answer_rejects_empty_categories(client):
    r = client.post("/answer", json={"thread_id": "t", "categories": []})
    assert r.status_code == 422


@pytest.mark.integration
def test_upload_full_flow_creates_folder_with_brief(client, png_bytes, tmp_path, monkeypatch):
    """실제 OpenAI + vector_db + 이미지 검색·저장까지 전체 흐름. 문장이 아니라 구조만 검사한다."""
    from app.agent import storage

    monkeypatch.setattr(storage, "RESULT_DIR", tmp_path / "result")  # 실제 result/ 를 건드리지 않는다

    r = client.post(
        "/upload",
        data={"text": "주황 버섯 몬스터가 겨울 지역에 살아서 따뜻한 외피를 입고 코코아를 든 모습"},
        files={"image": ("a.png", png_bytes, "image/png")},
    )
    body = r.json()
    # 에이전트가 요청하는 답을 순서대로 보내 끝까지 진행한다 (되묻는 내용은 LLM 판단에 따라 달라진다)
    for _ in range(8):
        if body["status"] != "needs_input":
            break
        tid = body["thread_id"]
        if body["kind"] == "confirm_categories":
            payload = {"thread_id": tid, "categories": [c["name"] for c in body["proposed_categories"]], "per_category": 2}
        elif body["kind"] == "select_images":
            assert body["candidates"] and all(c["review"] for c in body["candidates"])  # 검토 결과가 붙어 있다
            names = {c["name"] for c in body["categories"]}
            assert {c["topic"] for c in body["candidates"]} <= names
            payload = {"thread_id": tid, "selected_ids": [body["candidates"][0]["id"]], "save_unverified": False}
        elif body["kind"] == "confirm_brief":
            assert {s["heading"] for s in body["brief_sections"]} >= {"작업 목적 및 디자인 목표", "검토 체크리스트"}
            payload = {"thread_id": tid, "brief_sections": body["brief_sections"], "brief_notes": ""}
        else:
            answers = {q["key"]: "prop" if q["key"] == "asset_type" else "테스트 답변" for q in body["questions"]}
            payload = {"thread_id": tid, "answers": answers}
        body = client.post("/answer", json=payload).json()

    assert body["status"] == "done"
    assert {g["source_type"] for g in body["guidelines"]} == {"confirmed_plans", "company_rules"}
    folder = tmp_path / "result" / "artBrief_001"
    assert body["output"]["folder"] == "result/artBrief_001" and (folder / "references.json").exists()
    brief_text = (folder / "지시서.md").read_text(encoding="utf-8")
    assert brief_text.startswith("# 작업 지시서") and "## 이미지 출처 및 라이선스 확인 정보" in brief_text
