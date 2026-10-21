"""지시서 단계: 이미지 선택 → 작성 계획 → 사용자 승인 → 이미지 저장 → 지시서.md 작성.

흐름: select_images(사용자 선택) → draft_brief_plan → confirm_brief(사용자 승인·수정) → save_references → write_brief
"""
import asyncio
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from langgraph.types import interrupt

from app.agent.checklist import CHECKLISTS, TYPE_LABELS
from app.agent.llm import WRITER_MODEL, get_client
from app.agent.progress import emit_detail
from app.agent.retriever import search_scoped
from app.agent.state import (
    AgentState,
    BriefDraft,
    BriefPlan,
    BriefSection,
    Candidate,
    Guideline,
    SavedReference,
)
from app.agent.storage import category_folders, create_output_dir, save_selected, write_references_json

# 이 두 섹션은 이미지 저장 결과로 코드가 직접 작성한다. (LLM 이 파일 경로나 라이선스를 지어내지 못하게)
SECTION_IMAGES = "참고 이미지별 설명과 활용 목적"
SECTION_LICENSE = "이미지 출처 및 라이선스 확인 정보"
AUTO_SECTIONS = [SECTION_IMAGES, SECTION_LICENSE]

# Need.md 9장의 지시서 필수 항목. 계획에 빠져 있으면 채워 넣는다.
REQUIRED_HEADINGS = [
    "작업 목적 및 디자인 목표",
    "대상과 세계관·분위기",
    "반드시 반영할 시각적 특징",
    "색상·재질·조명·형태 가이드",
    "피해야 할 요소 및 제외 조건",
    "관련 내부 디자인 규칙",
    "검토 체크리스트",
]
MISSING_OUTLINE = "(계획이 비어 있어요. 이 섹션에 쓸 내용을 적거나, 그대로 두면 입력된 정보로 AI 가 작성해요.)"

RULE_CATEGORIES = ["color", "modeling", "texture", "naming"]  # 지시서에 반영할 회사 규정 카테고리
RULES_PER_CATEGORY = 3

PLAN_PROMPT = f"""너는 게임 아트팀에 전달할 작업 지시서(지시서.md)를 설계하는 아트 디렉터 보조다.
지시서에 **어떤 내용을 쓸지** 섹션별 계획을 세워라. 아직 본문을 쓰지 마라. 사용자가 이 계획을 보고 수정·승인한다.

- 아래 섹션을 이 제목 그대로, 이 순서로 포함해라: {' / '.join(REQUIRED_HEADINGS)}
- 에셋 종류에 필요한 섹션이 더 있으면 추가해도 된다. (예: 캐릭터라면 '표정·포즈')
- '{SECTION_IMAGES}', '{SECTION_LICENSE}' 는 시스템이 자동으로 작성하니 만들지 마라.
- outline 은 그 섹션에 쓸 내용을 2~4줄로 요약해라. 입력(사용자 요청, 확인된 필수 항목, 세계관 가이드, 회사 규정, 선택한 레퍼런스)에
  근거한 내용만 적고, 회사 규정은 수치를 인용해라. 정보가 없는 항목은 '미정이라 AI 제안으로 채움'이라고 적어라.
- 사용자가 한국어를 쓰니 제목과 outline 모두 한국어로 써라."""

WRITE_PROMPT = f"""너는 게임 아트팀에 전달할 작업 지시서를 쓰는 아트 디렉터 보조다.
사용자가 승인한 작성 계획의 각 섹션을 순서대로, **제목을 바꾸지 말고** 마크다운 본문으로 작성해라.

- 본문은 그 섹션의 outline 과 사용자의 추가 요청을 따르고, 입력에 있는 내용에 근거해라. 입력에 없는 사실을 지어내지 마라.
- 회사 규정은 수치와 조건('최대', '권장', '이상' 등)을 원문 그대로 인용해라. 의역하거나 조건을 바꾸지 마라.
  (예: '최대 5색, 몬스터는 3색 권장'을 '3색으로 제한'이라고 쓰면 틀린 것이다)
- '카테고리별로 반영한 세계관 규칙'에 대체 지시(예: '코코아는 세계관에 없음 → 허브차로 대체')가 있으면
  사용자 요청 원문보다 우선해 대체한 내용으로 쓰고, 대체했다는 사실을 해당 섹션에 한 줄로 밝혀라.
- 입력에 없는 작업 절차나 일정(베타 테스트, 피드백 반영 등)을 만들어 넣지 마라.
- 제외 조건은 영문 단어의 뜻 그대로 옮겨라. 세계관이 중세 후기라면 '고전적/중세적' 요소를 피하라고 쓰면 안 된다.
  세계관 가이드가 금지한 요소는 '피해야 할 요소'에 반영해라.
- 값이 '미정'인 항목은 세계관과 규정에 맞게 제안하되 문장 끝에 '(AI 제안)'을 붙여라.
- 목록과 표를 적절히 써서 아트팀이 바로 볼 수 있게 간결하게 써라. 본문에 섹션 제목(##)은 쓰지 마라. 시스템이 붙인다.
- 파일 경로나 링크, 라이선스 정보는 쓰지 마라. '{SECTION_IMAGES}', '{SECTION_LICENSE}' 섹션은 시스템이 작성한다.
- image_usage: 선택된 이미지마다 id 를 그대로 쓰고, 이 작업에서 무엇을 참고하려고 고른 이미지인지(카테고리, 검토 의견 기반) 한 문장으로 써라."""


# ── 1. 이미지 선택 ───────────────────────────────────────────────────────────

def select_images(state: AgentState) -> dict:
    """[5-1단계] 검토를 통과한 이미지 중 사용자가 클릭해서 고른 것을 받는다. (사용자가 고를 때까지 멈춘다)"""
    valid = {c.id for c in state["candidates"]}
    while True:  # 존재하지 않는 이미지만 오면 다시 묻는다
        answer = interrupt({"kind": "select_images"})
        chosen = [i for i in dict.fromkeys(answer["selected_ids"]) if i in valid]
        if chosen:
            return {
                "selected_ids": chosen,
                "save_unverified": bool(answer.get("save_unverified")),
                "current_step": "이미지 선택",
            }


# ── 2. 작성 계획 ─────────────────────────────────────────────────────────────

def _selected(state: AgentState) -> list[Candidate]:
    chosen = set(state["selected_ids"])
    return [c for c in state["candidates"] if c.id in chosen]


def _format_guides(guides: list[Guideline]) -> str:
    return "\n\n".join(f"[{g.file} > {g.section}]\n{g.text}" for g in guides) or "(없음)"


def brief_context(state: AgentState, rules: list[Guideline]) -> str:
    """계획과 본문 작성에 쓸 입력 정보를 하나의 텍스트로 모은다."""
    a = state["analysis"]
    asset_type = state.get("asset_type")
    details = "\n".join(
        f"- {item.label}: {state['details'].get(item.key, '미정')}" for item in CHECKLISTS.get(asset_type, [])
    )
    world = [g for g in state.get("guidelines", []) if g.source_type == "confirmed_plans"]
    category_rules = "\n".join(
        f"- {c.name}: {'; '.join(c.applied_rules)}" for c in state["final_categories"] if c.applied_rules
    )
    images = "\n".join(
        f"- [{c.id}] 카테고리 '{c.topic}' | {c.title} | 검토 의견: {c.review or '없음'} | 라이선스: {c.license_detail or c.license}"
        for c in _selected(state)
    )
    return (
        f"## 사용자 요청 원문\n{state.get('text', '')}\n\n"
        f"## 최종 목표\n{a.goal}\n\n"
        f"## 에셋 종류\n{TYPE_LABELS.get(asset_type, '미정')}\n{details}\n\n"
        f"## 분석된 요구사항\n{a.model_dump_json(indent=2)}\n\n"
        f"## 세계관·기획 가이드\n{_format_guides(world)}\n\n"
        f"## 카테고리별로 반영한 세계관 규칙\n{category_rules or '(없음)'}\n\n"
        f"## 회사 규정\n{_format_guides(rules)}\n\n"
        f"## 제외 조건\n{', '.join(state['reference_plan'].exclude_terms) or '(없음)'}\n\n"
        f"## 선택한 레퍼런스 이미지\n{images}"
    )


async def _fetch_rules(state: AgentState) -> list[Guideline]:
    """지시서에 반영할 회사 규정(색상, 모델링, 텍스처, 네이밍)을 찾는다."""
    query = f"{state['analysis'].goal} {TYPE_LABELS.get(state.get('asset_type'), '')}".strip()
    found = await asyncio.gather(*[search_scoped(query, "company_rules", [c], RULES_PER_CATEGORY) for c in RULE_CATEGORIES])
    unique = {(g.file, g.section): g for guides in found for g in guides}
    return list(unique.values())


def ensure_required_sections(sections: list[BriefSection]) -> list[BriefSection]:
    """자동 작성 섹션은 빼고, 필수 섹션이 빠져 있으면 뒤에 채워 넣는다. (제목이 중복되면 앞의 것만 쓴다)"""
    seen: set[str] = set()
    cleaned = []
    for s in sections:
        if s.heading in AUTO_SECTIONS or s.heading in seen:
            continue
        seen.add(s.heading)
        cleaned.append(s)
    cleaned += [BriefSection(heading=h, outline=MISSING_OUTLINE) for h in REQUIRED_HEADINGS if h not in seen]
    return cleaned


async def draft_brief_plan(state: AgentState) -> dict:
    """[5-2단계] 지시서에 무엇을 쓸지 섹션별 계획을 세운다. (회사 규정을 찾아 반영)"""
    rules = await _fetch_rules(state)
    completion = await get_client().chat.completions.parse(
        model=WRITER_MODEL,
        messages=[
            {"role": "system", "content": PLAN_PROMPT},
            {"role": "user", "content": brief_context(state, rules)},
        ],
        response_format=BriefPlan,
    )
    plan = BriefPlan(sections=ensure_required_sections(completion.choices[0].message.parsed.sections))
    return {"rule_guides": rules, "brief_plan": plan, "current_step": "지시서 작성 계획 수립"}


def confirm_brief(state: AgentState) -> dict:
    """[5-3단계] 작성 계획을 사용자에게 보여주고 수정·승인을 받는다. (승인할 때까지 멈춘다)"""
    answer = interrupt({
        "kind": "confirm_brief",
        "sections": [s.model_dump() for s in state["brief_plan"].sections],
        "auto_sections": AUTO_SECTIONS,
    })
    plan = BriefPlan(sections=[BriefSection(**s) for s in answer["sections"]])
    return {"brief_plan": plan, "brief_notes": answer.get("notes", ""), "current_step": "지시서 계획 확정"}


# ── 3. 저장과 작성 ───────────────────────────────────────────────────────────

async def save_references(state: AgentState) -> dict:
    """[6-1단계] result/artBrief_NNN/ 을 만들고 선택한 이미지를 카테고리 폴더에 저장한다."""
    output_dir = create_output_dir()
    saved = await save_selected(state, output_dir, progress=lambda done, total: emit_detail(f"이미지 저장 {done}/{total}"))
    write_references_json(state, output_dir, saved)
    return {"output_dir": str(output_dir), "saved_refs": saved, "current_step": "레퍼런스 이미지 저장"}


def _md_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip() or "-"


STATUS_LABEL = {"saved": "저장됨", "link_only": "링크만 기록", "failed": "저장 실패"}


def _images_section(saved: list[SavedReference], folders: dict[str, str]) -> str:
    out = []
    for category, folder in folders.items():
        out.append(f"### {folder}")
        for ref in (r for r in saved if r.candidate.topic == category):
            c = ref.candidate
            title = c.title or "(제목 없음)"
            target = f"![{title}]({quote(ref.file)})" if ref.file else f"[{title}]({c.source_url})"
            note = f" ({ref.note})" if ref.note else ""
            out.append(f"- {target}{note}")
            out.append(f"  - 활용 목적: {ref.usage or '(작성되지 않음)'}")
            if c.review:
                out.append(f"  - 검토 의견: {c.review}")
        out.append("")
    return "\n".join(out).rstrip()


def _license_section(saved: list[SavedReference]) -> str:
    rows = ["| 파일/링크 | 출처 | 저작자 | 라이선스 | 상태 |", "|---|---|---|---|---|"]
    for ref in saved:
        c = ref.candidate
        where = ref.file or c.source_url
        license_text = c.license_detail or {"confirmed": "확인됨", "unclear": "확인 필요", "restricted": "제한됨"}[c.license]
        rows.append(
            f"| {_md_cell(where)} | {_md_cell(c.source_name)} | {_md_cell(c.creator)} | {_md_cell(license_text)} | {STATUS_LABEL[ref.status]} |"
        )
    unverified = sum(r.candidate.license != "confirmed" for r in saved)
    warning = (
        f"> ⚠️ 라이선스가 확인되지 않았거나 제한된 이미지가 {unverified}장 있습니다. 상업적으로 사용하기 전에 반드시 출처를 확인하세요.\n\n"
        if unverified
        else ""
    )
    return warning + "\n".join(rows)


def build_markdown(state: AgentState, bodies: dict[str, str], saved: list[SavedReference]) -> str:
    """승인된 계획 순서대로 LLM 본문을 붙이고, 이미지·라이선스 섹션은 저장 결과로 직접 작성한다."""
    a = state["analysis"]
    folders = category_folders(state)
    header = [
        f"# 작업 지시서: {a.subject}",
        "",
        *([f"> {a.goal}", ""] if a.goal else []),
        f"- 에셋 종류: {TYPE_LABELS.get(state.get('asset_type'), '미정')}",
        f"- 작성일: {datetime.now().strftime('%Y-%m-%d')}",
        f"- 결과 폴더: {Path(state['output_dir']).name}",
        "",
    ]
    parts = ["\n".join(header)]
    for section in state["brief_plan"].sections:
        body = bodies.get(section.heading, "(이 섹션은 작성되지 않았습니다. 다시 시도해주세요.)")
        parts.append(f"## {section.heading}\n\n{body.strip()}")
    parts.append(f"## {SECTION_IMAGES}\n\n{_images_section(saved, folders)}")
    parts.append(f"## {SECTION_LICENSE}\n\n{_license_section(saved)}")
    return "\n\n".join(parts) + "\n"


async def write_brief(state: AgentState) -> dict:
    """[6-2단계] 승인된 계획대로 지시서 본문을 쓰고 지시서.md 로 저장한다."""
    plan_text = "\n".join(f"{i}. {s.heading}: {s.outline}" for i, s in enumerate(state["brief_plan"].sections, start=1))
    notes = state.get("brief_notes", "").strip()
    user_message = (
        f"{brief_context(state, state.get('rule_guides', []))}\n\n"
        f"## 승인된 작성 계획\n{plan_text}\n\n"
        f"## 사용자의 추가 요청\n{notes or '(없음)'}"
    )
    completion = await get_client().chat.completions.parse(
        model=WRITER_MODEL,
        messages=[{"role": "system", "content": WRITE_PROMPT}, {"role": "user", "content": user_message}],
        response_format=BriefDraft,
    )
    draft = completion.choices[0].message.parsed

    usage = {u.id: u.usage for u in draft.image_usage}
    saved = [r.model_copy(update={"usage": usage.get(r.candidate.id, "")}) for r in state["saved_refs"]]
    markdown = build_markdown(state, {s.heading: s.body for s in draft.sections}, saved)

    path = Path(state["output_dir"]) / "지시서.md"
    path.write_text(markdown, encoding="utf-8")
    return {"saved_refs": saved, "brief_path": str(path), "brief_markdown": markdown, "current_step": "지시서 작성"}
