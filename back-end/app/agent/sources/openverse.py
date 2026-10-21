"""Openverse(CC 라이선스 이미지 검색). API 키 없이 사용 가능 (비로그인은 호출 한도가 낮다)."""
import hashlib

import httpx

from app.agent.sources.base import classify_license
from app.agent.state import Candidate

API_URL = "https://api.openverse.org/v1/images/"


class OpenverseSource:
    name = "Openverse"

    async def search(self, client: httpx.AsyncClient, query: str, limit: int) -> list[Candidate]:
        res = await client.get(
            API_URL,
            params={"q": query, "page_size": limit, "license_type": "commercial", "mature": "false"},
        )
        res.raise_for_status()

        candidates = []
        for r in res.json().get("results", []):
            license_name = f"{r['license']} {r.get('license_version') or ''}".strip()
            candidates.append(Candidate(
                id=hashlib.sha1(r["url"].encode()).hexdigest()[:12],
                image_url=r["url"],
                thumbnail_url=r.get("thumbnail") or r["url"],
                source_url=r.get("foreign_landing_url") or r["url"],
                source_name=f"Openverse ({r.get('source') or r.get('provider') or ''})".replace(" ()", ""),
                license=classify_license(r["license"]),
                license_detail=f"CC {license_name.upper()}" if r["license"] not in {"cc0", "pdm"} else license_name.upper(),
                creator=r.get("creator") or "",
                title=r.get("title") or "",
                tags=[t["name"] for t in r.get("tags", [])][:8],
                reason=f"검색어: {query}",
            ))
        return candidates
