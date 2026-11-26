#!/usr/bin/env python3
"""V-T2 tnum 점검(2b-T, t_9ebf54c4) — PM 점검 스크립트(~/.hermes/cache/fbb-tds/pm_tnum_audit.py) 기준.

  /usr/bin/python3 tests/tnum_check.py [--docs <docs 폴더>] [--out <결과.json>]

숫자가 든 텍스트(자기 텍스트 노드)를 가진 보이는 요소 중 computed font-variant-numeric에 tabular-nums가
없는 요소 수를 센다. 제목(.b2 사업명 · .dt-t 상세 제목, 그 안 강조·취소선 포함)은 제외. aria-hidden(아이콘) 제외.
범위: 라이트·다크 × 390·1280 × 최신 공고·최신 사전규격·기관별·기관 상세(kdb)·검색·공고 상세·사전규격 상세.
'pm' 값 = PM 원 스크립트와 같은 범위(390 라이트, 제목 포함, 검색어 '시스템', 상세는 bids[0])의 누락 수.
누락 0이면 종료 코드 0.
"""
import argparse
import json
import os
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_harness as H  # noqa: E402

SCENES = ("latest", "prespec", "org", "org-kdb", "search", "bid", "pdet")
TITLE_SEL = ".b2, .dt-t"
JS = """(titleSel) => {const out={}; const ex={};
 for (const el of document.querySelectorAll('body *')) { if (el.closest('[aria-hidden=true]')) continue;
  let own=''; for (const n of el.childNodes) if (n.nodeType===3) own+=n.textContent; own=own.trim(); if (!/\\d/.test(own)) continue;
  const cs=getComputedStyle(el); if (cs.display==='none' || el.offsetParent===null && cs.position!=='fixed') continue;
  if (cs.fontVariantNumeric.includes('tabular-nums')) continue;
  const k=el.tagName.toLowerCase()+'.'+[...el.classList].join('.')+' < '+(el.parentElement.className||el.parentElement.tagName);
  const bag = titleSel && el.closest(titleSel) ? ex : out; bag[k]=(bag[k]||0)+1; }
 return {miss: out, title: ex}; }"""


def run(docs):
    d = H.data(docs)
    srv, base = H.serve(docs)
    res = {"docs": docs, "cells": {}, "pm": {}}
    with sync_playwright() as p:
        br = p.chromium.launch()
        for vname in H.VIEWS:
            for scheme in H.SCHEMES:
                ctx = H.new_context(br, vname, scheme)
                for sc in SCENES:
                    pg = H.open_scene(ctx, base, sc, d)
                    r = pg.evaluate(JS, TITLE_SEL)
                    res["cells"]["%s-%s-%s" % (vname, scheme, sc)] = r
                    H.close_scene(pg)
                ctx.close()
        # PM 원 스크립트와 같은 범위(390, 라이트, 제목 포함)
        ctx = br.new_context(viewport=H.VIEWS["m"])
        for name, h in [("#/latest", "#/latest"), ("#/prespec", "#/prespec"), ("#/org", "#/org"), ("#/org/kdb", "#/org/kdb"),
                        ("#/search?q=시스템", "#/search?q=시스템"), ("detail", "#/bid/" + d["bids"][0]["key"])]:
            pg = ctx.new_page()
            pg.goto(base.split("?")[0] + h)
            pg.wait_for_timeout(800)
            r = pg.evaluate(JS, "")
            res["pm"][name] = sum(r["miss"].values())
            H.close_scene(pg)
        br.close()
    srv.shutdown()
    res["missing_total"] = sum(sum(v["miss"].values()) for v in res["cells"].values())
    res["title_excluded_total"] = sum(sum(v["title"].values()) for v in res["cells"].values())
    res["pm_total"] = sum(res["pm"].values())
    agg = {}
    for v in res["cells"].values():
        for k, n in v["miss"].items():
            agg[k] = agg.get(k, 0) + n
    res["missing_by_selector"] = dict(sorted(agg.items(), key=lambda x: -x[1]))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default=H.DOCS)
    ap.add_argument("--out")
    a = ap.parse_args()
    res = run(os.path.abspath(a.docs))
    if a.out:
        json.dump(res, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("tnum 누락(제목 제외, 28칸 합계):", res["missing_total"], "| PM 범위(390 라이트 6화면, 제목 포함):", res["pm_total"], res["pm"])
    for k, n in list(res["missing_by_selector"].items())[:25]:
        print("  %4d  %s" % (n, k))
    return 0 if res["missing_total"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
