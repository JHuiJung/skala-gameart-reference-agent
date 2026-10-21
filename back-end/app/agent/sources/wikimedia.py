"""Wikimedia Commons 이미지 검색. API 키 없이 사용 가능."""
import hashlib
import re

import httpx

from app.agent.sources.base import classify_license
from app.agent.state import Candidate

API_URL = "https://commons.wikimedia.org/w/api.php"
IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp"}  # svg, tiff 등 레퍼런스로 쓰기 어려운 형식은 제외


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip()


class WikimediaSource:
    name = "Wikimedia Commons"

    async def search(self, client: httpx.AsyncClient, query: str, limit: int) -> list[Candidate]:
        res = await client.get(API_URL, params={
            "action": "query", "format": "json", "generator": "search",
            "gsrsearch": query, "gsrnamespace": 6, "gsrlimit": limit,  # namespace 6 = 파일
            "prop": "imageinfo", "iiprop": "url|mime|extmetadata", "iiurlwidth": 480,
            "iiextmetadatafilter": "LicenseShortName|Artist",
        })
        res.raise_for_status()

        candidates = []
        pages = res.json().get("query", {}).get("pages", {}).values()
        for page in sorted(pages, key=lambda p: p.get("index", 0)):  # 검색 순위 유지
            info = (page.get("imageinfo") or [{}])[0]
            if info.get("mime") not in IMAGE_MIMES:
                continue
            meta = info.get("extmetadata", {})
            license_name = meta.get("LicenseShortName", {}).get("value", "")
            candidates.append(Candidate(
                id=hashlib.sha1(info["url"].encode()).hexdigest()[:12],
                image_url=info["url"],
                thumbnail_url=info.get("thumburl") or info["url"],
                source_url=info.get("descriptionurl") or info["url"],
                source_name=self.name,
                license=classify_license(license_name),
                license_detail=license_name,
                creator=_strip_html(meta.get("Artist", {}).get("value", "")),
                title=page["title"].removeprefix("File:"),
                reason=f"검색어: {query}",
            ))
        return candidates
