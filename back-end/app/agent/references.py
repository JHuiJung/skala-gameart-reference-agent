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
from app.agent.progress import emit_detail
from app.agent.retriever import search_scoped
from app.agent.state import (
    AgentState,
    Candidate,
    CategoryExpansion,
    GroundedCategories,
    ReferenceCategory,
    ReferencePlan,
)

PLANNER_PROMPT = """너는 게임 아트팀의 레퍼런스 조사를 이끄는 리서처다.
사용자 요구사항과 내부 가이드를 읽고, 이 작업을 위해 찾아야 할 레퍼런스 카테고리를 스스로 정해라.
먼저 '사용자 요청 원문'과 '최종 목표(goal)'를 읽어라. 카테고리와 검색 키워드는 이미지의 현재 모습이 아니라 **최종 목표**를 기준으로 정한다.
- 사용자가 변경·변형을 요구했다면(예: 차가운 지역 버전으로), 변경된 모습을 찾는 카테고리여야 한다.
  이미지의 현재 모습(예: 버섯 모자, 가벼운 옷)은 변경 대상이면 검색어로 쓰지 마라.
- categories: 4~6개. 요구사항의 구성 요소(대상의 형태, 의상, 소품, 배경, 색감·조명 등)를 빠짐없이 나눠 담아라.
  - 사용자가 언급한 모든 요소(대상, 의상, 소품 등)는 각각 카테고리가 되어야 한다.
  - 지역·계절·장소가 언급되면 그 환경을 다루는 배경 카테고리를 반드시 포함해라.
  - 색감·조명 카테고리도 하나 포함해라.
  - name: 사용자에게 보여줄 한국어 이름, 짧게 (예: 겨울 설원 배경, 방한 외투)
  - reason: 이 카테고리가 왜 필요한지 한 문장
  - queries: 이미지 검색용 영문 키워드 2~3개. 카테고리 하나만 설명하도록 구체적으로.
- exclude_terms: 검색 결과에서 걸러낼 영문 단어. 사용자가 명시적으로 원하지 않는다고 말한 것과 내부 가이드가 금지한 것만 넣어라.
  요구사항과 반대되는 속성을 추측해서 넣지 마라. (예: 사용자가 '따뜻한 겨울 외피'를 원하면 'warm'을, 주황 몬스터를 원하면 'orange'를 넣으면 안 된다)
사용자가 말한 조건(계절, 지역, 소재, 소품 등)은 카테고리 이름과 검색 키워드에 반드시 드러나게 해라.
(예: '겨울 지역에 서식'이면 배경 카테고리는 그냥 '숲 배경'이 아니라 '겨울 설원 배경'처럼)
내부 가이드와 충돌하는 키워드는 만들지 마라."""

EXPAND_PROMPT = """사용자가 레퍼런스 카테고리를 새로 추가했다. 작업 맥락을 참고해 각 카테고리의 이유와 검색 키워드를 만들어라.
- 입력으로 주어진 카테고리 이름을 그대로 쓰고, 순서도 유지해라.
- 검색 키워드는 이미지의 현재 모습이 아니라 사용자의 최종 목표를 기준으로 만들어라.
- reason: 이 카테고리가 왜 필요한지 한 문장
- queries: 이미지 검색용 영문 키워드 2~3개"""

GROUND_PROMPT = """너는 게임 아트 레퍼런스 검색어를 세계관에 맞게 다듬는 리서처다.
아래 카테고리들의 검색 키워드를 '게임 세계관·기획 가이드'에 맞게 다시 써라.
- '세계관 공통 가이드'는 모든 카테고리에 적용한다. 시대 기준 영문 키워드(예: late medieval, medieval)를
  검색어에 녹여라. 현대 소재·현대 물건이 검색되지 않게 하기 위해서다. (예: 'winter coat' 가 아니라 'medieval winter cloak')
- '카테고리별 가이드'는 해당 카테고리에만 적용한다. 허용 소재, 선별 기준, 권장 검색 키워드가 있으면 따라라.
- 사용자의 최종 목표(변경·변형 요구, 지역, 계절 등)는 그대로 유지해라. 세계관 때문에 목표를 바꾸지 마라.
- 사용자가 요청한 대상이 세계관에 없는 것이면(가이드가 없다고 명시한 소재 등) 형태와 역할은 유지하되 가이드가 제시한 대체물로 바꿔 검색어를 만들고, applied_rules 에 이유를 적어라.
- 카테고리 이름은 그대로 두고, 입력 순서대로 모두 돌려줘라. 검색어(queries)는 영문 2~3개.
- applied_rules: 반영한 **가이드 규칙 그 자체**를 짧은 한국어로 1~2개. 무엇을 바꿨는지가 아니라 어떤 규칙 때문인지를 적어라.
  좋은 예: "중세 후기 복식 기준: 울·가죽 소재, 현대 의류 금지", "코코아는 세계관에 없음 → 허브차·따뜻한 우유로 대체"
  나쁜 예: "검색어에 medieval 키워드를 추가함"
  가이드에 해당 내용이 없으면 빈 리스트. 가이드에 없는 내용을 지어내지 마라.
- era_keyword: 세계관 공통 가이드의 시대 기준을 나타내는 가장 짧고 일반적인 영문 키워드 하나 (예: medieval). 없으면 빈 문자열.
- exclude_terms: 세계관 공통 가이드에 '공통 제외 키워드'가 있으면 그대로 옮기고, 카테고리별 가이드가 금지한 요소도 더해라. **가이드에 명시된** 영문 단어만. 사용자 요청에 필요한 속성(색, 분위기 등)은 절대 넣지 마라."""

QUERIES_PER_CATEGORY = 2  # 출처의 호출 한도를 아끼기 위해 카테고리당 사용할 검색 키워드 수
PER_QUERY_LIMIT = 8  # 키워드·출처당 가져올 결과 수
DEFAULT_PER_CATEGORY = 5  # 사용자가 고르지 않았을 때 카테고리당 보여줄 이미지 수
POOL_MULTIPLIER = 2  # 이미지 검토에서 탈락하는 것을 감안해, 보여줄 수의 몇 배를 먼저 모을지
MIN_POOL, MAX_POOL = 6, 20  # 카테고리당 검토 대상 이미지 수의 하한·상한 (검토 비용 제한)
LICENSE_RANK = {"confirmed": 0, "unclear": 1, "restricted": 2}  # 상업 이용이 확실한 것을 먼저
WORLD_CATEGORIES = ["world", "mood"]  # 모든 카테고리에 공통으로 적용하는 세계관 가이드
WORLD_KEYWORD_QUERY = "레퍼런스 검색 키워드 가이드. 시대 기준, 공통 포함 키워드, 공통 제외 키워드"
GUIDES_PER_CATEGORY = 3  # 질의 하나당 찾아 올 가이드 조각 수
MAX_GUIDES_PER_CATEGORY = 5  # 카테고리 하나에 LLM 에게 보여줄 가이드 조각 수 상한
MAX_CONCURRENT_REQUESTS = 10  # 동시에 보내는 검색 요청 수 (출처에 부담을 주지 않도록)

logger = logging.getLogger(__name__)


def _format_for_planner(state: AgentState) -> str:
    """카테고리 제안 LLM 에 넘길 입력(요구사항 + 내부 가이드)을 텍스트로 만든다."""
    a = state["analysis"]
    guide_text = "\n\n".join(f"[{g.file} > {g.section}]\n{g.text}" for g in state.get("guidelines", []))
    return (
        f"## 사용자 요청 원문\n{state.get('text', '')}\n\n"
        f"## 최종 목표(goal)\n{a.goal}\n\n"
        f"## 분석된 요구사항\n{a.model_dump_json(indent=2)}\n\n"
        f"## 내부 가이드\n{guide_text}"
    )


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


def _format_guides(guides) -> str:
    return "\n\n".join(f"[{g.file} > {g.section}]\n{g.text}" for g in guides) or "(관련 가이드 없음)"


def _drop_conflicting_excludes(exclude_terms: list[str], categories: list[ReferenceCategory]) -> list[str]:
    """검색어에 쓰인 단어가 제외어에도 있으면 제외어에서 뺀다.

    제외어는 이미지의 제목·태그에 그 단어가 있으면 걸러내므로, 검색어와 겹치면 찾은 결과를 스스로 지워 버린다.
    (예: 검색어 'warm milk' 와 제외어 'warm')
    """
    queries = [q.lower() for c in categories for q in c.queries]
    return [t for t in exclude_terms if not any(t.lower() in q for q in queries)]


def _ensure_era(queries: list[str], era_keyword: str) -> list[str]:
    """시대 키워드가 검색어에 하나도 없으면 첫 검색어 앞에 붙인다.

    LLM 이 프롬프트의 '시대 키워드를 넣어라'는 지시를 자주 빠뜨려서, 세계관 반영의 핵심인 이 부분은 코드로 보장한다.
    """
    era = era_keyword.strip().lower()
    if not era or any(era in q.lower() for q in queries):
        return queries
    return [f"{era_keyword.strip()} {queries[0]}", *queries[1:]]


async def _category_guides(c: ReferenceCategory) -> list:
    """카테고리 하나에 관련된 기획 가이드를 찾는다.

    질의를 두 가지로 나눠 합친다. 이름만 짧게 찾으면 정확한 문서가 잘 나오고(예: '코코아 소품' → 음료 소품 가이드),
    이유까지 붙이면 문맥이 풍부해진다. 길고 영문이 섞인 질의는 엉뚱한 문서(예: 몬스터 기획)를 끌어오므로 쓰지 않는다.
    """
    found = await asyncio.gather(
        search_scoped(c.name, "confirmed_plans", [], GUIDES_PER_CATEGORY),
        search_scoped(f"{c.name}. {c.reason}", "confirmed_plans", [], GUIDES_PER_CATEGORY),
    )
    unique = {(g.file, g.section): g for guides in found for g in guides}  # 같은 청크는 한 번만
    return list(unique.values())[:MAX_GUIDES_PER_CATEGORY]


async def _ground(state: AgentState, categories: list[ReferenceCategory]) -> tuple[list[ReferenceCategory], list[str]]:
    """카테고리마다 관련 세계관·기획 가이드를 찾아, 검색어를 세계관에 맞게 다시 쓴다 (RAG).

    1) 세계관 공통 가이드(시대·지역·분위기)를 한 번 찾고  2) 카테고리별 가이드를 각각 찾고  3) LLM 이 둘을 반영해 검색어를 다시 쓴다.
    반환: (다시 쓴 카테고리, 가이드가 금지한 제외어)
    """
    goal = state["analysis"].goal or state.get("text", "")
    world_by_goal, world_keywords, *per_category = await asyncio.gather(
        search_scoped(goal, "confirmed_plans", WORLD_CATEGORIES, GUIDES_PER_CATEGORY),
        # 시대·공통 검색 키워드 가이드는 요청 내용과 상관없이 항상 필요하므로 따로 찾는다
        search_scoped(WORLD_KEYWORD_QUERY, "confirmed_plans", ["world"], 1),
        *[_category_guides(c) for c in categories],
    )
    world = list({(g.file, g.section): g for g in [*world_keywords, *world_by_goal]}.values())

    sections = [
        f"## 사용자 요청 원문\n{state.get('text', '')}\n\n## 최종 목표\n{state['analysis'].goal}",
        f"## 세계관 공통 가이드\n{_format_guides(world)}",
    ]
    for c, guides in zip(categories, per_category):
        sections.append(
            f"## 카테고리: {c.name}\n이유: {c.reason}\n현재 검색어: {', '.join(c.queries)}\n"
            f"### 카테고리별 가이드\n{_format_guides(guides)}"
        )

    completion = await get_client().chat.completions.parse(
        model=PLANNER_MODEL,
        messages=[
            {"role": "system", "content": GROUND_PROMPT},
            {"role": "user", "content": "\n\n".join(sections)},
        ],
        response_format=GroundedCategories,
    )
    parsed = completion.choices[0].message.parsed
    grounded = {c.name: c for c in parsed.categories}

    # LLM 이 카테고리를 빠뜨리거나 이름을 바꿨다면 원래 카테고리를 그대로 쓴다
    result = []
    for c in categories:
        g = grounded.get(c.name)
        if g and g.queries:
            c = c.model_copy(update={"queries": _ensure_era(g.queries, parsed.era_keyword), "applied_rules": g.applied_rules})
        result.append(c)
    return result, parsed.exclude_terms


async def ground_categories(state: AgentState) -> dict:
    """[3-1단계] 제안된 카테고리의 검색어에 게임 세계관(시대·지역·소재 기준)을 반영한다."""
    plan = state["reference_plan"]
    categories, extra_exclude = await _ground(state, plan.categories)
    merged_exclude = list(dict.fromkeys([*plan.exclude_terms, *extra_exclude]))
    return {
        "reference_plan": ReferencePlan(categories=categories, exclude_terms=merged_exclude),
        "current_step": "세계관 가이드 반영",
    }


def confirm_categories(state: AgentState) -> dict:
    """[3-2단계] 제안한 카테고리를 사용자에게 보여주고 첨삭을 받는다. (사용자가 확정할 때까지 멈춘다)"""
    proposal = state["reference_plan"].categories
    answers = interrupt({
        "kind": "confirm_categories",
        "goal": state["analysis"].goal,  # 사용자가 AI 의 요청 이해가 맞는지 바로 확인할 수 있게 함께 보여준다
        "categories": [c.model_dump(include={"name", "reason", "applied_rules"}) for c in proposal],
    })
    return {
        "confirmed_names": answers["categories"],
        "per_category": answers.get("per_category", DEFAULT_PER_CATEGORY),
        "current_step": "카테고리 확정",
    }


async def finalize_categories(state: AgentState) -> dict:
    """[3-3단계] 확정된 이름을 검색 가능한 카테고리로 만든다.

    AI 가 제안했던 카테고리는 기존 검색 키워드를 그대로 쓰고,
    사용자가 새로 추가한 카테고리만 LLM 으로 이유와 검색 키워드를 만든다.
    """
    proposed = {c.name: c for c in state["reference_plan"].categories}
    names = list(dict.fromkeys(state["confirmed_names"]))  # 순서를 유지하며 중복 제거
    new_names = [n for n in names if n not in proposed]

    created: dict[str, ReferenceCategory] = {}
    if new_names:
        context = f"사용자 요청 원문: {state.get('text', '')}\n최종 목표: {state['analysis'].goal}\n" + state["analysis"].model_dump_json(indent=2)
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
    new_categories = [created.get(n) or ReferenceCategory(name=n, queries=[n]) for n in new_names]

    # 사용자가 새로 추가한 카테고리도 AI 가 제안한 것과 똑같이 세계관 가이드를 반영한다
    plan = state["reference_plan"]
    exclude_terms = plan.exclude_terms
    if new_categories:
        new_categories, extra_exclude = await _ground(state, new_categories)
        exclude_terms = list(dict.fromkeys([*exclude_terms, *extra_exclude]))
    grounded_new = {c.name: c for c in new_categories}

    final = [proposed.get(n) or grounded_new[n] for n in names]
    # 실제로 검색에 쓸 키워드만 남긴다. 화면에 보여주는 "검색에 사용한 단어"가 사실과 같도록 여기서 자른다
    final = [c.model_copy(update={"queries": c.queries[:QUERIES_PER_CATEGORY]}) for c in final]
    return {
        "final_categories": final,
        "reference_plan": ReferencePlan(
            categories=plan.categories, exclude_terms=_drop_conflicting_excludes(exclude_terms, final)
        ),
        "current_step": "카테고리 검색어 준비",
    }


def _is_excluded(c: Candidate, exclude_terms: list[str]) -> bool:
    text = " ".join([c.title, *c.tags]).lower()
    return any(term.lower() in text for term in exclude_terms)


def merge_candidates(
    batches: list[list[Candidate]],
    exclude_terms: list[str],
    seen: set[str],
    limit: int,
    web_slots: int | None = None,
) -> list[Candidate]:
    """한 카테고리의 여러 (키워드, 출처) 검색 결과를 하나로 합친다.

    1) 제외어가 제목·태그에 있는 후보 제거  2) 이미지 주소 기준 중복 제거 (seen 은 카테고리 간 공유)
    3) 키워드·출처가 골고루 섞이도록 번갈아 배치
    4) 라이선스가 확실한 후보(confirmed)를 우선하되, 불확실한 후보(웹 검색 등)에도 web_slots 개의 자리를 보장한다.
       결과는 확실한 후보가 앞에 오도록 정렬한다.
    """
    pool: list[Candidate] = []
    longest = max((len(b) for b in batches), default=0)
    for rank in range(longest):  # 각 결과 목록의 1등끼리, 2등끼리 ... 순서로 섞는다
        for batch in batches:
            if rank >= len(batch):
                continue
            c = batch[rank]
            if c.image_url in seen or _is_excluded(c, exclude_terms):
                continue
            seen.add(c.image_url)
            pool.append(c)

    web_slots = max(1, limit // 3) if web_slots is None else web_slots  # 라이선스가 불확실한 웹 검색 결과에 보장하는 자리
    confirmed = [c for c in pool if c.license == "confirmed"]
    others = sorted((c for c in pool if c.license != "confirmed"), key=lambda c: LICENSE_RANK[c.license])
    reserved = others[: min(web_slots, limit)]
    picked = confirmed[: limit - len(reserved)]
    picked += reserved
    # 확실한 후보가 모자라 자리가 남으면 불확실한 후보로 채운다
    picked += [c for c in others if c not in reserved][: limit - len(picked)]
    picked.sort(key=lambda c: LICENSE_RANK[c.license])  # 안정 정렬: 같은 등급 안에서는 순서 유지
    return picked


async def search_images(state: AgentState) -> dict:
    """[4단계] 확정된 카테고리마다 이미지 검색 출처(Openverse, Wikimedia, Tavily)에서 검토 대상 후보를 모은다."""
    categories = state["final_categories"]
    exclude_terms = state["reference_plan"].exclude_terms
    pool_size = min(max(state.get("per_category", DEFAULT_PER_CATEGORY) * POOL_MULTIPLIER, MIN_POOL), MAX_POOL)
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

        finished = 0

        async def search_category(cat):
            nonlocal finished
            batches = await asyncio.gather(*[run(src, q) for q in cat.queries for src in DEFAULT_SOURCES])
            finished += 1
            emit_detail(f"'{cat.name}' 검색 완료 ({finished}/{len(categories)})")
            return batches

        per_category = await asyncio.gather(*[search_category(cat) for cat in categories])

    seen: set[str] = set()  # 같은 이미지가 여러 카테고리에 중복으로 나오지 않게 한다
    candidates: list[Candidate] = []
    for cat, batches in zip(categories, per_category):
        for c in merge_candidates(list(batches), exclude_terms, seen, pool_size):
            candidates.append(c.model_copy(update={"topic": cat.name}))

    return {"candidates": candidates, "source_errors": sorted(set(errors)), "current_step": "웹 이미지 검색"}
