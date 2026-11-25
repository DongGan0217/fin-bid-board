#!/usr/bin/env python3
"""fin-bid-board 검증(B-2, t_5d8d9af0) — 로컬 http.server로 docs/를 띄우고 Playwright(Chromium)로 점검한다.

  /usr/bin/python3 tests/verify_board.py --db <fbw.db 읽기 전용 사본> --out <캡처·결과 폴더>

점검: 콘솔 오류 0 · 렌더 건수 = bids.json 건수 · 검색 'ISMP' 건수 = DB 조회 수 · 라우트 직접 진입 ·
      390/1280 × 라이트/다크 캡처 · 카드 금지어/담당자 필드 부재. 결과는 <out>/verify.json.
      + 사전규격 탭(t_63a567e3): 게시중 수 = status '게시중' 수 · 마감 포함(3개월) = prespecs 전체 수 ·
      기관별/검색 화면 사전규격 0건 · 상세 S-1(링크 버튼 / 링크 없을 때 안내) · PC S-2(오른쪽 패널 없음) ·
      하단 탭바 ① 대비 실측 ≥ 시안 값 · app.css 새 HEX 0(main 대비).
"""
import argparse
import calendar
import datetime
import functools
import http.server
import json
import os
import re
import socketserver
import sqlite3
import subprocess
import threading

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
VIEWS = {"m": {"width": 390, "height": 844}, "pc": {"width": 1280, "height": 840}}
CARD_BANNED = ["추정", "낙찰", "게시", "공고번호", "나라장터", "R26BK", "정정공고", "재등록", "담당"]
BUILTIN_TOPICS = ["ISP·ISMP·컨설팅", "AI·데이터", "회계·세무자문", "연구용역", "감리", "구축·개발",
                  "유지보수", "운영·위탁", "회선·인프라", "기타"]


def cutoff(today, months):
    y, m = divmod(today.year * 12 + today.month - 1 - months, 12)
    m += 1
    return datetime.date(y, m, min(today.day, calendar.monthrange(y, m)[1])).isoformat()


# 시안 t_6461f479 contrast.md ① 값(라이트 / 다크): 탭바↔카드, 선택 글자(알약 위), 비선택 글자(탭바 위)
TABBAR_MIN = {"light": {"bar_card": 16.56, "on": 11.00, "off": 8.26},
              "dark": {"bar_card": 9.97, "on": 11.32, "off": 6.45}}


def _lum(rgb):
    def ch(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = [ch(x) for x in rgb]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted([_lum(a), _lum(b)], reverse=True)
    return round((la + 0.05) / (lb + 0.05), 2)


def parse_rgb(css):
    return [int(float(x)) for x in re.findall(r"[\d.]+", css)[:3]]


def hex_check():
    """app.css의 HEX 중 main 브랜치 app.css에 없는 값(새 HEX) — 0이어야 함."""
    cur = open(os.path.join(DOCS, "assets", "app.css"), encoding="utf-8").read()
    try:
        base = subprocess.run(["git", "-C", ROOT, "show", "main:docs/assets/app.css"], capture_output=True,
                              text=True, check=True).stdout
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}
    hx = lambda t: {h.upper() for h in re.findall(r"#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b", t)}  # noqa: E731
    js = open(os.path.join(DOCS, "assets", "app.js"), encoding="utf-8").read()
    return {"new_hex_css": sorted(hx(cur) - hx(base)), "hex_in_js": sorted(hx(js)),
            "rgba_new": sorted(set(re.findall(r"rgba\([^)]*\)", cur)) - set(re.findall(r"rgba\([^)]*\)", base)))}


def tabbar(pg):
    return pg.evaluate("""() => {
      const n = document.querySelector('.nav'), on = n.querySelector('a.on'), off = n.querySelector('a:not(.on)');
      const card = document.querySelector('#app .xa-card'), cs = e => getComputedStyle(e);
      return {bar: cs(n).backgroundColor, card: card ? cs(card).backgroundColor : null,
              onColor: cs(on).color, onBg: cs(on).backgroundColor, onWeight: cs(on).fontWeight,
              offColor: cs(off).color, labels: [...n.querySelectorAll('a')].map(a => [...a.childNodes].filter(c => c.nodeType === 3).map(c => c.textContent).join('').trim()),
              onIconFilled: on.querySelector('.ms').classList.contains('f'),
              tabs: [...n.querySelectorAll('a')].map(a => { const r = a.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; }),
              clipped: [...n.querySelectorAll('a')].filter(a => a.scrollWidth > a.clientWidth + 1).length};
    }""")


def prespec_checks(pg, newpage, base, data, a, vname, scheme, res):
    """사전규격 탭: 건수·토글·상세(S-1)·PC 폭(S-2)·탭바 대비·기관별/검색 미포함."""
    out = {}
    pre = data.get("prespecs") or []
    n_open = sum(1 for p in pre if p["status"] == "게시중")
    shot = lambda name, full=False: (pg.screenshot(path=os.path.join(a.out, "%s%s-%s-%s.png" % (a.prefix, vname, scheme, name)), full_page=full),  # noqa: E731
                                     res["shots"].append(os.path.join(a.out, "%s%s-%s-%s.png" % (a.prefix, vname, scheme, name))))
    pg.goto(base + "#/prespec", wait_until="networkidle")
    pg.wait_for_selector("#app .xa-pre")
    pg.evaluate("document.fonts.ready")
    pg.wait_for_timeout(200)
    out["open_default_1m"] = pg.locator("#app .xa-pre").count()
    out["open_json"] = n_open
    out["tab_on"] = pg.evaluate("(document.querySelector(vname==='m' ? '.nav a.on' : '.gnb nav a.on')||{}).textContent".replace("vname", repr(vname)))
    out["side_panel"] = pg.locator("#app .xa-side").count()
    if vname == "pc":
        out["list_width"] = pg.evaluate("Math.round(document.querySelector('#app [data-pre-list]').getBoundingClientRect().width)")
        out["title_width"] = pg.evaluate("Math.round(document.querySelector('#app .xa-pre .b2').getBoundingClientRect().width)")
    else:
        tb = tabbar(pg)
        bar, card, on_c, on_bg, off_c = (parse_rgb(tb[k]) for k in ("bar", "card", "onColor", "onBg", "offColor"))
        out["tabbar"] = dict(tb, bar_card=contrast(bar, card), on=contrast(on_c, on_bg), off=contrast(off_c, bar),
                             min=TABBAR_MIN[scheme])
        out["tabbar"]["ok"] = (all(out["tabbar"][k] >= TABBAR_MIN[scheme][k] for k in ("bar_card", "on", "off"))
                               and tb["labels"] == ["최신 공고", "최신 사전규격", "기관별", "검색"]
                               and int(tb["onWeight"]) >= 700 and tb["onIconFilled"] and not tb["clipped"]
                               and all(w >= 48 and h >= 48 for w, h in tb["tabs"]))
    # 마감 포함 + 3개월 → prespecs 전체
    pg.click("#app .dd")
    pg.click("#sheet .opt[data-m='3']")
    pg.wait_for_timeout(200)
    out["open_3m"] = pg.locator("#app .xa-pre").count()
    pg.click('#app [data-act="pc"]')
    pg.wait_for_timeout(200)
    out["with_closed_3m"] = pg.locator("#app .xa-pre").count()
    out["json_total"] = len(pre)
    out["closed_badges"] = pg.locator("#app .xa-pre .bd.x").count()
    pg.evaluate("(() => { const e = document.querySelector('#app .xa-pre .bd.x'); if (e) window.scrollTo(0, e.closest('.xa-card').getBoundingClientRect().top + scrollY - 220); })()")
    pg.wait_for_timeout(200)
    shot("prespec-closed")
    pg.click('#app [data-act="pc"]')                 # 끄기 → 게시중만
    pg.wait_for_timeout(150)
    out["after_toggle_off"] = pg.locator("#app .xa-pre").count()
    # 카드 클릭 → 상세 → 닫기
    pg.evaluate("window.scrollTo(0,0)")
    first = [p for p in pre if p["status"] == "게시중"]
    pg.locator("#app .xa-pre").first.click()
    pg.wait_for_selector("#sheet .sheet")
    out["click_hash"] = pg.evaluate("location.hash")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(300)
    out["after_close"] = pg.evaluate("location.hash")
    # 상세 직접 진입(S-1 링크 있음)
    p0 = sorted(first, key=lambda p: p["ddln"] or "")[-1] if first else pre[0]
    pg2 = newpage()
    pg2.goto(base + "#/prespec/" + p0["no"], wait_until="networkidle")
    pg2.wait_for_selector("#sheet .sheet")
    pg2.evaluate("document.fonts.ready")
    pg2.wait_for_timeout(300)
    det = pg2.evaluate("""() => ({labels: [...document.querySelectorAll('#sheet .kv>span')].map(e => e.textContent),
      btn1: (document.querySelector('#sheet a.btn1')||{}).href || null, pn: !!document.querySelector('#sheet .pn'),
      copy: (document.querySelector('#sheet [data-act=copy]')||{}).textContent || '', base: (document.querySelector('#app h1')||{}).textContent || ''})""")
    det["no"] = p0["no"]
    out["detail_link"] = det
    p_ = pg2
    p_.screenshot(path=os.path.join(a.out, "%s%s-%s-prespec-detail.png" % (a.prefix, vname, scheme)))
    res["shots"].append(os.path.join(a.out, "%s%s-%s-prespec-detail.png" % (a.prefix, vname, scheme)))
    pg2.keyboard.press("Escape")
    pg2.wait_for_timeout(300)
    out["detail_close_to"] = pg2.evaluate("location.hash")
    pg2.close()
    # 상세 S-1 안내(링크 없는 데이터로 대체 응답)
    d2 = dict(data)
    d2["prespecs"] = [dict(p, url=None) for p in pre]
    pg3 = newpage()
    pg3.route("**/data/bids.json", lambda r: r.fulfill(status=200, content_type="application/json",
                                                        body=json.dumps(d2, ensure_ascii=False)))
    pg3.goto(base + "?nolink=1#/prespec/" + p0["no"], wait_until="networkidle")
    pg3.wait_for_selector("#sheet .sheet")
    pg3.evaluate("document.fonts.ready")
    pg3.wait_for_timeout(300)
    out["detail_nolink"] = pg3.evaluate("""() => ({btn1: !!document.querySelector('#sheet a.btn1'),
      pn: (document.querySelector('#sheet .pn')||{}).textContent || '', copy: !!document.querySelector('#sheet [data-act=copy]')})""")
    pg3.screenshot(path=os.path.join(a.out, "%s%s-%s-prespec-detail-nolink.png" % (a.prefix, vname, scheme)))
    res["shots"].append(os.path.join(a.out, "%s%s-%s-prespec-detail-nolink.png" % (a.prefix, vname, scheme)))
    pg3.close()
    # 기관별·검색에는 사전규격 없음
    nopre = {}
    for h in ("#/org", "#/org/kexim", "#/search?q=ISMP", "#/search?q=" + (pre[0]["no"] if pre else "R26BD")):
        pg.goto(base + h, wait_until="networkidle")
        pg.wait_for_timeout(250)
        nopre[h] = pg.locator("#app .xa-pre, #app .pt").count()
    out["no_prespec_elsewhere"] = nopre
    want_labels = ["발주기관", "배정예산", "공개일시", "의견등록 마감", "진행상태", "주제", "사전규격등록번호", "입찰공고 연결"]
    out["ok"] = (out["open_default_1m"] == n_open and out["with_closed_3m"] == len(pre) and out["after_toggle_off"] == out["open_3m"]
                 and out["side_panel"] == 0 and det["labels"] == want_labels and bool(det["btn1"]) == bool(p0.get("url"))
                 and det["copy"].endswith("등록번호 복사") and out["detail_nolink"]["btn1"] is False
                 and "나라장터 › 발주목록에서 사전규격등록번호로 검색" in out["detail_nolink"]["pn"]
                 and out["click_hash"].startswith("#/prespec/") and out["after_close"] == "#/prespec"
                 and out["detail_close_to"] == "#/prespec" and not any(nopre.values())
                 and out["tab_on"].strip().endswith("최신 사전규격")
                 and (vname == "m" and out["tabbar"]["ok"] or vname == "pc" and out["list_width"] == 1120))
    return out


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


def chip_state(pg):
    return pg.evaluate("""() => {
      const g = document.querySelector('#app .chips[aria-label="주제"]');
      const gr = g.getBoundingClientRect();
      return [...g.querySelectorAll('button.c')].map(b => {
        const r = b.getBoundingClientRect();
        return {label: b.firstChild.textContent.trim(), n: +(b.querySelector('i')||{textContent:'-1'}).textContent,
                top: Math.round(r.top), left: Math.round(r.left), right: Math.round(r.right),
                textClipped: b.scrollWidth > b.clientWidth + 1, insideRow: r.right <= gr.right + 1 && r.left >= gr.left - 1};
      }).concat([{row: true, scrollW: g.scrollWidth, clientW: g.clientWidth}]);
    }""")


def topic_checks(pg, base, data, a, vname, res):
    """주제 칩 v2: 표시 순서·건수(0건 포함)·클릭 필터·줄바꿈/잘림 + 내장 목록 폴백."""
    from collections import Counter
    out = {}
    want_order = data.get("topics") or []
    pg.goto(base + "#/latest", wait_until="networkidle")
    pg.wait_for_selector("#app .xa-bid")
    pg.click("#app .dd")
    pg.click("#sheet .opt[data-m='3']")            # 3개월 = export 전체
    pg.wait_for_timeout(200)
    pg.evaluate("document.fonts.ready")
    st = chip_state(pg)
    row, chips = st[-1], st[:-1]
    want_n = Counter(b["topic"] for b in data["bids"])
    out["labels"] = [c["label"] for c in chips]
    out["counts"] = {c["label"]: c["n"] for c in chips}
    out["order_ok"] = out["labels"] == want_order and len(chips) == 10
    out["counts_ok"] = all(c["n"] == want_n.get(c["label"], 0) for c in chips)
    out["ai_zero_chip"] = out["counts"].get("AI·데이터") == 0
    out["text_clipped"] = [c["label"] for c in chips if c["textClipped"]]
    out["rows"] = len({c["top"] for c in chips})
    out["row_scroll"] = {"scrollW": row["scrollW"], "clientW": row["clientW"]}
    shot = os.path.join(a.out, "%s%s-light-topic-chips.png" % (a.prefix, vname))
    pg.screenshot(path=shot, full_page=False)
    res["shots"].append(shot)
    if vname == "m":                                 # 가로 스크롤 끝까지 → 마지막 칩(기타) 노출 캡처
        pg.evaluate("document.querySelector('#app .chips[aria-label=\"주제\"]').scrollLeft = 1e5")
        pg.wait_for_timeout(150)
        last = chip_state(pg)[-2]
        out["last_chip_visible_after_scroll"] = last["label"] == want_order[-1] and last["insideRow"]
        shot = os.path.join(a.out, "%s%s-light-topic-chips-end.png" % (a.prefix, vname))
        pg.screenshot(path=shot, full_page=False)
        res["shots"].append(shot)
    else:
        out["all_inside_row"] = all(c["insideRow"] for c in chips)
    clicks = {}
    for t in want_order:                             # 칩 클릭 → 카드 수 = 칩 건수
        pg.click('#app .chips[aria-label="주제"] button[data-v="%s"]' % t)
        pg.wait_for_timeout(80)
        clicks[t] = pg.locator("#app .xa-bid").count()
        if t == "AI·데이터":
            out["ai_empty_hint"] = pg.locator("#app .a-hint").count() == 1
        pg.click('#app .chips[aria-label="주제"] button[data-v="%s"]' % t)   # 해제
        pg.wait_for_timeout(80)
    out["click_counts_ok"] = all(clicks[t] == want_n.get(t, 0) for t in want_order)
    # 폴백: topics 없는 bids.json → 내장 10개
    d2 = dict(data)
    d2.pop("topics", None)
    pg.route("**/data/bids.json", lambda r: r.fulfill(status=200, content_type="application/json",
                                                       body=json.dumps(d2, ensure_ascii=False)))
    pg.goto(base + "?fb=1#/latest", wait_until="networkidle")
    pg.wait_for_selector("#app .xa-bid")
    out["fallback_labels_ok"] = [c["label"] for c in chip_state(pg)[:-1]] == BUILTIN_TOPICS
    pg.unroute("**/data/bids.json")
    ok_keys = ["order_ok", "counts_ok", "ai_zero_chip", "click_counts_ok", "fallback_labels_ok", "ai_empty_hint"]
    ok_keys.append("last_chip_visible_after_scroll" if vname == "m" else "all_inside_row")
    out["ok"] = all(out.get(k) for k in ok_keys) and not out["text_clipped"]
    return out


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
    res = {"base": base, "bids_json": n_bids, "console_errors": [], "routes": {}, "shots": [], "checks": {},
           "topic_checks": {}, "prespec_checks": {}, "hex": hex_check()}
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
                          ("search-ISMP", "#/search?q=ISMP"), ("bid", "#/bid/" + bid_key), ("root", ""),
                          ("prespec", "#/prespec")]
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
                    res["topic_checks"]["%s" % vname] = topic_checks(pg, base, data, a, vname, res)
                    pg.goto(base + "#/latest", wait_until="networkidle")
                    pg.wait_for_selector("#app .xa-bid")
                    pg.evaluate("document.fonts.ready")
                    shot = os.path.join(a.out, "%s%s-light-latest-full.png" % (a.prefix, vname))
                    pg.screenshot(path=shot, full_page=True)
                    res["shots"].append(shot)
                pgp = newpage()
                res["prespec_checks"]["%s-%s" % (vname, scheme)] = prespec_checks(pgp, newpage, base, data, a, vname, scheme, res)
                pgp.close()
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
        "topic_checks_ok": all(v.get("ok") for v in res["topic_checks"].values()) and len(res["topic_checks"]) == 2,
        "prespec_checks_ok": all(v.get("ok") for v in res["prespec_checks"].values()) and len(res["prespec_checks"]) == 4,
        "prespec_counts": {k: [v["open_default_1m"], v["open_json"], v["with_closed_3m"], v["json_total"]]
                           for k, v in res["prespec_checks"].items()},
        "tabbar": {k: {x: v["tabbar"][x] for x in ("bar_card", "on", "off", "ok")}
                   for k, v in res["prespec_checks"].items() if "tabbar" in v},
        "new_hex_css": res["hex"].get("new_hex_css"), "hex_in_js": res["hex"].get("hex_in_js"),
        "rgba_new": res["hex"].get("rgba_new"),
    })
    json.dump(res, open(os.path.join(a.out, a.prefix + "verify.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(res["checks"], ensure_ascii=False, indent=1))
    print("console_errors:", res["console_errors"][:10])


if __name__ == "__main__":
    main()
