"""검색으로 모은 후보 이미지가 카테고리·최종 목표·세계관에 적합한지 비전 모델로 검토한다.

흐름: 이미지 내려받기(검토용, 저장하지 않음) → 10장씩 비전 모델에 보내 0~10점 → 기준 미달 제거 → 상위 N장만 남김
"""
import asyncio
import base64
import logging

import httpx

from app.agent.llm import REVIEW_MODEL, get_client
from app.agent.references import DEFAULT_PER_CATEGORY, LICENSE_RANK
from app.agent.sources.base import USER_AGENT
from app.agent.state import AgentState, Candidate, ImageReview, ReferenceCategory

BATCH_SIZE = 10  # 한 번에 비전 모델에 보내는 이미지 수
PASS_SCORE = 6  # 10점 만점에서 이 점수 이상이어야 적합으로 본다
MAX_IMAGE_BYTES = 4 * 1024 * 1024  # 검토용으로 내려받는 이미지 최대 크기
DOWNLOAD_TIMEOUT = httpx.Timeout(15.0)
MAX_CONCURRENT_DOWNLOADS = 8
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

NOT_LOADED = "이미지를 불러오지 못해 검토할 수 없었어요."
NOT_REVIEWED = "검토하지 못했어요."

REVIEW_PROMPT = """너는 게임 아트팀의 레퍼런스 이미지 검수자다.
각 이미지가 아래 카테고리의 레퍼런스로 적합한지 0~10점으로 평가해라.

이 이미지는 **오직 이 카테고리 하나**의 레퍼런스로 쓰인다. 사용자의 최종 목표 전체를 이미지 한 장이 만족할 필요는 없다.
다른 카테고리가 맡는 대상이 없다고 감점하지 마라. (예: 의상 이미지에 몬스터가 없거나, 배경·색감 이미지에 소품이 없는 것은 문제가 아니다)

평가 기준 (모두 만족해야 높은 점수):
1. 이 카테고리의 대상이 이미지에 분명히 보인다.
2. 최종 목표 중 이 카테고리와 관련된 방향을 따른다. (예: 의상 카테고리이고 목표가 '차가운 지역 버전'이면 방한 의상이어야 한다)
3. 세계관 규칙을 어기지 않는다. 시대에 맞지 않는 현대 요소(현대 의류, 플라스틱, 로고, 현대 건물 등)가 보이면 크게 감점한다.
4. 상품 판매 사진, 코스튬·코스프레 사진, 워터마크로 가려진 사진은 레퍼런스로 부적합해 감점한다.

점수 가이드: 9~10 매우 적합 / 6~8 쓸 만함 / 3~5 일부만 맞음 / 0~2 무관하거나 규칙 위반.
reason 은 한국어 한 문장으로, 이미지에서 실제로 보이는 것을 근거로 적어라. 각 이미지를 번호대로 모두 평가해라."""


async def _fetch_image(client: httpx.AsyncClient, url: str) -> tuple[str, bytes] | None:
    """이미지 하나를 내려받는다. 이미지가 아니거나 너무 크거나 요청이 실패하면 None."""
    try:
        res = await client.get(url)
        res.raise_for_status()
    except httpx.HTTPError:
        return None
    content_type = res.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in IMAGE_TYPES or len(res.content) > MAX_IMAGE_BYTES:
        return None
    return content_type, res.content


async def _to_data_url(client: httpx.AsyncClient, gate: asyncio.Semaphore, candidate: Candidate) -> str | None:
    """검토용으로 이미지를 내려받아 data URL 로 만든다. 실패하면 None. (서버에 저장하지 않는다)

    작은 썸네일을 먼저 시도하고, 실패하면 원본으로 한 번 더 시도한다.
    (Openverse 썸네일은 간헐적으로 실패하고, Wikimedia 원본은 요청 제한(429)에 자주 걸려서 이 순서가 가장 잘 된다)
    """
    urls = list(dict.fromkeys([candidate.thumbnail_url or candidate.image_url, candidate.image_url]))
    async with gate:
        for url in urls:
            fetched = await _fetch_image(client, url)
            if fetched:
                content_type, content = fetched
                return f"data:{content_type};base64,{base64.b64encode(content).decode()}"
    return None


def _context(state: AgentState, category: ReferenceCategory) -> str:
    plan = state.get("reference_plan")
    exclude = ", ".join(plan.exclude_terms) if plan else ""
    return (
        f"## 사용자 요청 원문\n{state.get('text', '')}\n\n"
        f"## 최종 목표\n{state['analysis'].goal}\n\n"
        f"## 카테고리\n이름: {category.name}\n이유: {category.reason}\n"
        f"반영해야 할 세계관 규칙: {'; '.join(category.applied_rules) or '(없음)'}\n"
        f"보이면 안 되는 요소: {exclude or '(없음)'}"
    )


async def _review_batch(state, category, items: list[tuple[Candidate, str]]) -> dict[int, tuple[int, str]]:
    """이미지 한 묶음을 검토해 {번호: (점수, 이유)} 로 돌려준다."""
    content: list[dict] = [{"type": "text", "text": _context(state, category)}]
    for number, (candidate, data_url) in enumerate(items, start=1):
        content.append({"type": "text", "text": f"[이미지 {number}] 검색어: {candidate.reason.removeprefix('검색어: ')}"})
        content.append({"type": "image_url", "image_url": {"url": data_url, "detail": "low"}})

    completion = await get_client().chat.completions.parse(
        model=REVIEW_MODEL,
        messages=[{"role": "system", "content": REVIEW_PROMPT}, {"role": "user", "content": content}],
        response_format=ImageReview,
    )
    return {v.index: (v.score, v.reason) for v in completion.choices[0].message.parsed.verdicts}


async def _review_category(state, http, gate, category, candidates, want, errors):
    """한 카테고리의 후보를 검토해 (남길 후보, 걸러낸 후보)를 돌려준다."""
    data_urls = await asyncio.gather(*[_to_data_url(http, gate, c) for c in candidates])

    scored: list[Candidate] = []  # 검토를 마친 후보
    unreviewed: list[Candidate] = []  # 검토 호출이 실패한 후보 (적합 여부를 모름)
    rejected: list[Candidate] = []

    loadable = []
    for c, url in zip(candidates, data_urls):
        if url is None:
            rejected.append(c.model_copy(update={"review": NOT_LOADED}))
        else:
            loadable.append((c, url))

    batches = [loadable[i:i + BATCH_SIZE] for i in range(0, len(loadable), BATCH_SIZE)]

    async def run(batch):
        try:
            return batch, await _review_batch(state, category, batch)
        except Exception as e:  # 검토가 실패해도 후보를 모두 잃지 않도록 한다
            logging.getLogger(__name__).warning("이미지 검토 실패 (%s): %s", category.name, e)
            errors.append(f"이미지 검토: {type(e).__name__}")
            return batch, None

    for batch, verdicts in await asyncio.gather(*[run(b) for b in batches]):
        for number, (c, _) in enumerate(batch, start=1):
            if verdicts is None or number not in verdicts:
                unreviewed.append(c.model_copy(update={"review": NOT_REVIEWED}))
                continue
            score, reason = verdicts[number]
            reviewed = c.model_copy(update={"score": score / 10, "review": reason})
            (scored if score >= PASS_SCORE else rejected).append(reviewed)

    # 점수가 높은 순, 같으면 라이선스가 확실한 순. 모자라면 검토하지 못한 후보로 채운다
    scored.sort(key=lambda c: (-c.score, LICENSE_RANK[c.license]))
    kept = (scored + unreviewed)[:want]
    return kept, rejected


async def review_images(state: AgentState) -> dict:
    """[4-1단계] 카테고리별 후보를 검토해 적합한 이미지만, 사용자가 고른 개수만큼 남긴다."""
    want = state.get("per_category", DEFAULT_PER_CATEGORY)
    errors = list(state.get("source_errors", []))
    gate = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

    async with httpx.AsyncClient(
        timeout=DOWNLOAD_TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True
    ) as http:
        results = await asyncio.gather(*[
            _review_category(
                state, http, gate, cat, [c for c in state["candidates"] if c.topic == cat.name], want, errors
            )
            for cat in state["final_categories"]
        ])

    return {
        "candidates": [c for kept, _ in results for c in kept],
        "rejected_candidates": [c for _, rejected in results for c in rejected],
        "source_errors": sorted(set(errors)),
        "current_step": "이미지 적합성 검토",
    }
