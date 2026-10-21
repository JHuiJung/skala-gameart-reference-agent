"""선택한 레퍼런스 이미지를 result/artBrief_NNN/<카테고리>/ 에 저장한다."""
import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path

import httpx

from app.agent.sources.base import USER_AGENT
from app.agent.state import AgentState, Candidate, ReferenceCategory, SavedReference

# 프로젝트 루트(back-end 의 상위)의 result 폴더. RESULT_DIR 환경변수로 바꿀 수 있다.
RESULT_DIR = Path(os.getenv("RESULT_DIR", Path(__file__).resolve().parents[3] / "result"))
FOLDER_PREFIX = "artBrief_"

MAX_IMAGE_BYTES = 20 * 1024 * 1024
DOWNLOAD_TIMEOUT = httpx.Timeout(30.0)
RETRY_STATUS = {429, 503}  # 잠시 후 다시 시도하면 되는 응답 (요청 제한 등)
MAX_ATTEMPTS = 3
RETRY_DELAY = 1.5  # 초. 시도할수록 늘어난다
EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}

NOT_SAVED_UNCLEAR = "라이선스를 확인하지 못해 파일로 저장하지 않고 링크만 기록했어요."
NOT_SAVED_RESTRICTED = "상업 이용이 제한된 이미지라 파일로 저장하지 않고 링크만 기록했어요."
DOWNLOAD_FAILED = "이미지를 내려받지 못했어요. 링크만 기록했어요."


def create_output_dir(base: Path | None = None) -> Path:
    """result/artBrief_001, 002, ... 중 아직 없는 다음 번호의 폴더를 만든다."""
    base = base or RESULT_DIR
    base.mkdir(parents=True, exist_ok=True)
    numbers = [int(m.group(1)) for p in base.iterdir() if (m := re.fullmatch(rf"{FOLDER_PREFIX}(\d+)", p.name))]
    number = max(numbers, default=0) + 1
    while True:
        path = base / f"{FOLDER_PREFIX}{number:03d}"
        try:
            path.mkdir()  # exist_ok=False: 동시에 두 요청이 와도 같은 폴더를 쓰지 않는다
            return path
        except FileExistsError:
            number += 1


def slugify(text: str, fallback: str, max_len: int = 40) -> str:
    """폴더·파일 이름으로 쓸 수 있게 다듬는다. 한글은 그대로 두고 경로를 깨는 문자만 없앤다."""
    cleaned = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "", text)
    cleaned = re.sub(r"\s+", "_", cleaned.strip()).strip("._")
    return cleaned[:max_len].rstrip("._") or fallback


def storage_decision(candidate: Candidate, save_unverified: bool) -> tuple[bool, str]:
    """이 이미지를 파일로 저장해도 되는지 (저장 여부, 저장하지 않는 이유).

    라이선스가 확인된 이미지만 기본으로 저장한다 (Need.md 10장). 확인이 안 된 이미지는 사용자가 명시적으로
    허용했을 때만 저장하고, 상업 이용이 제한된 이미지는 허용해도 저장하지 않는다.
    """
    if candidate.license == "confirmed":
        return True, ""
    if candidate.license == "unclear" and save_unverified:
        return True, ""
    return False, NOT_SAVED_RESTRICTED if candidate.license == "restricted" else NOT_SAVED_UNCLEAR


async def download_image(http: httpx.AsyncClient, candidate: Candidate) -> tuple[bytes, str] | None:
    """원본 이미지를 내려받는다. 원본이 안 되면 썸네일로 대신한다. 실패하면 None.

    요청 제한(429) 등은 잠시 기다렸다가 다시 시도한다.
    """
    for url in dict.fromkeys([candidate.image_url, candidate.thumbnail_url]):
        if not url:
            continue
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                res = await http.get(url)
            except httpx.HTTPError:
                break
            if res.status_code in RETRY_STATUS and attempt < MAX_ATTEMPTS:
                await asyncio.sleep(RETRY_DELAY * attempt)
                continue
            content_type = res.headers.get("content-type", "").split(";")[0].strip().lower()
            if res.status_code == 200 and content_type in EXTENSIONS and len(res.content) <= MAX_IMAGE_BYTES:
                return res.content, content_type
            break
    return None


def category_folders(state: AgentState) -> dict[str, str]:
    """선택한 이미지가 있는 카테고리마다 '01_겨울_외피' 같은 폴더 이름을 정한다. (카테고리 이름 -> 폴더 이름)"""
    chosen = set(state["selected_ids"])
    used = [c for c in state["final_categories"] if any(x.id in chosen and x.topic == c.name for x in state["candidates"])]
    return {c.name: f"{i:02d}_{slugify(c.name, 'category')}" for i, c in enumerate(used, start=1)}


async def save_selected(state: AgentState, output_dir: Path, progress=lambda done, total: None) -> list[SavedReference]:
    """선택한 이미지를 카테고리 폴더에 저장하고, 저장하지 않은 이미지는 이유와 함께 기록한다."""
    chosen = set(state["selected_ids"])
    folders = category_folders(state)
    selected = [c for cat in state["final_categories"] for c in state["candidates"] if c.id in chosen and c.topic == cat.name]
    for folder in folders.values():
        (output_dir / folder).mkdir(exist_ok=True)

    gate = asyncio.Semaphore(4)  # 한 사이트에 요청이 몰리지 않게 한다
    finished = 0

    async def save_one(number: int, candidate: Candidate, http: httpx.AsyncClient) -> SavedReference:
        nonlocal finished
        allowed, reason = storage_decision(candidate, state.get("save_unverified", False))
        if not allowed:
            result = SavedReference(candidate=candidate, status="link_only", note=reason)
        else:
            async with gate:
                downloaded = await download_image(http, candidate)
            if downloaded is None:
                result = SavedReference(candidate=candidate, status="failed", note=DOWNLOAD_FAILED)
            else:
                content, content_type = downloaded
                name = f"{number:02d}_{slugify(candidate.title, f'image_{number}')}{EXTENSIONS[content_type]}"
                relative = f"{folders[candidate.topic]}/{name}"
                (output_dir / relative).write_bytes(content)
                result = SavedReference(candidate=candidate, file=relative, status="saved")
        finished += 1
        progress(finished, len(selected))
        return result

    per_folder: dict[str, int] = {}
    numbered = []
    for c in selected:  # 폴더 안에서 1번부터 번호를 매긴다
        per_folder[c.topic] = per_folder.get(c.topic, 0) + 1
        numbered.append((per_folder[c.topic], c))

    # Wikimedia 등은 User-Agent 가 없으면 403 으로 막는다
    async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as http:
        return list(await asyncio.gather(*[save_one(n, c, http) for n, c in numbered]))


def write_references_json(state: AgentState, output_dir: Path, saved: list[SavedReference]) -> Path:
    """이미지별 출처·라이선스·저장 결과를 references.json 으로 남긴다."""
    folders = category_folders(state)
    by_category = {}
    for ref in saved:
        by_category.setdefault(ref.candidate.topic, []).append(ref)

    def category_entry(cat: ReferenceCategory) -> dict:
        return {
            "name": cat.name,
            "folder": folders[cat.name],
            "queries": cat.queries,
            "applied_rules": cat.applied_rules,
            "images": [
                {
                    "id": r.candidate.id,
                    "title": r.candidate.title,
                    "file": r.file,
                    "status": r.status,
                    "note": r.note,
                    "image_url": r.candidate.image_url,
                    "source_url": r.candidate.source_url,
                    "source_name": r.candidate.source_name,
                    "creator": r.candidate.creator,
                    "license": r.candidate.license,
                    "license_detail": r.candidate.license_detail,
                    "found_by": r.candidate.reason.removeprefix("검색어: "),
                    "review_score": r.candidate.score,
                    "review": r.candidate.review,
                }
                for r in by_category[cat.name]
            ],
        }

    data = {
        "folder": output_dir.name,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "goal": state["analysis"].goal,
        "asset_type": state.get("asset_type"),
        "exclude_terms": state["reference_plan"].exclude_terms,
        "categories": [category_entry(c) for c in state["final_categories"] if c.name in folders],
    }
    path = output_dir / "references.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
