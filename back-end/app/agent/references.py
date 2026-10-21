"""레퍼런스 카테고리 단계: 카테고리 제안 → 사용자 확인·수정 → 카테고리별 이미지 검색.

흐름: plan_categories → confirm_categories(사용자에게 되묻기) → finalize_categories → search_images
"""
import asyncio
import logging

import httpx
from langgraph.types import interrupt

from app.agent.llm import PLANNER_MODEL, get_client
from app.agent.sources import DEFAULT_SOURCES
from app.agent.sources.base import TIMEOUT, USER_AGENT
from app.agent.state import (
    AgentState,
    Candidate,
    CategoryExpansion,
    ReferenceCategory,
    ReferencePlan,
)

PLANNER_PROMPT = """너는 게임 아트팀의 레퍼런스 조사를 이끄는 리서처다.
사용자 요구사항과 내부 가이드를 읽고, 이 작업을 위해 찾아야 할 레퍼런스 카테고리를 스스로 정해라.
- categories: 4~6개. 요구사항의 구성 요소(대상의 형태, 의상, 소품, 배경, 색감·조명 등)를 빠짐없이 나눠 담아라.
  - 사용자가 언급한 모든 요소(대상, 의상, 소품 등)는 각각 카테고리가 되어야 한다.
  - 지역·계절·장소가 언급되면 그 환경을 다루는 배경 카테고리를 반드시 포함해라.
  - 색감·조명 카테고리도 하나 포함해라.
  - name: 사용자에게 보여줄 한국어 이름, 짧게 (예: 겨울 설원 배경, 방한 외투)
  - reason: 이 카테고리가 왜 필요한지 한 문장
  - queries: 이미지 검색용 영문 키워드 2~3개. 카테고리 하나만 설명하도록 구체적으로.
- exclude_terms: 검색 결과에서 걸러낼 영문 단어. 사용자의 제외 요소와 내부 가이드가 피하라고 한 것을 반영해라.
사용자가 말한 조건(계절, 지역, 소재, 소품 등)은 카테고리 이름과 검색 키워드에 반드시 드러나게 해라.
(예: '겨울 지역에 서식'이면 배경 카테고리는 그냥 '숲 배경'이 아니라 '겨울 설원 배경'처럼)
내부 가이드와 충돌하는 키워드는 만들지 마라."""

EXPAND_PROMPT = """사용자가 레퍼런스 카테고리를 새로 추가했다. 작업 맥락을 참고해 각 카테고리의 이유와 검색 키워드를 만들어라.
- 입력으로 주어진 카테고리 이름을 그대로 쓰고, 순서도 유지해라.
- reason: 이 카테고리가 왜 필요한지 한 문장
- queries: 이미지 검색용 영문 키워드 2~3개"""

QUERIES_PER_CATEGORY = 2  # 출처의 호출 한도를 아끼기 위해 카테고리당 사용할 검색 키워드 수
PER_QUERY_LIMIT = 8  # 키워드·출처당 가져올 결과 수
PER_CATEGORY_CANDIDATES = 6  # 카테고리당 보여줄 후보 수
LICENSE_RANK = {"confirmed": 0, "unclear": 1, "restricted": 2}  # 상업 이용이 확실한 것을 먼저
MAX_CONCURRENT_REQUESTS = 6  # 동시에 보내는 검색 요청 수 (출처에 부담을 주지 않도록)

logger = logging.getLogger(__name__)


def _format_for_planner(state: AgentState) -> str:
    """카테고리 제안 LLM 에 넘길 입력(요구사항 + 내부 가이드)을 텍스트로 만든다."""
    a = state["analysis"]
    guide_text = "\n\n".join(f"[{g.file} > {g.section}]\n{g.text}" for g in state.get("guidelines", []))
    return f"## 사용자 요구사항\n{a.model_dump_json(indent=2)}\n\n## 내부 가이드\n{guide_text}"


async def plan_categories(state: AgentState) -> dict:
    """[3단계] 요구사항과 내부 가이드를 보고 레퍼런스 카테고리 초안(이름, 이유, 검색 키워드)을 만든다."""
    completion = await get_client().chat.completions.parse(
        model=PLANNER_MODEL,
        messages=[
            {"role": "system", "content": PLANNER_PROMPT},
            {"role": "user", "content": _format_for_planner(state)},
        ],
        response_format=ReferencePlan,
    )
    return {"reference_plan": completion.choices[0].message.parsed, "current_step": "레퍼런스 카테고리 제안"}


def confirm_categories(state: AgentState) -> dict:
    """[3-1단계] 제안한 카테고리를 사용자에게 보여주고 첨삭을 받는다. (사용자가 확정할 때까지 멈춘다)"""
    proposal = state["reference_plan"].categories
    answers = interrupt({
        "kind": "confirm_categories",
        "categories": [c.model_dump(include={"name", "reason"}) for c in proposal],
    })
    return {"confirmed_names": answers["categories"], "current_step": "카테고리 확정"}


async def finalize_categories(state: AgentState) -> dict:
    """[3-2단계] 확정된 이름을 검색 가능한 카테고리로 만든다.

    AI 가 제안했던 카테고리는 기존 검색 키워드를 그대로 쓰고,
    사용자가 새로 추가한 카테고리만 LLM 으로 이유와 검색 키워드를 만든다.
    """
    proposed = {c.name: c for c in state["reference_plan"].categories}
    names = list(dict.fromkeys(state["confirmed_names"]))  # 순서를 유지하며 중복 제거
    new_names = [n for n in names if n not in proposed]

    created: dict[str, ReferenceCategory] = {}
    if new_names:
        context = state["analysis"].model_dump_json(indent=2)
        completion = await get_client().chat.completions.parse(
            model=PLANNER_MODEL,
            messages=[
                {"role": "system", "content": EXPAND_PROMPT},
                {"role": "user", "content": f"## 작업 맥락\n{context}\n\n## 추가된 카테고리\n" + "\n".join(new_names)},
            ],
            response_format=CategoryExpansion,
        )
        created = {c.name: c for c in completion.choices[0].message.parsed.categories}

    # LLM 이 이름을 바꾸거나 빠뜨려도 사용자가 입력한 이름 그대로, 검색어는 이름 자체라도 갖도록 보완한다
    final = [
        proposed.get(n) or created.get(n) or ReferenceCategory(name=n, queries=[n])
        for n in names
    ]
    return {"final_categories": final, "current_step": "카테고리 검색어 준비"}


def _is_excluded(c: Candidate, exclude_terms: list[str]) -> bool:
    text = " ".join([c.title, *c.tags]).lower()
    return any(term.lower() in text for term in exclude_terms)


def merge_candidates(
    batches: list[list[Candidate]],
    exclude_terms: list[str],
    seen: set[str],
    limit: int = PER_CATEGORY_CANDIDATES,
) -> list[Candidate]:
    """한 카테고리의 여러 (키워드, 출처) 검색 결과를 하나로 합친다.

    1) 제외어가 제목·태그에 있는 후보 제거  2) 이미지 주소 기준 중복 제거 (seen 은 카테고리 간 공유)
    3) 키워드·출처가 골고루 섞이도록 번갈아 배치  4) 라이선스가 확실한 후보를 앞으로 (순서 유지)
    """
    merged: list[Candidate] = []
    longest = max((len(b) for b in batches), default=0)
    for rank in range(longest):  # 각 결과 목록의 1등끼리, 2등끼리 ... 순서로 섞는다
        for batch in batches:
            if rank >= len(batch):
                continue
            c = batch[rank]
            if c.image_url in seen or _is_excluded(c, exclude_terms):
                continue
            seen.add(c.image_url)
            merged.append(c)
    merged.sort(key=lambda c: LICENSE_RANK[c.license])  # 안정 정렬이라 같은 등급 안에서는 순서가 유지된다
    return merged[:limit]


async def search_images(state: AgentState) -> dict:
    """[4단계] 확정된 카테고리마다 키 없이 쓸 수 있는 출처(Openverse, Wikimedia)에서 이미지 후보를 모은다."""
    categories = state["final_categories"]
    exclude_terms = state["reference_plan"].exclude_terms
    errors: list[str] = []
    gate = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async with httpx.AsyncClient(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:

        async def run(source, query):
            async with gate:
                try:
                    return await source.search(client, query, PER_QUERY_LIMIT)
                except Exception as e:  # 한 출처가 실패해도 나머지 결과로 계속 진행한다
                    logger.warning("%s 검색 실패 (%s): %s", source.name, query, e)
                    errors.append(f"{source.name}: {type(e).__name__}")
                    return []

        per_category = await asyncio.gather(*[
            asyncio.gather(*[run(src, q) for q in cat.queries[:QUERIES_PER_CATEGORY] for src in DEFAULT_SOURCES])
            for cat in categories
        ])

    seen: set[str] = set()  # 같은 이미지가 여러 카테고리에 중복으로 나오지 않게 한다
    candidates: list[Candidate] = []
    for cat, batches in zip(categories, per_category):
        for c in merge_candidates(list(batches), exclude_terms, seen):
            candidates.append(c.model_copy(update={"topic": cat.name}))

    return {"candidates": candidates, "source_errors": sorted(set(errors)), "current_step": "웹 이미지 검색"}
