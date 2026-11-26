"""V-T1 정적 시험(2b-T, t_9ebf54c4) — TDS 3.1 토큰 규칙. 표준 라이브러리만.

  /usr/bin/python3 -m unittest discover -s tests -p 'test_*.py'

app.css: 토큰 정의 블록(:root·다크) 밖 HEX·rgba 0 · #000/#000000/black 0 · font-size px 0 · radius 허용 단계만.
app.js: 인라인 style= 0. 그 밖에 HEX 값 ⊂ DESIGN.md 토큰, 다크 두 블록 동일, 탭바 그림자 = shadow-md, z-index 단계.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSS = open(os.path.join(ROOT, "docs", "assets", "app.css"), encoding="utf-8").read()
JS = open(os.path.join(ROOT, "docs", "assets", "app.js"), encoding="utf-8").read()
HTML = open(os.path.join(ROOT, "docs", "index.html"), encoding="utf-8").read()
DESIGN_MD = os.path.expanduser("~/projects/DesignSystem-RE/toss/DESIGN.md")
# DESIGN.md v3.1 §2.1·2.2·2.3 HEX 중 이 보드가 쓰는 값(DESIGN.md가 없을 때의 기준 — 있으면 원문에서 다시 확인)
DESIGN_HEX = {"#F9FAFB", "#F2F4F6", "#E5E8EB", "#D1D6DB", "#B0B8C1", "#8B95A1", "#6B7684", "#4E5968", "#333D4B", "#191F28",
              "#1C1E22", "#24262B", "#33373D", "#4A4F57", "#626870", "#7E858E", "#9EA5AE", "#C3C8CE", "#E4E6EA", "#FFFFFF",
              "#E8F3FF", "#3182F6", "#1B64DA", "#1957C2", "#1C4989", "#1C2331", "#8FC7FF",
              "#FFEEEE", "#F04452", "#2A2023", "#DC2E47", "#171719", "#202022", "#2C2C30"}
RADIUS_OK = {0, 4, 6, 8, 12, 16, 20, 24, 28, 9999}
HEX_RE = re.compile(r"#[0-9A-Fa-f]{3,8}\b")


def strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def token_blocks(css):
    """선택자가 :root로 시작하는 규칙 블록(라이트·다크 정의)의 (선택자, 본문) 목록."""
    out = []
    for m in re.finditer(r"(:root[^{]*)\{([^{}]*)\}", strip_comments(css)):
        out.append((m.group(1).strip(), m.group(2)))
    return out


def outside_tokens(css):
    return re.sub(r":root[^{]*\{[^{}]*\}", "", strip_comments(css))


def decls(body):
    return dict((k.strip(), v.strip()) for k, v in (d.split(":", 1) for d in body.split(";") if ":" in d))


class TdsStaticTest(unittest.TestCase):
    def test_no_hex_or_rgba_outside_token_blocks(self):
        rest = outside_tokens(CSS)
        self.assertEqual(HEX_RE.findall(rest), [])
        self.assertEqual(re.findall(r"rgba?\(", rest), [])

    def test_no_pure_black(self):
        c = strip_comments(CSS).lower()
        self.assertEqual(re.findall(r"#000(?:000)?\b", c), [])
        self.assertEqual(re.findall(r"\bblack\b", c), [])
        self.assertEqual(re.findall(r"#000(?:000)?\b", JS), [])

    def test_no_px_font_size_outside_tokens(self):
        rest = outside_tokens(CSS)
        self.assertEqual(re.findall(r"font-size\s*:\s*\d+(?:\.\d+)?px", rest), [])
        self.assertEqual(re.findall(r"font\s*:\s*[^;}]*\d+px", rest), [])
        # 토큰 정의는 있어야 한다(§3.3 t1~t7)
        root = decls(token_blocks(CSS)[0][1])
        self.assertEqual([root["--t%d" % i] for i in range(1, 8)], ["30px", "26px", "22px", "20px", "17px", "15px", "13px"])

    def test_radius_steps_only(self):
        bad = []
        for v in re.findall(r"border-radius\s*:\s*([^;}]+)", strip_comments(CSS)):
            for n in re.findall(r"(\d+(?:\.\d+)?)px|(?<![\w.])(0)(?![\w.])", v):
                x = float(n[0] or n[1])
                if x not in RADIUS_OK:
                    bad.append(v)
        self.assertEqual(bad, [])

    def test_js_has_no_inline_style(self):
        self.assertEqual(re.findall(r"style\s*=", JS), [])
        self.assertEqual(HEX_RE.findall(JS), [])

    def test_html_has_no_inline_style_or_hex(self):
        body = HTML.split("<body>", 1)[1]
        self.assertEqual(re.findall(r"style\s*=", body), [])
        self.assertEqual(HEX_RE.findall(HTML), [])

    def test_hex_values_are_design_tokens(self):
        allowed = set(DESIGN_HEX)
        if os.path.exists(DESIGN_MD):
            with open(DESIGN_MD, encoding="utf-8") as f:
                md = {h.upper() for h in HEX_RE.findall(f.read())}
            self.assertTrue(DESIGN_HEX <= md, sorted(DESIGN_HEX - md))
            allowed = md
        used = {h.upper() for h in HEX_RE.findall(strip_comments(CSS))}
        self.assertEqual(sorted(used - allowed), [])

    def test_dark_blocks_identical_and_match_d_b1(self):
        blocks = token_blocks(CSS)
        dark = [decls(b) for s, b in blocks if s != ":root"]
        self.assertEqual(len(dark), 2)
        self.assertEqual(dark[0], dark[1])
        d = dark[0]
        self.assertEqual((d["--surface-canvas"], d["--surface-floated100"], d["--surface-floated200"]), ("#171719", "#202022", "#2C2C30"))
        self.assertEqual(d["--adaptive-grey900"], "#FFFFFF")
        self.assertEqual(d["--color-bg-sheet"], "var(--surface-floated200)")

    def test_naming_matches_sister_board(self):
        root = decls(token_blocks(CSS)[0][1])
        for i in (50, 100, 200, 300, 400, 500, 600, 700, 800, 900):
            self.assertIn("--adaptive-grey%d" % i, root)
        for k in ("--adaptive-blue50", "--adaptive-blue500", "--adaptive-blue600", "--adaptive-blue700", "--adaptive-red50",
                  "--adaptive-red500", "--surface-default", "--surface-canvas", "--surface-floated100", "--surface-floated200", "--dim"):
            self.assertIn(k, root)
        # 컴포넌트 규칙은 --adaptive-*/--surface-*를 직접 쓰지 않고 의미 변수(--color-*)만 참조
        rest = outside_tokens(CSS)
        self.assertEqual(re.findall(r"var\(--(?:adaptive|surface)-[^)]*\)", rest), [])
        old = re.findall(r"var\(--(?:ink2?|meta|metaC|ph|chip|chipInk|sel|selInk|line|accent|accentBg|fill|pressed|nav|navOn|navOff|navPill|card|canvas)\)", CSS)
        self.assertEqual(old, [])

    def test_tabbar_shadow_md_and_inverse_surface(self):
        root = decls(token_blocks(CSS)[0][1])
        self.assertEqual(root["--shadow-md"], "0 8px 24px rgba(25,31,40,0.08)")
        self.assertRegex(CSS, r"\.nav\{[^}]*box-shadow:var\(--shadow-md\)")
        self.assertEqual((root["--color-nav-bg"], root["--color-nav-on"]), ("var(--adaptive-grey900)", "var(--surface-default)"))
        dark = decls([b for s, b in token_blocks(CSS) if s != ":root"][0])
        self.assertEqual((dark["--color-nav-bg"], dark["--color-nav-on"]), ("#F2F4F6", "#191F28"))

    def test_z_index_scale(self):
        root = decls(token_blocks(CSS)[0][1])
        self.assertEqual([root[k] for k in ("--z-gnb", "--z-cta", "--z-sheet", "--z-modal")], ["100", "200", "500", "700"])
        self.assertEqual(re.findall(r"z-index\s*:\s*\d", outside_tokens(CSS)), [])

    def test_no_new_gradient_or_brand_font(self):
        c = strip_comments(CSS)
        self.assertNotIn("gradient(", c)
        self.assertNotIn("Toss Product Sans", c + HTML)
        self.assertIn("Pretendard", c)

    def test_bottom_cta_and_states_present(self):
        self.assertIn('class="cta"', JS)
        self.assertRegex(CSS, r"\.cta>\*\{[^}]*height:56px[^}]*border-radius:16px")
        self.assertIn("st-error", JS)
        self.assertIn('data-act="retry"', JS)
        self.assertIn("st-empty", JS)
        self.assertEqual(HTML.count('class="sk-row"'), 6)
        self.assertRegex(CSS, r"@keyframes sk")

    def test_card_rows_have_no_divider(self):
        self.assertNotRegex(outside_tokens(CSS), r"\.xa-bid[^{]*\{[^}]*border-top")
        self.assertNotRegex(outside_tokens(CSS), r"inset 0 0 0 1px")

    def test_cache_bust_updated(self):
        v = re.findall(r"app\.(?:css|js)\?v=(\w+)", HTML)
        self.assertEqual(len(v), 2)
        self.assertEqual(v[0], v[1])
        self.assertNotEqual(v[0], "20261125b")


if __name__ == "__main__":
    unittest.main()
