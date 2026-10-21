"""vector_db(Chroma)에서 내부 가이드를 검색한다. 저장은 scripts/ingest_docs.py 가 담당한다."""
import asyncio
import os
import threading
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from app.agent.state import Guideline

# 프로젝트 루트(back-end 의 상위)의 vector_db. VECTOR_DB_DIR 환경변수로 바꿀 수 있다.
DB_DIR = Path(os.getenv("VECTOR_DB_DIR", Path(__file__).resolve().parents[3] / "vector_db"))
COLLECTION = "artbrief_docs"
EMBED_MODEL = "text-embedding-3-small"  # scripts/ingest_docs.py 의 EMBED_MODEL 과 같아야 한다

# 인제스트 때 붙인 값 (scripts/ingest_docs.py 의 CATEGORY_BY_FILE 참고)
PLAN_CATEGORIES = ["world", "mood", "background", "monster"]  # source_type = confirmed_plans
RULE_CATEGORIES = ["color", "modeling", "texture", "naming"]  # source_type = company_rules


_collection = None
_lock = threading.Lock()


def get_collection():
    """컬렉션을 처음 쓸 때 한 번만 연다. 여러 스레드가 동시에 처음 호출해도 한 번만 만들도록 락을 건다."""
    global _collection
    with _lock:
        if _collection is None:
            embed_fn = embedding_functions.OpenAIEmbeddingFunction(
                api_key=os.environ["OPENAI_API_KEY"], model_name=EMBED_MODEL
            )
            client = chromadb.PersistentClient(path=str(DB_DIR))
            _collection = client.get_collection(COLLECTION, embedding_function=embed_fn)
    return _collection


def _search(query: str, source_type: str, categories: list[str], n_results: int) -> list[Guideline]:
    where = {"source_type": source_type}
    if categories:  # 카테고리가 없으면 해당 source_type 전체에서 검색
        where = {"$and": [where, {"category": {"$in": categories}}]}
    res = get_collection().query(query_texts=[query], n_results=n_results, where=where)
    return [
        Guideline(
            text=doc,
            source_type=meta["source_type"],
            category=meta["category"],
            file=meta["file"],
            section=meta["section"],
        )
        for doc, meta in zip(res["documents"][0], res["metadatas"][0])
    ]


async def search_guidelines(
    query: str, categories: list[str], plan_k: int = 4, rule_k: int = 3
) -> list[Guideline]:
    """확정된 기획과 회사 규정을 따로 검색해 합친다. (규정이 검색에서 빠지지 않게 하기 위함)

    categories 는 LLM 이 고른 카테고리이며 각 source_type 안에서 범위를 좁히는 데 쓴다.
    Chroma 는 동기 라이브러리라 스레드에서 실행한다.
    """
    plan_cats = [c for c in categories if c in PLAN_CATEGORIES]
    rule_cats = [c for c in categories if c in RULE_CATEGORIES]
    plans, rules = await asyncio.gather(
        asyncio.to_thread(_search, query, "confirmed_plans", plan_cats, plan_k),
        asyncio.to_thread(_search, query, "company_rules", rule_cats, rule_k),
    )
    return plans + rules
