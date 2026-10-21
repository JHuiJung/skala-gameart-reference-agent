from pathlib import Path

from app.agent.retriever import PLAN_CATEGORIES, RULE_CATEGORIES
from ingest_docs import CATEGORY_BY_FILE, DOCS_DIR, MAX_CHARS, parse_doc, split_long

DOC = """# 색상 사용 규정

> ⚠️ MOCK 문서: 테스트용

- 문서 상태: 시행 중

## 1. 팔레트 제한
- 주요 색상은 최대 5색

## 2. 표 예시
| 분류 | 값 |
|---|---|
| 몬스터 | 3색 |
"""


def test_short_text_is_not_split():
    assert split_long("짧은 문장") == ["짧은 문장"]


def test_long_text_is_split_by_paragraph():
    paragraphs = [f"문단 {i} " + "가" * 300 for i in range(6)]
    chunks = split_long("\n\n".join(paragraphs))
    assert len(chunks) > 1
    assert all(len(c) <= MAX_CHARS + 400 for c in chunks)  # 문단 하나는 쪼개지 않는다
    assert "".join(chunks).count("문단") == 6  # 내용이 사라지지 않는다


def test_parse_doc_builds_chunks_with_metadata(tmp_path):
    path = tmp_path / "company_rules" / "01_color_rules.md"
    path.parent.mkdir()
    path.write_text(DOC, encoding="utf-8")

    records = parse_doc(path)

    assert len(records) == 2  # ## 섹션마다 한 청크
    first = records[0]
    assert first["metadata"] == {
        "source_type": "company_rules",
        "category": "color",
        "doc_title": "색상 사용 규정",
        "section": "1. 팔레트 제한",
        "file": "01_color_rules.md",
        "status": "시행 중",
    }
    assert first["text"].startswith("색상 사용 규정 > 1. 팔레트 제한")
    assert all("MOCK" not in r["text"] for r in records)  # MOCK 안내문은 청크에 넣지 않는다


def test_table_stays_in_one_chunk(tmp_path):
    path = tmp_path / "company_rules" / "01_color_rules.md"
    path.parent.mkdir()
    path.write_text(DOC, encoding="utf-8")

    table_chunk = parse_doc(path)[1]["text"]
    assert "| 분류 | 값 |" in table_chunk and "| 몬스터 | 3색 |" in table_chunk


def test_every_doc_has_a_category_known_to_the_retriever():
    # 문서를 추가하고 CATEGORY_BY_FILE 에 등록하지 않으면 category 가 'etc' 가 되어 검색에서 영영 찾을 수 없다
    docs = {p.name for p in Path(DOCS_DIR).rglob("*.md")}
    assert docs <= set(CATEGORY_BY_FILE), f"카테고리가 등록되지 않은 문서: {docs - set(CATEGORY_BY_FILE)}"
    # 인제스트가 붙이는 category 값은 모두 검색기(retriever)가 아는 값이어야 한다
    assert set(CATEGORY_BY_FILE.values()) <= set(PLAN_CATEGORIES) | set(RULE_CATEGORIES)
