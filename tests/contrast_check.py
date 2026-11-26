#!/usr/bin/env python3
"""V-T3 글자 대비 점검(2b-T, t_9ebf54c4).

  /usr/bin/python3 tests/contrast_check.py [--docs <docs 폴더>] [--out <결과.json>]

보이는 글자(자기 텍스트 노드가 있는 요소 + 값이 있는 입력칸)의 글자색과 실제 배경색(조상 배경을 알파 합성)의
WCAG 대비를 잰다. 상세 시트가 열려 있으면 시트 안만(나머지는 스크림 아래), 아니면 #sheet 밖 전체.
aria-hidden(아이콘)·sr-only(1px)·화면 밖 가로 스크롤 영역은 제외하지 않는다(가로 칩은 스크롤하면 보이므로 포함).
범위: 라이트·다크 × 390·1280 × 최신 공고·사전규격·기관별·기관 상세·검색·공고 상세·사전규격 상세·로딩·빈 결과·오류.
판정: 3:1 미만 0이면 종료 코드 0. 본문 크기(18.66px 굵게·24px 미만) 4.5:1 미만 목록은 따로 보고.
하단 탭바 대비(탭바↔카드, 선택 글자, 비선택 글자)도 모바일 칸에서 같이 잰다.
"""
import argparse
import json
import os
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_harness as H  # noqa: E402

SCENES = ("latest", "prespec", "org", "org-kdb", "search", "bid", "pdet", "loading", "empty", "error")
# verify_board.py TABBAR_MIN(시안 t_6461f479 contrast.md ① 값)
TABBAR_MIN = {"light": {"bar_card": 16.56, "on": 11.00, "off": 8.26},
              "dark": {"bar_card": 9.97, "on": 11.32, "off": 6.45}}

JS = r"""() => {
 const parse = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number);
   return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
 const over = (top, bot) => { const a = top[3]; return [0,1,2].map(i => top[i]*a + bot[i]*(1-a)).concat([1]); };
 const bgOf = el => { const layers = []; for (let e = el; e; e = e.parentElement) { const c = parse(getComputedStyle(e).backgroundColor);
     if (c && c[3] > 0) { layers.push(c); if (c[3] >= 1) break; } }
   let acc = [255,255,255,1]; for (let i = layers.length - 1; i >= 0; i--) acc = over(layers[i], acc); return acc; };
 const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); };
   return 0.2126*f(c[0]) + 0.7152*f(c[1]) + 0.0722*f(c[2]); };
 const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x,y)+0.05)/(Math.min(x,y)+0.05); };
 const sheet = document.querySelector('#sheet .sheet');
 const scope = sheet ? [sheet] : [document.body];
 const out = [];
 for (const root of scope) for (const el of root.querySelectorAll('*')) {
   if (!sheet && el.closest('#sheet')) continue;
   if (el.closest('[aria-hidden=true]')) continue;
   let own = ''; for (const n of el.childNodes) if (n.nodeType === 3) own += n.textContent; own = own.trim();
   if (el.tagName === 'INPUT') own = (el.value || '').trim();
   if (!own) continue;
   const cs = getComputedStyle(el); if (cs.display === 'none' || cs.visibility === 'hidden' || el.offsetParent === null && cs.position !== 'fixed') continue;
   const r = el.getBoundingClientRect(); if (r.width <= 1 || r.height <= 1) continue;
   let op = 1; for (let e = el; e; e = e.parentElement) op *= +getComputedStyle(e).opacity; if (op < 0.05) continue;
   const bg = bgOf(el); let fg = parse(cs.color); fg = over([fg[0], fg[1], fg[2], fg[3]*op], bg);
   const size = parseFloat(cs.fontSize), w = +cs.fontWeight, large = size >= 24 || size >= 18.66 && w >= 700;
   out.push({sel: el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).join('.') : '') +
              ' < ' + (el.parentElement.className || el.parentElement.tagName), text: own.slice(0, 30), ratio: Math.round(ratio(fg, bg)*100)/100,
             fg: cs.color, bg: 'rgb(' + bg.slice(0,3).map(Math.round).join(',') + ')', size, w, large});
 }
 return out; }"""

TAB_JS = """() => { const n = document.querySelector('.nav'); if (!n || getComputedStyle(n).display === 'none') return null;
  const on = n.querySelector('a.on'), off = n.querySelector('a:not(.on)'), card = document.querySelector('#app .xa-card'), cs = e => getComputedStyle(e);
  return {bar: cs(n).backgroundColor, card: card ? cs(card).backgroundColor : null, onColor: on ? cs(on).color : null,
          onBg: on ? cs(on).backgroundColor : null, offColor: cs(off).color}; }"""


def _rgb(s):
    import re
    return [float(x) for x in re.findall(r"[\d.]+", s)[:3]]


def _lum(c):
    f = [(v / 255.0) / 12.92 if v / 255.0 <= 0.03928 else ((v / 255.0 + 0.055) / 1.055) ** 2.4 for v in c]
    return 0.2126 * f[0] + 0.7152 * f[1] + 0.0722 * f[2]


def ratio(a, b):
    x, y = sorted([_lum(_rgb(a)), _lum(_rgb(b))], reverse=True)
    return round((x + 0.05) / (y + 0.05), 2)


def run(docs):
    d = H.data(docs)
    srv, base = H.serve(docs)
    res = {"docs": docs, "cells": {}, "tabbar": {}}
    with sync_playwright() as p:
        br = p.chromium.launch()
        for vname in H.VIEWS:
            for scheme in H.SCHEMES:
                ctx = H.new_context(br, vname, scheme)
                for sc in SCENES:
                    pg = H.open_scene(ctx, base, sc, d)
                    items = pg.evaluate(JS)
                    res["cells"]["%s-%s-%s" % (vname, scheme, sc)] = items
                    if vname == "m" and sc == "latest":
                        tb = pg.evaluate(TAB_JS)
                        if tb and tb["card"]:
                            m = {"bar_card": ratio(tb["bar"], tb["card"]), "on": ratio(tb["onColor"], tb["onBg"]),
                                 "off": ratio(tb["offColor"], tb["bar"])}
                            m["min"] = TABBAR_MIN[scheme]
                            m["ok"] = all(m[k] >= TABBAR_MIN[scheme][k] for k in ("bar_card", "on", "off"))
                            res["tabbar"][scheme] = dict(m, raw=tb)
                    H.close_scene(pg)
                ctx.close()
        br.close()
    srv.shutdown()
    allit = [(k, it) for k, v in res["cells"].items() for it in v]
    res["text_items"] = len(allit)
    res["min_ratio"] = min(it["ratio"] for _, it in allit) if allit else None
    res["min_item"] = min(allit, key=lambda x: x[1]["ratio"]) if allit else None
    under3 = [(k, it) for k, it in allit if it["ratio"] < 3]
    body45 = [(k, it) for k, it in allit if it["ratio"] < 4.5 and not it["large"]]
    group = lambda lst: sorted({(it["sel"], it["fg"], it["bg"], it["ratio"]) for _, it in lst}, key=lambda x: x[3])  # noqa: E731
    res["under3_count"] = len(under3)
    res["under3"] = [list(x) for x in group(under3)]
    res["body_under45_count"] = len(body45)
    res["body_under45"] = [list(x) for x in group(body45)]
    res["tabbar_ok"] = all(v["ok"] for v in res["tabbar"].values()) and len(res["tabbar"]) == 2
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default=H.DOCS)
    ap.add_argument("--out")
    a = ap.parse_args()
    res = run(os.path.abspath(a.docs))
    if a.out:
        json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("글자 요소 %d개 · 최소 대비 %s (%s)" % (res["text_items"], res["min_ratio"], res["min_item"]))
    print("3:1 미만: %d건" % res["under3_count"])
    for x in res["under3"][:20]:
        print("   ", x)
    print("본문 4.5:1 미만: %d건(종류 %d)" % (res["body_under45_count"], len(res["body_under45"])))
    for x in res["body_under45"][:40]:
        print("   ", x)
    print("하단 탭바:", {k: {x: v[x] for x in ("bar_card", "on", "off", "ok")} for k, v in res["tabbar"].items()})
    return 0 if res["under3_count"] == 0 and res["tabbar_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
