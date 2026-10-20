"""docs/ 의 마크다운 문서를 청킹하고 카테고리 메타데이터를 붙여 Chroma(vector_db/)에 저장한다.

실행: python scripts/ingest_docs.py
"""
import re
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
import os

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs"
DB_DIR = ROOT / "vector_db"
COLLECTION = "artbrief_docs"
EMBED_MODEL = "text-embedding-3-small"
MAX_CHARS = 800

# 파일명 -> 카테고리 (폴더명은 source_type 으로 그대로 사용)
CATEGORY_BY_FILE = {
    "01_world_setting.md": "world",
    "02_mood_art_direction.md": "mood",
    "03_background_forest_village_loen.md": "background",
    "04_monster_moss_wolf.md": "monster",
    "05_monster_mist_giant.md": "monster",
    "06_monster_thorn_wisp.md": "monster",
    "01_color_rules.md": "color",
    "02_modeling_optimization_rules.md": "modeling",
    "03_texture_resource_rules.md": "texture",
    "04_file_naming_delivery_rules.md": "naming",
}


def split_long(text: str) -> list[str]:
    """MAX_CHARS 를 넘는 섹션을 빈 줄(문단·표·코드블록 단위) 기준으로 나눈다."""
    if len(text) <= MAX_CHARS:
        return [text]
    chunks, buf = [], ""
    for para in re.split(r"\n\s*\n", text):
        if buf and len(buf) + len(para) + 2 > MAX_CHARS:
            chunks.append(buf)
            buf = para
        else:
            buf = f"{buf}\n\n{para}" if buf else para
    if buf:
        chunks.append(buf)
    return chunks


def parse_doc(path: Path) -> list[dict]:
    lines = [l for l in path.read_text(encoding="utf-8").splitlines() if not l.startswith("> ⚠️")]
    title = next((l[2:].strip() for l in lines if l.startswith("# ")), path.stem)

    sections: list[tuple[str, list[str]]] = [("개요", [])]
    for line in lines:
        if line.startswith("# "):
            continue
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        else:
            sections[-1][1].append(line)

    preamble = "\n".join(sections[0][1])
    m = re.search(r"문서 상태:\s*(.+)", preamble)
    status = m.group(1).strip() if m else ""

    records = []
    for section, body_lines in sections[1:]:
        body = "\n".join(body_lines).strip()
        if not body:
            continue
        for part in split_long(body):
            records.append({
                # 임베딩 품질을 위해 문서 제목 > 섹션명을 청크 앞에 붙인다
                "text": f"{title} > {section}\n{part}",
                "metadata": {
                    "source_type": path.parent.name,
                    "category": CATEGORY_BY_FILE.get(path.name, "etc"),
                    "doc_title": title,
                    "section": section,
                    "file": path.name,
                    "status": status,
                },
            })
    return records


def main():
    load_dotenv(ROOT / ".env")
    embed_fn = embedding_functions.OpenAIEmbeddingFunction(
        api_key=os.environ["OPENAI_API_KEY"], model_name=EMBED_MODEL
    )

    records = []
    for path in sorted(DOCS_DIR.rglob("*.md")):
        records.extend(parse_doc(path))

    client = chromadb.PersistentClient(path=str(DB_DIR))
    try:  # 재실행 시 중복 방지를 위해 컬렉션을 새로 만든다
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    col = client.create_collection(COLLECTION, embedding_function=embed_fn)

    ids = [f"{r['metadata']['file']}::{i}" for i, r in enumerate(records)]
    col.add(
        ids=ids,
        documents=[r["text"] for r in records],
        metadatas=[r["metadata"] for r in records],
    )

    print(f"{len(records)}개 청크 저장 완료 -> {DB_DIR}")
    counts: dict[str, int] = {}
    for r in records:
        key = f"{r['metadata']['source_type']}/{r['metadata']['category']}"
        counts[key] = counts.get(key, 0) + 1
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
