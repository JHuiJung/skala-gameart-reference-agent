import struct
import sys
import zlib
from pathlib import Path

import pytest

from app.agent import brief, intake, nodes, references, review, storage
from app.agent.state import (
    AssetClassification,
    BriefDraft,
    BriefPlan,
    BriefSection,
    BriefSectionBody,
    Candidate,
    GroundedCategories,
    Guideline,
    GuidelineRouting,
    ImageReview,
    ImageUsage,
    ImageVerdict,
    InputAnalysis,
    ReferencePlan,
)
from tests.fakes import FakeClient
from tests.graph_fakes import CATEGORY

# scripts/ 는 패키지가 아니므로 테스트에서 import 할 수 있게 경로를 추가한다
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


@pytest.fixture
def png_bytes() -> bytes:
    """테스트용 아주 작은 단색 PNG."""
    w = h = 8
    raw = b"".join(b"\x00" + bytes((80, 90, 80)) * w for _ in range(h))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = struct.pack(">I", len(data)) + kind + data
        return body + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


@pytest.fixture
def result_dir(tmp_path, monkeypatch):
    """결과 폴더를 임시 폴더로 바꿔서 테스트가 실제 result/ 를 건드리지 않게 한다."""
    path = tmp_path / "result"
    monkeypatch.setattr(storage, "RESULT_DIR", path)
    return path


@pytest.fixture
def fake_llm(monkeypatch, result_dir):
    """OpenAI, 벡터 DB 검색, 이미지 검색 출처, 이미지 내려받기를 모두 대역으로 바꿔 그래프 전체를 돌릴 수 있게 한다."""

    def install(classification, details):
        client = FakeClient({
            AssetClassification: AssetClassification(asset_type=classification),
            type(details): details,
            InputAnalysis: InputAnalysis(subject="테스트 대상"),
            GuidelineRouting: GuidelineRouting(categories=["monster"]),
            ReferencePlan: ReferencePlan(categories=[CATEGORY], exclude_terms=["cartoon"]),
            GroundedCategories: GroundedCategories(
                categories=[CATEGORY.model_copy(update={"applied_rules": ["중세 후기 기준"]})], exclude_terms=["modern"]
            ),
            ImageReview: ImageReview(verdicts=[ImageVerdict(index=1, score=9, reason="눈 덮인 들판이 분명함")]),
            BriefPlan: BriefPlan(sections=[BriefSection(heading="작업 목적 및 디자인 목표", outline="목표를 정리한다")]),
            BriefDraft: BriefDraft(
                sections=[BriefSectionBody(heading="작업 목적 및 디자인 목표", body="눈 덮인 들판 배경을 만든다.")],
                image_usage=[ImageUsage(id="snowy field", usage="설원의 질감 참고")],
            ),
        })
        for module in (intake, nodes, references, review, brief):
            monkeypatch.setattr(module, "get_client", lambda: client)

        async def fake_search(query, categories):
            return [Guideline(text="t", source_type="company_rules", category="color", file="f.md", section="s")]

        monkeypatch.setattr(nodes, "search_guidelines", fake_search)

        async def fake_scoped(query, source_type, categories, n_results=3):
            return []

        monkeypatch.setattr(references, "search_scoped", fake_scoped)
        monkeypatch.setattr(brief, "search_scoped", fake_scoped)  # 회사 규정 검색도 외부 호출 없이

        class FakeSource:
            name = "Fake"

            async def search(self, http, query, limit):
                return [Candidate(id=query, image_url=f"https://img/{query}", source_url="https://s", title="Snowy Field", license="confirmed", creator="kim", license_detail="CC BY 2.0")]

        monkeypatch.setattr(references, "DEFAULT_SOURCES", [FakeSource()])

        async def fake_download(http, gate, candidate):
            return "data:image/png;base64,AAAA"  # 검토용 이미지 내려받기 대역

        monkeypatch.setattr(review, "_to_data_url", fake_download)

        async def fake_save_download(http, candidate):
            return b"IMG", "image/png"  # 저장용 이미지 내려받기 대역

        monkeypatch.setattr(storage, "download_image", fake_save_download)
        return client

    return install
