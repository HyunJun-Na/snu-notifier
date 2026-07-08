# -*- coding: utf-8 -*-
"""1단계 규칙 필터 + 2단계 Claude 관련도 판정"""
import json
import os
import re

import requests
from bs4 import BeautifulSoup

ANTHROPIC_API = "https://api.anthropic.com/v1/messages"


# ---------- 1단계: 규칙 ----------
def rule_classify(title, keywords):
    t = title.lower()
    for kw in keywords["hard_exclude"]:
        if str(kw).lower() in t:
            return "EXCLUDE"
    for kw in keywords["hard_include"]:
        if str(kw).lower() in t:
            return "INCLUDE"
    return "AMBIGUOUS"


# ---------- 프로필 (URL 실시간 참조) ----------
def build_profile(cfg):
    """base 프로필 + 프로필 페이지(github.io) 본문을 합쳐 반환."""
    profile = str(cfg["profile"]["base"]).strip()
    url = cfg["profile"].get("url")
    if url:
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)
            text = " ".join(text.split())[:2000]
            if len(text) > 50:
                profile += f"\n\n[본인 소개 페이지({url}) 내용]\n{text}"
        except Exception:
            pass  # 페이지 접속 실패 시 base만 사용
    return profile


# ---------- 2단계: Claude 판정 ----------
PROMPT = """다음은 서울대 게시판에 올라온 공지 제목이다. 아래 학생 프로필에 얼마나 관련 있는지 판정하라.

[학생 프로필]
{profile}

[공지] ({source})
{title}

JSON만 출력하라 (설명·마크다운 금지):
{{"score": 0-10 정수, "category": "인턴/채용|장학|교환/유학|봉사|행사|기타", "reason": "한 문장", "deadline": "제목에서 추정되는 마감일 YYYY-MM-DD 또는 null"}}
점수 기준: 8-10 놓치면 안 됨 / 5-7 알아두면 좋음 / 0-4 무관"""


def claude_score(post, profile, cfg):
    """애매한 글 1건을 Claude로 판정. 실패 시 안전하게 score 6(다이제스트행)."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    fallback = {"score": 6, "category": "기타",
                "reason": "판정 실패 - 안전을 위해 다이제스트 포함", "deadline": None}
    if not api_key:
        return fallback
    try:
        resp = requests.post(
            ANTHROPIC_API,
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": cfg["claude"]["model"], "max_tokens": 200,
                  "messages": [{"role": "user", "content": PROMPT.format(
                      profile=profile, source=post["source"], title=post["title"])}]},
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json()["content"][0]["text"]
        m = re.search(r"\{.*\}", text, re.S)
        result = json.loads(m.group()) if m else fallback
        result["score"] = int(result.get("score", 6))
        return result
    except Exception:
        return fallback


def process_posts(posts, cfg, profile):
    """전체 파이프라인: 규칙 → (애매하면) Claude → 라우팅 태그 부착."""
    instant, digest, dropped = [], [], []
    max_llm = int(cfg["claude"]["max_posts_per_run"])
    llm_used = 0

    for post in posts:
        rule = rule_classify(post["title"], cfg["keywords"])
        if rule == "EXCLUDE":
            post["verdict"] = {"score": 0, "reason": "규칙 제외"}
            dropped.append(post)
            continue

        if llm_used < max_llm:
            post["verdict"] = claude_score(post, profile, cfg)
            llm_used += 1
        else:
            post["verdict"] = {"score": 6, "category": "기타",
                               "reason": "판정 상한 초과", "deadline": None}

        score = post["verdict"]["score"]
        if rule == "INCLUDE" and score < cfg["routing"]["digest_min_score"]:
            score = cfg["routing"]["digest_min_score"]  # hard include는 최소 다이제스트 보장
            post["verdict"]["score"] = score

        if score >= cfg["routing"]["instant_min_score"]:
            instant.append(post)
        elif score >= cfg["routing"]["digest_min_score"]:
            digest.append(post)
        else:
            dropped.append(post)
    return instant, digest, dropped
