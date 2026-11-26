"""fin-bid-board 실브라우저 점검 공용 도구(2b-T, t_9ebf54c4) — tnum_check·contrast_check·capture_states가 같이 쓴다.

  serve(docs)            : docs/ 폴더를 로컬 http.server로 띄운다(포트 자동).
  open_scene(ctx, ...)   : 화면(scene)별로 새 페이지를 열고 렌더 완료까지 기다린다.
                           loading = bids.json 응답 보류, error = fetch 중단(abort), empty = 결과 0건 검색.
화면 이름: latest · prespec · org · org-kdb · search · bid · pdet · loading · empty · error
"""
import functools
import http.server
import json
import os
import socketserver
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
VIEWS = {"m": {"width": 390, "height": 844}, "pc": {"width": 1280, "height": 840}}
SCHEMES = ("light", "dark")
NOW = "2026-11-26T18:00"          # D-day 고정(전후 캡처 비교용) — app.js ?now= 시험 인자
SEARCH_Q = "ISMP"
EMPTY_Q = "zz없는검색어"


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 — 상위 서명 유지
        pass


def serve(docs=DOCS):
    h = functools.partial(_Quiet, directory=docs)
    s = socketserver.TCPServer(("127.0.0.1", 0), h)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, "http://127.0.0.1:%d/index.html?now=%s" % (s.server_address[1], NOW)


def data(docs=DOCS):
    return json.load(open(os.path.join(docs, "data", "bids.json"), encoding="utf-8"))


def scene_hash(name, d):
    return {
        "latest": "#/latest", "prespec": "#/prespec", "org": "#/org", "org-kdb": "#/org/kdb",
        "search": "#/search?q=" + SEARCH_Q, "bid": "#/bid/" + d["bids"][0]["key"],
        "pdet": "#/prespec/" + d["prespecs"][0]["no"], "loading": "#/latest", "error": "#/latest",
        "empty": "#/search?q=" + EMPTY_Q,
    }[name]


READY = {
    "loading": None,
    "error": "#app .a-hint, #app .st-error",
    "bid": "#sheet .sheet", "pdet": "#sheet .sheet",
}


def new_context(br, vname, scheme):
    vp = VIEWS[vname]
    return br.new_context(viewport=vp, color_scheme=scheme, device_scale_factor=2,
                          is_mobile=(vname == "m"), has_touch=(vname == "m"))


def open_scene(ctx, base, name, d, errors=None):
    """새 페이지를 열어 화면을 그린 뒤 돌려준다(호출자가 close)."""
    pg = ctx.new_page()
    if errors is not None:
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" and name != "error" else None)
        pg.on("pageerror", lambda x: errors.append("pageerror: %s" % x))
    if name == "loading":
        held = []
        pg._held = held                                         # close_scene()이 닫기 전에 정리
        pg.route("**/data/bids.json", lambda r: held.append(r))  # 응답 보류 → 로딩 상태 유지
    elif name == "error":
        pg.route("**/data/bids.json", lambda r: r.abort())      # fetch 실패
    pg.goto(base + scene_hash(name, d), wait_until="domcontentloaded" if name == "loading" else "networkidle")
    sel = READY.get(name, "#app .xa-bid, #app .xa-co, #app .xa-ms, #app .a-hint")
    if sel:
        pg.wait_for_selector(sel)
    pg.evaluate("document.fonts.ready")
    pg.wait_for_timeout(500 if name != "loading" else 900)
    return pg


def close_scene(pg):
    for r in getattr(pg, "_held", []):
        try:
            r.abort()
        except Exception:  # noqa: BLE001 — 닫는 중 정리 실패는 무시
            pass
    pg.close()
