"""이미지 검색 출처(Openverse, Wikimedia 등)가 따르는 공통 규칙."""
import re
from typing import Protocol

import httpx

from app.agent.state import Candidate

# Wikimedia 등 일부 출처는 User-Agent 가 없으면 요청을 막는다
USER_AGENT = "ArtBriefAI/0.1 (game art reference research tool)"
TIMEOUT = httpx.Timeout(25.0)  # Openverse 는 키 없이 쓰면 응답이 7~13초 걸린다


class ImageSource(Protocol):
    """출처 어댑터. 새 출처는 이 규칙만 맞추면 검색 노드에 바로 추가할 수 있다."""

    name: str

    async def search(self, client: httpx.AsyncClient, query: str, limit: int) -> list[Candidate]: ...


def classify_license(name: str) -> str:
    """라이선스 이름을 confirmed / restricted / unclear 로 분류한다.

    confirmed : 상업 이용이 허용되는 라이선스 (CC0, 퍼블릭 도메인, CC BY, CC BY-SA)
    restricted: 상업 이용이 제한됨 (NC 계열, fair use)
    unclear   : 그 외, 알 수 없음 (ND 포함 - 사람이 검토해야 함)
    """
    n = re.sub(r"[\s_]+", "-", name.strip().lower())
    if not n:
        return "unclear"
    if "nc" in n.split("-") or "fair-use" in n:
        return "restricted"
    if "nd" in n.split("-"):
        return "unclear"
    if n in {"cc0", "pdm", "public-domain"} or n.startswith(("cc-by", "cc0", "public-domain", "by")):
        return "confirmed"
    return "unclear"
