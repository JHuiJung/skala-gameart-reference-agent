"""Tavily 웹 이미지 검색. 웹 전체에서 찾기 때문에 범위가 넓지만 라이선스 정보를 주지 않는다.

API 키가 필요하다 (.env 의 TAVILY_API_KEY). 키가 없으면 이 출처는 건너뛴다.
검색 1회당 Tavily 크레딧이 소모된다.
"""
import hashlib
import logging
import os
from urllib.parse import urlparse

import httpx

from app.agent.state import Candidate

API_URL = "https://api.tavily.com/search"

# 유료 스톡 이미지 사이트. 워터마크가 있고 사용하려면 구매해야 하므로 '제한됨'으로 표시한다
STOCK_DOMAINS = (
    "dreamstime.com", "shutterstock.com", "istockphoto.com", "gettyimages.com", "alamy.com",
    "depositphotos.com", "123rf.com", "adobestock.com", "stock.adobe.com", "bigstockphoto.com",
)

logger = logging.getLogger(__name__)


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return host


def _is_stock(domain: str) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in STOCK_DOMAINS)


class TavilySource:
    name = "웹 검색 (Tavily)"
    _warned_missing_key = False

    async def search(self, client: httpx.AsyncClient, query: str, limit: int) -> list[Candidate]:
        key = os.getenv("TAVILY_API_KEY")
        if not key:
            if not TavilySource._warned_missing_key:  # 매 검색마다 경고하지 않도록 한 번만
                logger.warning("TAVILY_API_KEY 가 없어 웹 검색(Tavily)을 건너뜁니다.")
                TavilySource._warned_missing_key = True
            return []

        res = await client.post(
            API_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "query": query, "search_depth": "basic", "max_results": 3,
                "include_images": True, "include_image_descriptions": True,
            },
        )
        res.raise_for_status()

        candidates = []
        for item in res.json().get("images", [])[:limit]:
            # include_image_descriptions 를 켜면 객체, 아니면 URL 문자열로 온다
            url = item if isinstance(item, str) else item.get("url")
            if not url:
                continue
            info = {} if isinstance(item, str) else item
            description = info.get("description") or ""
            domain = _domain(url)
            stock = _is_stock(domain)
            candidates.append(Candidate(
                id=hashlib.sha1(url.encode()).hexdigest()[:12],
                image_url=url,
                thumbnail_url=url,
                source_url=url,  # Tavily 는 이미지가 있던 페이지 주소를 주지 않는다
                source_name=f"웹 검색 ({domain})",
                license="restricted" if stock else "unclear",
                license_detail="유료 스톡 이미지 (워터마크 가능)" if stock else "라이선스 정보 없음",
                title=info.get("title") or description[:80],
                tags=[description] if description else [],  # 제외어 필터가 설명도 볼 수 있게 한다
                reason=f"검색어: {query}",
            ))
        return candidates
