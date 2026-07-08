# -*- coding: utf-8 -*-
"""텔레그램: 알림 발송 + 채팅 명령으로 키워드 실시간 수정.

명령어 (봇 채팅창에 입력):
  /keywords          현재 include/exclude 키워드 전체 보기
  /add 키워드        hard_include에 추가 (무조건 통과)
  /block 키워드      hard_exclude에 추가 (무조건 제외)
  /remove 키워드     양쪽 목록에서 삭제
  /profile           현재 프로필(참조 URL 포함) 보기
  /status            마지막 실행 요약
  /help              명령어 안내
"""
import os

import requests

import store

API = "https://api.telegram.org/bot{token}/{method}"


def _token():
    return os.environ["TELEGRAM_BOT_TOKEN"]


def _chat_id():
    return os.environ["TELEGRAM_CHAT_ID"]


def send(text):
    """알림 1건 발송 (4096자 제한 대응 분할)."""
    for chunk in [text[i:i + 3900] for i in range(0, len(text), 3900)] or [""]:
        requests.post(API.format(token=_token(), method="sendMessage"),
                      json={"chat_id": _chat_id(), "text": chunk,
                            "disable_web_page_preview": False}, timeout=15)


# ---------- 명령 처리 ----------
def _fmt_keywords(cfg):
    inc = "\n".join(f"  · {k}" for k in cfg["keywords"]["hard_include"])
    exc = "\n".join(f"  · {k}" for k in cfg["keywords"]["hard_exclude"])
    return (f"📌 현재 필터 키워드\n\n✅ 무조건 통과 ({len(cfg['keywords']['hard_include'])}개)\n{inc}\n\n"
            f"🗑 무조건 제외 ({len(cfg['keywords']['hard_exclude'])}개)\n{exc}\n\n"
            f"수정: /add 키워드, /block 키워드, /remove 키워드")


def handle_command(text, cfg):
    """명령 1건 처리. (응답 문자열, config 변경 여부) 반환."""
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lower().split("@")[0]
    arg = parts[1].strip() if len(parts) > 1 else ""
    inc, exc = cfg["keywords"]["hard_include"], cfg["keywords"]["hard_exclude"]

    if cmd == "/keywords":
        return _fmt_keywords(cfg), False

    if cmd == "/add":
        if not arg:
            return "사용법: /add 키워드", False
        if any(str(k).lower() == arg.lower() for k in inc):
            return f"'{arg}' 는 이미 통과 목록에 있어요.", False
        inc.append(arg)
        return f"✅ '{arg}' → 무조건 통과 목록에 추가했어요. (다음 실행부터 적용)", True

    if cmd == "/block":
        if not arg:
            return "사용법: /block 키워드", False
        if any(str(k).lower() == arg.lower() for k in exc):
            return f"'{arg}' 는 이미 제외 목록에 있어요.", False
        exc.append(arg)
        return f"🗑 '{arg}' → 무조건 제외 목록에 추가했어요.", True

    if cmd == "/remove":
        if not arg:
            return "사용법: /remove 키워드", False
        removed = False
        for lst in (inc, exc):
            for k in list(lst):
                if str(k).lower() == arg.lower():
                    lst.remove(k)
                    removed = True
        return (f"➖ '{arg}' 를 목록에서 삭제했어요." if removed
                else f"'{arg}' 는 어느 목록에도 없어요. /keywords 로 확인해보세요."), removed

    if cmd == "/profile":
        return (f"👤 기본 프로필:\n{str(cfg['profile']['base']).strip()}\n\n"
                f"🔗 실시간 참조 페이지: {cfg['profile'].get('url') or '없음'}\n"
                f"(페이지를 수정하면 다음 실행부터 판정에 자동 반영됩니다)"), False

    if cmd == "/status":
        st = store.load_state("last_run.json", {})
        return ("아직 실행 기록이 없어요." if not st else
                f"🕐 마지막 실행: {st.get('time')}\n새 글 {st.get('new')}건 / "
                f"즉시 {st.get('instant')}건 / 다이제스트 대기 {st.get('digest')}건 / "
                f"버림 {st.get('dropped')}건\n오류: {st.get('errors') or '없음'}"), False

    return ("명령어: /keywords /add /block /remove /profile /status\n"
            "예) /add 학회  → '학회' 포함 공지는 무조건 통과"), False


def process_updates(cfg):
    """쌓인 텔레그램 메시지를 읽어 명령 처리. config 변경 여부 반환."""
    offset = store.load_state("tg_offset.json", {"offset": 0})["offset"]
    resp = requests.get(API.format(token=_token(), method="getUpdates"),
                        params={"offset": offset + 1, "timeout": 0}, timeout=20)
    changed = False
    for upd in resp.json().get("result", []):
        offset = upd["update_id"]
        msg = upd.get("message") or {}
        text = msg.get("text", "")
        # 본인 채팅만 처리 (보안)
        if str(msg.get("chat", {}).get("id")) != str(_chat_id()) or not text.startswith("/"):
            continue
        reply, did_change = handle_command(text, cfg)
        changed = changed or did_change
        send(reply)
    store.save_state("tg_offset.json", {"offset": offset})
    return changed
