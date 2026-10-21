import asyncio
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agent import brief, runner
from app.agent.state import (
    BriefDraft,
    BriefPlan,
    BriefSection,
    BriefSectionBody,
    Candidate,
    ImageUsage,
    InputAnalysis,
    ReferenceCategory,
    ReferencePlan,
    SavedReference,
)
from app.schemas import AnswerRequest
from tests.fakes import FakeClient
from tests.graph_fakes import ans, extracted, to_confirm_brief, to_select_images


# ── 이미지 선택 ──────────────────────────────────────────────────────────────

def test_image_selection_ignores_unknown_ids_and_asks_again_if_none_valid(fake_llm):
    fake_llm("prop", extracted(scale="a", function="b", interaction="c"))

    async def flow():
        selecting = await to_select_images()
        again = await runner.resume(ans(selecting.thread_id, selected_ids=["존재하지 않는 이미지"]))
        picked = await runner.resume(ans(selecting.thread_id, selected_ids=["존재하지 않는 이미지", "snowy field"]))
        return selecting, again, picked

    selecting, again, picked = asyncio.run(flow())

    assert again.kind == "select_images"  # 유효한 선택이 없으면 같은 화면을 다시 보여준다
    assert picked.kind == "confirm_brief"
    assert picked.selected_ids == ["snowy field"]  # 유효한 것만 남는다


def test_image_selection_response_keeps_results_visible(fake_llm):
    fake_llm("prop", extracted(scale="a", function="b", interaction="c"))
    selecting = asyncio.run(to_select_images())
    assert selecting.candidates and selecting.categories and selecting.analysis  # 선택 화면에서 이미지를 보여줄 수 있다


# ── 작성 계획 ────────────────────────────────────────────────────────────────

def test_plan_always_contains_required_sections_and_hides_auto_sections():
    llm_sections = [
        BriefSection(heading="작업 목적 및 디자인 목표", outline="목표"),
        BriefSection(heading=brief.SECTION_IMAGES, outline="LLM 이 만들어 버린 자동 섹션"),  # 제거되어야 함
        BriefSection(heading="표정·포즈", outline="추가 섹션"),
        BriefSection(heading="표정·포즈", outline="중복"),  # 제목이 같으면 앞의 것만
    ]
    result = brief.ensure_required_sections(llm_sections)

    headings = [s.heading for s in result]
    assert headings[:2] == ["작업 목적 및 디자인 목표", "표정·포즈"]  # LLM 이 정한 순서 유지
    assert set(brief.REQUIRED_HEADINGS) <= set(headings)  # 빠진 필수 섹션은 채워 넣는다
    assert brief.SECTION_IMAGES not in headings and headings.count("표정·포즈") == 1
    assert next(s for s in result if s.heading == "검토 체크리스트").outline == brief.MISSING_OUTLINE


def test_plan_step_uses_company_rules_and_selected_images(fake_llm, monkeypatch):
    client = fake_llm("prop", extracted(scale="a", function="b", interaction="c"))
    queried = []

    async def fake_scoped(query, source_type, categories, n_results=3):
        queried.append((source_type, tuple(categories)))
        from app.agent.state import Guideline
        return [Guideline(text=f"{categories[0]} 규정: 최대 5색", source_type="company_rules", category=categories[0],
                          file=f"{categories[0]}.md", section="1")] if source_type == "company_rules" else []

    monkeypatch.setattr(brief, "search_scoped", fake_scoped)
    confirm = asyncio.run(to_confirm_brief())

    # 색상·모델링·텍스처·네이밍 규정을 모두 찾는다
    assert sorted(c[1][0] for c in queried if c[0] == "company_rules") == ["color", "modeling", "naming", "texture"]
    plan_call = next(c for c in client.calls if c["messages"][0]["content"] == brief.PLAN_PROMPT)
    prompt = plan_call["messages"][1]["content"]
    assert "color 규정: 최대 5색" in prompt  # 회사 규정이 계획 입력에 들어간다
    assert "[snowy field]" in prompt and "눈 덮인 들판이 분명함" in prompt  # 선택한 이미지와 검토 의견
    assert confirm.kind == "confirm_brief" and confirm.auto_sections == brief.AUTO_SECTIONS
    assert {s.heading for s in confirm.brief_sections} >= set(brief.REQUIRED_HEADINGS)


# ── 승인 → 저장 → 지시서 ─────────────────────────────────────────────────────

def edited_sections(confirm):
    sections = [s.model_copy() for s in confirm.brief_sections]
    sections[0] = BriefSection(heading=sections[0].heading, outline="사용자가 고친 계획: 설원 질감을 강조한다")
    return sections[:3] + [BriefSection(heading="사용자가 추가한 섹션", outline="직접 추가")]


def test_approved_plan_creates_numbered_folder_with_images_references_and_brief(fake_llm, result_dir):
    client = fake_llm("prop", extracted(scale="a", function="b", interaction="c"))

    async def flow():
        confirm = await to_confirm_brief()
        return confirm, await runner.resume(
            ans(confirm.thread_id, brief_sections=edited_sections(confirm), brief_notes="더 차갑게 써주세요")
        )

    confirm, done = asyncio.run(flow())

    folder = result_dir / "artBrief_001"
    assert (folder / "01_배경" / "01_Snowy_Field.png").read_bytes() == b"IMG"
    assert json.loads((folder / "references.json").read_text(encoding="utf-8"))["categories"][0]["images"][0]["status"] == "saved"

    text = (folder / "지시서.md").read_text(encoding="utf-8")
    assert text.startswith("# 작업 지시서: 테스트 대상")
    assert "## 작업 목적 및 디자인 목표\n\n눈 덮인 들판 배경을 만든다." in text  # LLM 본문
    assert "## 사용자가 추가한 섹션" in text and "(이 섹션은 작성되지 않았습니다" in text  # LLM 이 안 쓴 섹션은 표시
    assert "![Snowy Field](01_%EB%B0%B0%EA%B2%BD/01_Snowy_Field.png)" in text  # 한글 경로는 인코딩된 상대 링크
    assert "활용 목적: 설원의 질감 참고" in text and "검토 의견: 눈 덮인 들판이 분명함" in text
    assert "| 01_배경/01_Snowy_Field.png | - | kim | CC BY 2.0 | 저장됨 |" in text
    assert "⚠️" not in text  # 라이선스가 모두 확인됨

    # 승인된(사용자가 수정한) 계획과 추가 요청이 본문 작성에 전달된다
    write_call = next(c for c in client.calls if c["messages"][0]["content"] == brief.WRITE_PROMPT)
    prompt = write_call["messages"][1]["content"]
    assert "사용자가 고친 계획: 설원 질감을 강조한다" in prompt and "사용자가 추가한 섹션: 직접 추가" in prompt
    assert "더 차갑게 써주세요" in prompt

    assert done.status == "done" and done.output.folder == "result/artBrief_001" and done.output.brief_file == "지시서.md"
    assert (done.output.saved, done.output.link_only, done.output.failed) == (1, 0, 0)
    assert done.output.brief_markdown == text


def test_next_run_uses_next_folder_number(fake_llm, result_dir):
    fake_llm("prop", extracted(scale="a", function="b", interaction="c"))

    async def one_run():
        confirm = await to_confirm_brief()
        return await runner.resume(ans(confirm.thread_id, brief_sections=confirm.brief_sections))

    first = asyncio.run(one_run())
    second = asyncio.run(one_run())
    assert (first.output.folder, second.output.folder) == ("result/artBrief_001", "result/artBrief_002")


def test_confirm_brief_rejects_other_kinds_of_answers(fake_llm):
    fake_llm("prop", extracted(scale="a", function="b", interaction="c"))

    async def flow():
        confirm = await to_confirm_brief()
        await runner.resume(ans(confirm.thread_id, categories=["배경"]))

    with pytest.raises(runner.WrongAnswerKind):
        asyncio.run(flow())


# ── 저장 정책과 지시서 조립 (그래프 없이) ────────────────────────────────────

def candidate(id, license="confirmed", **kw):
    return Candidate(id=id, image_url=f"https://img/{id}.jpg", source_url=f"https://src/{id}", topic="의상", license=license,
                     title=kw.pop("title", f"Image {id}"), **kw)


def brief_state(candidates, selected, tmp_path, save_unverified=False):
    cat = ReferenceCategory(name="의상", queries=["cloak"])
    return {
        "text": "t", "asset_type": "character", "details": {},
        "analysis": InputAnalysis(goal="차가운 지역 버전", subject="버섯 몬스터"),
        "reference_plan": ReferencePlan(categories=[cat]), "final_categories": [cat], "candidates": candidates,
        "selected_ids": selected, "save_unverified": save_unverified, "output_dir": str(tmp_path),
        "brief_plan": BriefPlan(sections=[BriefSection(heading="목표", outline="o")]),
    }


def test_unverified_images_are_linked_not_saved_in_markdown(tmp_path, monkeypatch):
    from app.agent import storage

    async def fake_download(http, c):
        return b"x", "image/png"

    monkeypatch.setattr(storage, "download_image", fake_download)
    cands = [candidate("ok"), candidate("unsure", license="unclear", title="Pipe | Title", source_name="웹 검색 (etsy.com)"),
             candidate("stock", license="restricted")]
    st = brief_state(cands, ["ok", "unsure", "stock"], tmp_path)
    saved = asyncio.run(storage.save_selected(st, tmp_path))
    usage = {r.candidate.id: r.model_copy(update={"usage": f"{r.candidate.id} 용도"}) for r in saved}
    md = brief.build_markdown(st, {"목표": "본문"}, list(usage.values()))

    assert "![Image ok](01_%EC%9D%98%EC%83%81/01_Image_ok.png)" in md  # 확인된 이미지는 파일로 삽입
    assert "[Pipe | Title](https://src/unsure)" in md and "[Image stock](https://src/stock)" in md  # 나머지는 원본 링크
    assert "(라이선스를 확인하지 못해 파일로 저장하지 않고 링크만 기록했어요.)" in md
    assert "⚠️ 라이선스가 확인되지 않았거나 제한된 이미지가 2장" in md
    assert "| https://src/unsure | 웹 검색 (etsy.com) | - | 확인 필요 | 링크만 기록 |" in md
    assert not any("Pipe" in p.name for p in tmp_path.rglob("*"))  # 링크만 기록한 이미지는 파일이 없다


def test_markdown_follows_the_approved_plan_order(tmp_path):
    st = brief_state([candidate("ok")], ["ok"], tmp_path)
    st["brief_plan"] = BriefPlan(sections=[BriefSection(heading="둘째", outline=""), BriefSection(heading="첫째", outline="")])
    saved = [SavedReference(candidate=candidate("ok"), file="01_의상/01_a.png", status="saved", usage="u")]

    md = brief.build_markdown(st, {"첫째": "A", "둘째": "B"}, saved)

    assert md.index("## 둘째") < md.index("## 첫째") < md.index(f"## {brief.SECTION_IMAGES}") < md.index(f"## {brief.SECTION_LICENSE}")


# ── 요청 검증 ────────────────────────────────────────────────────────────────

def sections(*headings):
    return [BriefSection(heading=h, outline="내용") for h in headings]


def test_answer_request_cleans_brief_sections():
    req = AnswerRequest(thread_id="t", brief_sections=[BriefSection(heading=" 목표 ", outline=" 내용 ")])
    assert req.brief_sections[0].heading == "목표" and req.brief_sections[0].outline == "내용"


@pytest.mark.parametrize("bad", [
    [],                                   # 비어 있음
    sections("a", "a"),                   # 제목 중복
    sections("   "),                      # 빈 제목
    sections(*[f"s{i}" for i in range(16)]),  # 너무 많음
    sections("가" * 61),                  # 제목이 너무 김
    [BriefSection(heading="a", outline="x" * 1501)],
])
def test_answer_request_rejects_bad_brief_sections(bad):
    with pytest.raises(ValidationError):
        AnswerRequest(thread_id="t", brief_sections=bad)


def test_answer_request_rejects_empty_image_selection():
    with pytest.raises(ValidationError):
        AnswerRequest(thread_id="t", selected_ids=[])
