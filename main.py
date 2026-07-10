# -*- coding: utf-8 -*-
"""메인 실행: GitHub Actions가 매일 아침(KST 08시경) 1회 실행.

순서:
1. 텔레그램 명령 처리 (키워드 수정 등) → config.yaml 반영
2. 게시판 크롤 → 지난 하루 새 글 감지
3. 규칙 필터 + Claude 판정 (프로필 페이지 실시간 참조)
4. 아침 리포트 한 통으로 발송:
   🚨 중요(8점↑) → ☀️ 일반(5~7점) → 🗑 걸러진 글 목록
"""
from datetime import datetime, timedelta, timezone

import crawler
import pipeline
import store
import telegram_bot as tg

KST = timezone(timedelta(hours=9))


def fmt_post(p):
    v = p["verdict"]
    dl = f"\n⏰ 마감: {v['deadline']}" if v.get("deadline") else ""
    return (f"[{p['source']}]\n{p['title']}\n"
            f"⭐ {v['score']}/10 · {v.get('category', '')} — {v.get('reason', '')}{dl}\n{p['url']}")


def main():
    cfg = store.load_config()

    # 1. 텔레그램 명령 처리 (키워드/설정 변경 시 config.yaml 저장)
    try:
        if tg.process_updates(cfg):
            store.save_config(cfg)
            cfg = store.load_config()
    except Exception as e:
        print(f"텔레그램 명령 처리 실패: {e}")

    # 2. 크롤
    seen = set(store.load_state("seen.json", []))
    first_run = len(seen) == 0
    new_posts, errors = crawler.crawl_all(cfg["sources"], seen)
    store.save_state("seen.json", sorted(seen))

    now = datetime.now(KST)
    if first_run:
        tg.send(f"🔧 초기 설정 완료! 기존 글 {len(new_posts)}건을 기준선으로 저장했어요.\n"
                f"내일 아침부터 새로 올라온 글만 정리해서 보내드립니다.\n명령어 안내는 /help")
        store.save_state("last_run.json", {
            "time": now.strftime("%m/%d %H:%M"),
            "new": 0, "instant": 0, "digest": 0, "dropped": 0, "errors": errors})
        return

    # 3. 필터 + 판정
    profile = pipeline.build_profile(cfg)
    instant, digest, dropped = pipeline.process_posts(new_posts, cfg, profile)

    # 4. 아침 리포트 한 통 (섹션별 정리)
    sections = []
    if instant:
        sections.append("🚨 놓치면 안 되는 공지 (" + str(len(instant)) + "건)\n\n"
                        + "\n\n".join(fmt_post(p) for p in sorted(
                            instant, key=lambda p: -p["verdict"]["score"])))
    if digest:
        sections.append("☀️ 알아두면 좋은 공지 (" + str(len(digest)) + "건)\n\n"
                        + "\n\n".join(fmt_post(p) for p in sorted(
                            digest, key=lambda p: -p["verdict"]["score"])[:15]))
    if dropped:
        titles = "\n".join(f"  · {p['title'][:50]}" for p in dropped[:20])
        sections.append(f"🗑 걸러진 글 ({len(dropped)}건)\n{titles}\n\n"
                        f"필요한 게 걸러졌다면 /add 키워드 로 조정하세요.")

    header = f"📋 {now.strftime('%m/%d')} SNU 공지 리포트"
    today = now.strftime("%Y-%m-%d")
    last_report = store.load_state("report_sent.json", {"date": ""})
    if sections:
        # 새 글이 있으면 항상 발송 (같은 날 두 번째 실행이어도 그 사이 새 글만 실림)
        tg.send(header + "\n\n" + "\n\n" + ("\n" + "─" * 20 + "\n\n").join(sections))
        store.save_state("report_sent.json", {"date": today})
    elif last_report["date"] != today:
        # 새 글이 없어도 하루 한 번은 생존 신호를 보냄
        tg.send(header + "\n\n어제는 새로 올라온 글이 없었어요."
                + (f"\n⚠️ 수집 오류: {errors}" if errors else ""))
        store.save_state("report_sent.json", {"date": today})
    # 오늘 이미 리포트를 보냈고 새 글도 없으면 조용히 종료 (예약 이중화 대비)

    store.save_state("last_run.json", {
        "time": now.strftime("%m/%d %H:%M"), "new": len(new_posts),
        "instant": len(instant), "digest": len(digest),
        "dropped": len(dropped), "errors": errors})
    print(f"완료: 새 글 {len(new_posts)} / 중요 {len(instant)} / 일반 {len(digest)} / 버림 {len(dropped)}")


if __name__ == "__main__":
    main()
