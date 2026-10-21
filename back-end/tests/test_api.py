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


@pytest.mark.integration
def test_upload_full_flow_includes_company_rules(client, png_bytes):
    """실제 OpenAI + vector_db 를 사용하는 전체 흐름. 문장이 아니라 구조만 검사한다."""
    r = client.post(
        "/upload",
        data={"text": "이끼 늑대 몬스터의 색상은 몇 가지까지 써도 돼?"},
        files={"image": ("a.png", png_bytes, "image/png")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["analysis"]["subject"]
    sources = {g["source_type"] for g in body["guidelines"]}
    assert sources == {"confirmed_plans", "company_rules"}
    plan = body["search_plan"]
    assert plan["queries"] and plan["topics"]
