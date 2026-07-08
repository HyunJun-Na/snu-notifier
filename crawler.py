# -*- coding: utf-8 -*-
"""게시판 크롤러.

전략: 정교한 게시판별 파서 대신 '범용 링크 추출 + 새 글 감지'를 사용.
- 페이지의 모든 링크 중 게시글일 가능성이 있는 것(제목 길이, 도메인 조건)을 수집
- 첫 실행 때 전부 baseline으로 저장(알림 없음)
- 이후 실행에서 '처음 보는 링크'만 새 글로 처리
→ 메뉴/네비게이션 링크가 섞여도 항상 존재하므로 새 글로 잡히지 않음.
  게시판 HTML 구조가 조금 바뀌어도 계속 동작하는 견고한 방식.
"""
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (personal notice monitor; contact via repo)"}

# 게시글이 아닐 가능성이 높은 링크 제외 패턴
SKIP_HREF = re.compile(
    r"(login|logout|sitemap|#|javascript:|mailto:|\.pdf$|\.hwp$|\.jpg$|\.png$"
    r"|/category/|/tag/|/page/|paged=|/wp-|facebook|instagram|twitter|youtube)",
    re.I,
)
MIN_TITLE_LEN = 10  # 이보다 짧은 링크 텍스트는 메뉴일 가능성이 높음


def fetch_board(source):
    """소스 하나에서 (title, url) 후보 목록을 반환."""
    resp = requests.get(source["url"], headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    base_host = urlparse(source["url"]).netloc
    posts, seen_here = [], set()
    for a in soup.find_all("a", href=True):
        href = urljoin(source["url"], a["href"])
        title = " ".join(a.get_text(" ", strip=True).split())
        if (
            urlparse(href).netloc != base_host
            or SKIP_HREF.search(href)
            or len(title) < MIN_TITLE_LEN
            or href == source["url"]
        ):
            continue
        if href in seen_here:
            continue
        seen_here.add(href)
        posts.append({"source": source["name"], "title": title, "url": href})
    return posts


def crawl_all(sources, seen_urls):
    """모든 소스를 돌며 새 글만 반환. seen_urls는 in-place 갱신됨."""
    new_posts, errors = [], []
    for src in sources:
        try:
            for post in fetch_board(src):
                if post["url"] not in seen_urls:
                    seen_urls.add(post["url"])
                    new_posts.append(post)
        except Exception as e:  # 한 게시판이 죽어도 나머지는 계속
            errors.append(f"{src['name']}: {e}")
    return new_posts, errors
