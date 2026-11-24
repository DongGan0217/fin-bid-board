#!/usr/bin/env python3
"""fin-bid-board 검증(B-2, t_5d8d9af0) — 로컬 http.server로 docs/를 띄우고 Playwright(Chromium)로 점검한다.

  /usr/bin/python3 tests/verify_board.py --db <fbw.db 읽기 전용 사본> --out <캡처·결과 폴더>

점검: 콘솔 오류 0 · 렌더 건수 = bids.json 건수 · 검색 'ISMP' 건수 = DB 조회 수 · 라우트 직접 진입 ·
      390/1280 × 라이트/다크 캡처 · 카드 금지어/담당자 필드 부재. 결과는 <out>/verify.json.
"""
import argparse
import calendar
import datetime
import functools
import http.server
import json
import os
import socketserver
import sqlite3
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
VIEWS = {"m": {"width": 390, "height": 844}, "pc": {"width": 1280, "height": 840}}
CARD_BANNED = ["추정", "낙찰", "게시", "공고번호", "나라장터", "R26BK", "정정공고", "재등록", "담당"]


def cutoff(today, months):
    y, m = divmod(today.year * 12 + today.month - 1 - months, 12)
    m += 1
    return datetime.date(y, m, min(today.day, calendar.monthrange(y, m)[1])).isoformat()


def db_count(db, q, today, months=3):
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True)
    like = "%" + q + "%"
    n = con.execute("SELECT count(*) FROM bids WHERE source='g2b' AND posted_at >= ? AND "
                    "(title LIKE ? OR demand_dept LIKE ? OR bid_key LIKE ?)",
                    (cutoff(today, months), like, like, like)).fetchone()[0]
    con.close()
    return n


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 — 상위 서명 유지
        pass


def serve():
    h = functools.partial(Quiet, directory=DOCS)
    s = socketserver.TCPServer(("127.0.0.1", 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, "http://127.0.0.1:%d/" % s.server_address[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--prefix", default="")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    data = json.load(open(os.path.join(DOCS, "data", "bids.json"), encoding="utf-8"))
    n_bids = len(data["bids"])
    keys = {b["key"] for b in data["bids"]}
    ismp = [b for b in data["bids"] if "ismp" in (b["title"] + b["org"] + (b["dept"] or "") + b["key"]).lower()]
    bid_key = ismp[-1]["key"] if ismp else data["bids"][0]["key"]
    srv, base = serve()
    res = {"base": base, "bids_json": n_bids, "console_errors": [], "routes": {}, "shots": [], "checks": {}}
    today = datetime.date.today()
    res["checks"]["ismp_db"] = db_count(a.db, "ISMP", today)

    with sync_playwright() as p:
        br = p.chromium.launch()
        for vname, vp in VIEWS.items():
            for scheme in ("light", "dark"):
                ctx = br.new_context(viewport=vp, color_scheme=scheme, device_scale_factor=2,
                                     is_mobile=(vname == "m"), has_touch=(vname == "m"))
                errs = []

                def newpage(e=errs):
                    pg_ = ctx.new_page()
                    pg_.on("console", lambda m: e.append(m.text) if m.type == "error" else None)
                    pg_.on("pageerror", lambda x: e.append("pageerror: %s" % x))
                    return pg_
                routes = [("latest", "#/latest"), ("org", "#/org"), ("org-kdb", "#/org/kdb"),
                          ("search-ISMP", "#/search?q=ISMP"), ("bid", "#/bid/" + bid_key), ("root", "")]
                for rname, h in routes:
                    pg = newpage()  # 라우트마다 새 문서로 직접 진입
                    pg.goto(base + h, wait_until="networkidle")
                    pg.wait_for_function("document.querySelector('#app .a-hint, #app .xa-bid, #app .xa-co, #app .xa-ms') !== null")
                    pg.evaluate("document.fonts.ready")
                    pg.wait_for_timeout(300)
                    info = pg.evaluate("""() => ({
                      cards: document.querySelectorAll('#app .xa-bid').length,
                      orgs: document.querySelectorAll('#app .xa-co').length,
                      tabOn: (document.querySelector('.nav a.on, .gnb nav a.on')||{}).textContent || '',
                      sheet: !!document.querySelector('#sheet .sheet'),
                      sheetTitle: (document.querySelector('#sheet .dt-t')||{}).textContent || '',
                      count: (document.querySelector('#app .xa-ms')||{dataset:{}}).dataset.count || null,
                      h1: (document.querySelector('#app h1')||{}).textContent || '',
                      updated: [...document.querySelectorAll('#app .xa-mm span, #app .xa-l1c span')].map(e=>e.textContent).filter(t=>t.startsWith('갱신'))[0] || '',
                      overflowX: document.documentElement.scrollWidth > window.innerWidth,
                      cardTexts: [...document.querySelectorAll('#app .xa-bid')].map(e=>e.innerText),
                      robots: (document.querySelector('meta[name=robots]')||{}).content || ''
                    })""")
                    texts = info.pop("cardTexts")
                    info["banned_in_cards"] = sorted({w for t in texts for w in CARD_BANNED if w in t})
                    res["routes"]["%s-%s-%s" % (vname, scheme, rname)] = info
                    shot = os.path.join(a.out, "%s%s-%s-%s.png" % (a.prefix, vname, scheme, rname))
                    pg.screenshot(path=shot, full_page=False)
                    res["shots"].append(shot)
                    if rname == "bid":  # 직접 진입한 상세를 닫으면 최신 공고로
                        pg.keyboard.press("Escape")
                        pg.wait_for_timeout(300)
                        info["close_to"] = pg.evaluate("location.hash")
                    pg.close()
                pg = newpage()
                # 기간 전환(3개월) 후 렌더 건수 + 전체 높이 캡처(최신 공고)
                pg.goto(base + "#/latest", wait_until="networkidle")
                pg.wait_for_selector("#app .xa-bid")
                pg.click("#app .dd")
                pg.click("#sheet .opt[data-m='3']")
                pg.wait_for_timeout(200)
                res["routes"]["%s-%s-latest-3m" % (vname, scheme)] = {"cards": pg.locator("#app .xa-bid").count()}
                # 카드 클릭 → 상세 → 닫기(뒤로)
                pg.locator("#app .xa-bid").first.click()
                pg.wait_for_selector("#sheet .sheet")
                opened = pg.evaluate("location.hash")
                pg.keyboard.press("Escape")
                pg.wait_for_timeout(300)
                res["routes"]["%s-%s-click-detail" % (vname, scheme)] = {
                    "opened": opened, "after_close": pg.evaluate("location.hash"),
                    "sheet_after": pg.locator("#sheet .sheet").count()}
                # 검색 입력(실시간)
                pg.goto(base + "#/search", wait_until="networkidle")
                pg.wait_for_selector("#q")
                pg.fill("#q", "ismp")
                pg.wait_for_timeout(400)
                res["routes"]["%s-%s-search-type" % (vname, scheme)] = {
                    "count": pg.evaluate("(document.querySelector('#app .xa-ms')||{dataset:{}}).dataset.count"),
                    "hash": pg.evaluate("location.hash"), "hl": pg.locator("#app .hl").count()}
                if scheme == "light":
                    pg.goto(base + "#/latest", wait_until="networkidle")
                    pg.wait_for_selector("#app .xa-bid")
                    pg.evaluate("document.fonts.ready")
                    shot = os.path.join(a.out, "%s%s-light-latest-full.png" % (a.prefix, vname))
                    pg.screenshot(path=shot, full_page=True)
                    res["shots"].append(shot)
                res["console_errors"] += ["%s-%s: %s" % (vname, scheme, e) for e in errs]
                ctx.close()
        br.close()
    srv.shutdown()

    r = res["routes"]
    res["checks"].update({
        "console_errors": len(res["console_errors"]),
        "latest_cards_all_views": sorted({v["cards"] for k, v in r.items() if k.endswith("-latest")}),
        "latest_3m_cards": sorted({v["cards"] for k, v in r.items() if k.endswith("-latest-3m")}),
        "ismp_page": sorted({v["count"] for k, v in r.items() if k.endswith("-search-ISMP")}),
        "ismp_typed": sorted({v["count"] for k, v in r.items() if k.endswith("-search-type")}),
        "bid_sheet_open": all(v["sheet"] for k, v in r.items() if k.endswith("-bid")),
        "banned_in_cards": sorted({w for v in r.values() for w in v.get("banned_in_cards", [])}),
        "overflow_x": [k for k, v in r.items() if v.get("overflowX")],
        "robots_meta": sorted({v.get("robots") for v in r.values() if "robots" in v}),
        "bid_key": bid_key, "bid_key_in_data": bid_key in keys,
    })
    json.dump(res, open(os.path.join(a.out, a.prefix + "verify.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(res["checks"], ensure_ascii=False, indent=1))
    print("console_errors:", res["console_errors"][:10])


if __name__ == "__main__":
    main()
