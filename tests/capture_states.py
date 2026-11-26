#!/usr/bin/env python3
"""V-T5 전후 캡처(2b-T, t_9ebf54c4).

  /usr/bin/python3 tests/capture_states.py --docs <docs 폴더> --out <캡처 폴더>

라이트·다크 × 390·1280 × (최신 공고·최신 사전규격·기관별·검색·공고 상세·로딩·빈 결과·오류) = 32장.
파일명 `<m|pc>-<light|dark>-<화면>.png` — before(main)와 after(tds31)를 같은 이름으로 찍어 나란히 비교한다.
D-day는 ?now=2026-11-26T18:00 고정. 콘솔 오류(오류 주입 화면 제외)는 <out>/capture.json에 남긴다.
"""
import argparse
import json
import os
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_harness as H  # noqa: E402

SCENES = ("latest", "prespec", "org", "search", "bid", "loading", "empty", "error")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default=H.DOCS)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    docs = os.path.abspath(a.docs)
    d = H.data(docs)
    srv, base = H.serve(docs)
    errs, shots = [], []
    with sync_playwright() as p:
        br = p.chromium.launch()
        for vname in H.VIEWS:
            for scheme in H.SCHEMES:
                ctx = H.new_context(br, vname, scheme)
                for sc in SCENES:
                    e = []
                    pg = H.open_scene(ctx, base, sc, d, errors=e)
                    f = os.path.join(a.out, "%s-%s-%s.png" % (vname, scheme, sc))
                    pg.screenshot(path=f)
                    shots.append(os.path.basename(f))
                    errs += ["%s-%s-%s: %s" % (vname, scheme, sc, x) for x in e]
                    H.close_scene(pg)
                ctx.close()
        br.close()
    srv.shutdown()
    json.dump({"docs": docs, "shots": shots, "console_errors": errs}, open(os.path.join(a.out, "capture.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("캡처 %d장 → %s · 콘솔 오류 %d" % (len(shots), a.out, len(errs)))
    for x in errs[:10]:
        print("  ", x)


if __name__ == "__main__":
    main()
