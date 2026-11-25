/* fin-bid-board — 바닐라 JS(빌드 없음). data/bids.json(fbw export, 공개 필드만)을 읽어
   최신 공고(게시일 묶음) · 기관별 · 검색을 그린다. 구현 기준 = 시안 t_7445582f A-compact.
   라우트: #/latest · #/prespec[/<no>] · #/org[/<id>] · #/search[?q=…] · #/bid/<key>
   사전규격(prespecs[])은 '최신 사전규격' 탭에만 — 기관별·검색에는 넣지 않는다(대표님 결정 2026-11-25).
   D-day는 브라우저가 KST(UTC+9) 기준으로 매번 계산한다. 담당자명·원문(raw)·첨부파일은 다루지 않는다. */
(function () {
  "use strict";
  // 주제 칩 표시 순서(v2, 10개). bids.json `topics`가 있으면 그것을 우선 쓴다.
  var TOPICS_BUILTIN = ["ISP·ISMP·컨설팅", "AI·데이터", "회계·세무자문", "연구용역", "감리", "구축·개발",
    "유지보수", "운영·위탁", "회선·인프라", "기타"];
  var TOPICS = TOPICS_BUILTIN;
  var STATUS = [{ id: "all", label: "전체" }, { id: "open", label: "진행 중" }, { id: "closed", label: "마감" }, { id: "rev", label: "취소·정정" }];
  var SECTORS = [
    { name: "정책·국책은행", ids: ["kdb", "ibk", "kexim", "bok"] },
    { name: "보증·보험", ids: ["kodit", "hf", "kdic", "kibo"] },
    { name: "자산관리·서민금융", ids: ["kamco", "kinfa"] },
    { name: "투자·감독", ids: ["kic", "fss"] }
  ];
  var ABBR = { kdb: "산은", ibk: "기은", kexim: "수은", bok: "한은", kdic: "예보", kodit: "신보", kibo: "기보", hf: "주금", kamco: "캠코", kinfa: "서금", kic: "KIC", fss: "금감" };
  var DOW = ["일", "월", "화", "수", "목", "금", "토"];
  var NOTE = "나라장터(조달청) 공개 공고를 자동 수집해 정리했습니다 · 정확한 내용은 나라장터 원문을 확인해 주세요";
  var D = null, BY = {}, PBY = {}, app = document.getElementById("app"), sheetEl = document.getElementById("sheet");
  var S = { months: 1, sMonths: 3, st: "all", tp: "", ost: "all", otp: "", sst: "all", q: "", pc: false, ptp: "", base: null, inApp: false };
  var mq = window.matchMedia("(min-width:1024px)");

  // ── 유틸 ───────────────────────────────────────────────────────
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function ms(name, fill) { return '<span class="ms' + (fill ? " f" : "") + '" aria-hidden="true">' + name + "</span>"; }
  function desk() { return mq.matches; }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function num(n) { return Number(n).toLocaleString("ko-KR"); }
  // KST 현재 시각 "YYYY-MM-DD HH:MM" (시험용 ?now=YYYY-MM-DDTHH:MM 지원)
  function nowKst() {
    var m = /[?&]now=(\d{4}-\d\d-\d\dT\d\d:\d\d)/.exec(location.search);
    if (m) return m[1].replace("T", " ");
    var d = new Date(Date.now() + 9 * 3600 * 1000);
    return d.getUTCFullYear() + "-" + pad(d.getUTCMonth() + 1) + "-" + pad(d.getUTCDate()) + " " + pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes());
  }
  function dayNum(ymd) { return Date.UTC(+ymd.slice(0, 4), +ymd.slice(5, 7) - 1, +ymd.slice(8, 10)) / 86400000; }
  function mmdd(s) { return s ? s.slice(5, 7) + "." + s.slice(8, 10) : ""; }
  function mdhm(s) { return s ? mmdd(s) + " " + s.slice(11, 16) : ""; }
  function dateHead(ymd) {
    var w = new Date(Date.UTC(+ymd.slice(0, 4), +ymd.slice(5, 7) - 1, +ymd.slice(8, 10))).getUTCDay();
    return (+ymd.slice(5, 7)) + "월 " + (+ymd.slice(8, 10)) + "일 (" + DOW[w] + ")";
  }
  // 달력 기준 N개월 전 같은 날(말일 보정) — fbw export와 같은 규칙
  function cutoff(today, months) {
    var y = +today.slice(0, 4), m = +today.slice(5, 7) - months, d = +today.slice(8, 10);
    while (m < 1) { m += 12; y -= 1; }
    var last = new Date(Date.UTC(y, m, 0)).getUTCDate();
    return y + "-" + pad(m) + "-" + pad(Math.min(d, last));
  }
  function amtShort(n) {
    if (n == null || n === "") return "–";
    return n >= 1e8 ? (n / 1e8).toFixed(2) + "억" : num(Math.round(n / 1e4)) + "만";
  }
  function amtFull(n) {
    if (n == null || n === "") return "–";
    var man = Math.round(n / 1e4), eok = Math.floor(man / 1e4), rest = man % 1e4;
    if (!man) return num(n) + "원";
    return (eok ? eok + "억" : "") + (eok && rest ? " " : "") + (rest ? num(rest) + "만" : "") + "원";
  }
  function hl(text, q) {
    text = String(text || "");
    if (!q) return esc(text);
    var lo = text.toLowerCase(), ql = q.toLowerCase(), out = "", i = 0, j;
    while ((j = lo.indexOf(ql, i)) >= 0) {
      out += esc(text.slice(i, j)) + '<span class="hl">' + esc(text.slice(j, j + q.length)) + "</span>";
      i = j + q.length;
    }
    return out + esc(text.slice(i));
  }

  // ── 상태 계산 ───────────────────────────────────────────────────
  // 취소 = 취소공고 · 마감 = 마감일시 지남 · 진행 중 = 그 밖(마감일 미표시 포함) · 취소·정정 = 취소공고 + 변경공고
  function info(b, now) {
    var cancel = b.status === "취소공고", closed = !cancel && !!b.closes && b.closes.slice(0, 16) < now;
    var dd = b.closes ? dayNum(b.closes) - dayNum(now) : null;
    return { cancel: cancel, closed: closed, open: !cancel && !closed, rev: cancel || b.status === "변경공고", dd: dd };
  }
  function badge(b, now) {
    var f = info(b, now);
    if (f.cancel) return '<span class="bd c">취소</span>';
    if (!b.closes) return '<span class="bd q">마감일 미표시</span>';
    if (f.closed) return '<span class="bd x">마감</span>';
    return '<span class="bd ' + (f.dd <= 7 ? "u" : "p") + '">' + (f.dd <= 0 ? "D-day" : "D-" + f.dd) + "</span>";
  }
  function dline(b, now) {
    var f = info(b, now);
    if (!b.closes) return "";
    if (f.closed) return '<span class="dl">' + esc(mdhm(b.closes)) + "</span>";
    return '<span class="dl' + (f.cancel ? " o" : "") + '">' + esc(mdhm(b.closes)) + " 마감</span>";
  }
  function inPeriod(list, months, now) {
    var c = cutoff(now.slice(0, 10), months);
    return list.filter(function (b) { return (b.posted || "").slice(0, 10) >= c; });
  }
  function byStatus(list, st, now) {
    if (st === "all") return list;
    return list.filter(function (b) { return info(b, now)[st]; });
  }
  function byTopic(list, tp) { return tp ? list.filter(function (b) { return b.topic === tp; }) : list; }
  function counts(list, now) {
    var c = { all: list.length, open: 0, closed: 0, rev: 0, cancel: 0, noclose: 0 };
    list.forEach(function (b) {
      var f = info(b, now);
      if (f.open) { c.open++; if (!b.closes) c.noclose++; }
      if (f.closed) c.closed++;
      if (f.rev) c.rev++;
      if (f.cancel) c.cancel++;
    });
    return c;
  }
  function match(b, q) {
    var ql = q.toLowerCase();
    return [b.title, b.org, b.dept, b.key].some(function (v) { return String(v || "").toLowerCase().indexOf(ql) >= 0; });
  }
  function orgStats(list, now) {
    var m = {};
    D.orgs.forEach(function (o) { m[o.id] = { n: 0, open: 0, last: "" }; });
    list.forEach(function (b) {
      var s = m[b.org_id] || (m[b.org_id] = { n: 0, open: 0, last: "" });
      s.n++; if (info(b, now).open) s.open++;
      if ((b.posted || "") > s.last) s.last = b.posted;
    });
    return m;
  }
  function sectors() {
    var seen = {}, out = SECTORS.map(function (s) {
      var ids = s.ids.filter(function (id) { return D.orgs.some(function (o) { return o.id === id; }); });
      ids.forEach(function (id) { seen[id] = 1; });
      return { name: s.name, ids: ids };
    });
    var rest = D.orgs.filter(function (o) { return !seen[o.id]; }).map(function (o) { return o.id; });
    if (rest.length) out.push({ name: "기타 기관", ids: rest });
    return out.filter(function (s) { return s.ids.length; });
  }
  function orgName(id) { var o = D.orgs.filter(function (x) { return x.id === id; })[0]; return o ? o.name : id; }
  function orgOrder(id) { for (var i = 0; i < D.orgs.length; i++) if (D.orgs[i].id === id) return i; return 99; }
  function sectorOf(id) { var s = sectors().filter(function (x) { return x.ids.indexOf(id) >= 0; })[0]; return s ? s.name : ""; }
  function updated() { var g = D.generated_at || ""; return g ? "갱신 " + g.slice(5, 7) + "/" + g.slice(8, 10) + " " + g.slice(11, 16) : ""; }

  // ── 조각 ───────────────────────────────────────────────────────
  function themeBtn(extra) {
    return '<button class="thm tap' + (extra || "") + '" type="button" data-act="theme" aria-label="화면 테마 바꾸기">' + ms(isDark() ? "light_mode" : "dark_mode") + "</button>";
  }
  function ddBtn(which) {
    var m = which === "s" ? S.sMonths : S.months;
    return '<button class="dd tap" type="button" data-act="period" data-w="' + which + '" aria-haspopup="dialog">최근 ' + m + "개월" + ms("expand_more") + "</button>";
  }
  function statusChips(c, cur, key, withCount) {
    return '<div class="chips" role="group" aria-label="상태">' + STATUS.map(function (s) {
      return '<button type="button" class="c tap' + (s.id === cur ? " on" : "") + '" data-act="chip" data-k="' + key + '" data-v="' + s.id + '" aria-pressed="' + (s.id === cur) + '">' +
        s.label + (withCount ? " <i>" + c[s.id] + "</i>" : "") + "</button>";
    }).join("") + "</div>";
  }
  // list = 현재 기간·상태 필터를 거친 목록. 0건 주제도 칩을 유지하고 건수 0을 표시한다.
  function topicChips(cur, key, list) {
    var n = {};
    (list || []).forEach(function (b) { var t = b.topic || "기타"; n[t] = (n[t] || 0) + 1; });
    return '<div class="chips" role="group" aria-label="주제"><span class="lb">주제</span>' + TOPICS.map(function (t) {
      return '<button type="button" class="c tap' + (t === cur ? " on" : "") + '" data-act="chip" data-k="' + key + '" data-v="' + esc(t) + '" aria-pressed="' + (t === cur) + '">' +
        esc(t) + " <i>" + (n[t] || 0) + "</i></button>";
    }).join("") + "</div>";
  }
  function topicList(d) {
    var out = (Array.isArray(d.topics) && d.topics.length ? d.topics : TOPICS_BUILTIN).filter(function (t) { return typeof t === "string" && t; });
    (d.bids || []).forEach(function (b) { var t = b.topic || "기타"; if (out.indexOf(t) < 0) out.push(t); });  // 목록 밖 주제도 칩 노출
    return out;
  }
  function card(b, now, q) {
    var f = info(b, now), title = hl(b.title, q);
    if (f.cancel) title = '<s class="cx">' + title + "</s>";
    var og = '<span class="og"><b>' + hl(b.org, q) + "</b>" + (b.dept ? " · " + hl(b.dept, q) : "") + "</span>";
    var dln = '<span class="dln">' + badge(b, now) + dline(b, now) + "</span>";
    var am = '<span class="am"><small>배정</small>' + esc(amtShort(b.budget)) + "</span>";
    return '<a class="xa-bid" href="#/bid/' + encodeURIComponent(b.key) + '" data-key="' + esc(b.key) + '">' +
      '<div class="b1">' + og + '<span class="rt">' + dln + am + "</span></div>" +
      '<div class="b2">' + title + "</div>" +
      '<div class="b5">' + dln + am + "</div></a>";
  }
  function grouped(list, now, q) {
    if (!list.length) return '<p class="a-hint">조건에 맞는 공고가 없습니다</p>';
    var g = [], cur = null;
    list.forEach(function (b) {
      var d = (b.posted || "").slice(0, 10);
      if (!cur || cur.d !== d) { cur = { d: d, items: [] }; g.push(cur); }
      cur.items.push(b);
    });
    return g.map(function (x) {
      return '<div class="xa-dt">' + (x.d ? dateHead(x.d) : "게시일 미상") + "<small>" + x.items.length + "건</small></div>" +
        '<div class="xa-card">' + x.items.map(function (b) { return card(b, now, q); }).join("") + "</div>";
    }).join("");
  }
  function plain(list, now) {
    if (!list.length) return '<p class="a-hint">조건에 맞는 공고가 없습니다</p>';
    return '<div class="xa-card" data-list>' + list.map(function (b) { return card(b, now, ""); }).join("") + "</div>";
  }
  function footer() { return '<div class="fn">' + NOTE + "</div>"; }
  function mHead(title, which, meta) {
    return '<div class="xa-mh m-only"><div class="xa-br">금융권 사업공고 보드</div>' + themeBtn() +
      '<div class="xa-mt"><h1>' + esc(title) + "</h1>" + ddBtn(which) + '</div><div class="xa-mm">' +
      meta.map(function (m) { return "<span>" + esc(m) + "</span>"; }).join("") + "</div></div>";
  }
  function pHead(title, which, meta) {
    return '<div class="xa-l1"><h1>' + esc(title) + "</h1>" + ddBtn(which) + '</div><div class="xa-l1c">' +
      meta.map(function (m) { return "<span>" + esc(m) + "</span>"; }).join("") + "</div>";
  }

  // ── 사전규격(시안 t_8ff77dcf A안 + t_6461f479 S-1·S-2) ─────────────
  // 게시중/마감 = 저장값 status(Q-4). D-day = 의견등록마감일시(ddln) 기준, KST 클라이언트 계산.
  // 기간 = 공개일(posted, rls 날짜와 같음 — 마감 건은 rls가 비어 posted만 있음) 기준, S.months 공유.
  function pOpen(p) { return p.status !== "마감"; }
  function pbadge(p, now) {
    if (!pOpen(p) || (p.ddln && p.ddln.slice(0, 16) < now)) return '<span class="bd x">마감</span>';
    if (!p.ddln) return '<span class="bd q">의견마감 미표시</span>';
    var dd = dayNum(p.ddln) - dayNum(now);
    return '<span class="bd ' + (dd <= 7 ? "u" : "p") + '">' + (dd <= 0 ? "D-day" : "D-" + dd) + "</span>";
  }
  function pdline(p, now) {
    if (!p.ddln) return "";
    if (!pOpen(p) || p.ddln.slice(0, 16) < now) return '<span class="dl">' + esc(mdhm(p.ddln)) + "</span>";
    return '<span class="dl">' + esc(mdhm(p.ddln)) + " 의견마감</span>";
  }
  function pcard(p, now) {
    var dln = '<span class="dln">' + pbadge(p, now) + pdline(p, now) + "</span>";
    var am = '<span class="am"><small>배정</small>' + esc(amtShort(p.budget)) + "</span>";
    return '<a class="xa-bid xa-pre" href="#/prespec/' + encodeURIComponent(p.no) + '" data-pre="' + esc(p.no) + '">' +
      '<div class="b1"><span class="og"><span class="pt">사전규격</span><b>' + esc(p.org) + '</b></span><span class="rt">' + dln + am + "</span></div>" +
      '<div class="b2">' + esc(p.title) + "</div>" +
      '<div class="b5">' + dln + am + "</div></a>";
  }
  function pgrouped(list, now) {
    if (!list.length) return '<p class="a-hint">조건에 맞는 사전규격이 없습니다</p>';
    var g = [], cur = null;
    list.forEach(function (p) {
      var d = (p.posted || "").slice(0, 10);
      if (!cur || cur.d !== d) { cur = { d: d, items: [] }; g.push(cur); }
      cur.items.push(p);
    });
    return g.map(function (x) {
      return '<div class="xa-dt">' + (x.d ? dateHead(x.d) + " 공개" : "공개일 미상") + "<small>" + x.items.length + "건</small></div>" +
        '<div class="xa-card">' + x.items.map(function (p) { return pcard(p, now); }).join("") + "</div>";
    }).join("");
  }
  function pcChips(nOpen, nClosed) {
    return '<div class="chips" role="group" aria-label="진행상태"><span class="lb">게시중 ' + nOpen + "건</span>" +
      '<button type="button" class="c tap' + (S.pc ? " on" : "") + '" data-act="pc" aria-pressed="' + S.pc + '">' +
      ms(S.pc ? "check_box" : "check_box_outline_blank", S.pc) + "마감 포함 <i>" + nClosed + "</i></button></div>";
  }
  function viewPre() {
    var now = nowKst(), all = inPeriod(D.prespecs, S.months, now), tl = byTopic(all, S.ptp);
    var nOpen = tl.filter(pOpen).length, nClosed = tl.length - nOpen, allOpen = all.filter(pOpen).length;
    var base = S.pc ? all : all.filter(pOpen), list = byTopic(base, S.ptp), upd = updated();
    var chips = pcChips(nOpen, nClosed) + topicChips(S.ptp, "ptp", base);
    if (!desk()) {
      return mHead("최신 사전규격", "m", ["게시중 " + allOpen + "건 · 일반용역", upd]) +
        '<div class="xa-mc">' + chips + "</div>" + '<div class="xa-ml" data-pre-list>' + pgrouped(list, now) + "</div>" + footer();
    }
    // S-2: 오른쪽 '기관별 게시중' 패널 없이 전체 폭
    return '<div class="xa-pw">' + pHead("최신 사전규격", "m", [D.orgs.length + "개 기관 · 일반용역 게시중 " + allOpen + "건", upd, "D-day는 의견등록 마감 기준"]) +
      '<div class="xa-chips">' + chips + '</div><div data-pre-list>' + pgrouped(list, now) + "</div></div>" + footer();
  }
  function pdetail(p) {
    var now = nowKst(), left = "";
    if (p.ddln && pOpen(p) && p.ddln.slice(0, 16) >= now) {
      var dd = dayNum(p.ddln) - dayNum(now);
      left = dd <= 0 ? "오늘 마감" : dd + "일 남음";
    }
    var link = p.url
      ? '<a class="btn1 tap" href="' + esc(p.url) + '" target="_blank" rel="noopener noreferrer">나라장터에서 보기 ' + ms("open_in_new") + "</a>"
      : '<p class="pn">' + ms("info") + "<span><b>나라장터 › 발주목록</b>에서 사전규격등록번호로 검색</span></p>";
    return '<div class="dt-h">' + pbadge(p, now) + '<span class="pt">사전규격</span><span class="tp">' + esc(p.topic || "기타") + "</span></div>" +
      '<h2 class="dt-t">' + esc(p.title) + "</h2>" +
      '<div class="kv"><span>발주기관</span><b>' + esc(p.org) + "</b></div>" +
      '<div class="kv"><span>배정예산</span><b>' + esc(amtFull(p.budget)) + "</b></div>" +
      '<div class="kv"><span>공개일시</span><b>' + esc(p.rls ? mdhm(p.rls) : mmdd(p.posted) || "–") + "</b></div>" +
      '<div class="kv"><span>의견등록 마감</span><b>' + esc(p.ddln ? mdhm(p.ddln) : "미표시") + (left ? "<small>" + left + "</small>" : "") + "</b></div>" +
      '<div class="kv"><span>진행상태</span><b>' + esc(p.status || "–") + "</b></div>" +
      '<div class="kv"><span>주제</span><b>' + esc(p.topic || "기타") + "</b></div>" +
      '<div class="kv"><span>사전규격등록번호</span><b style="font-variant-numeric:tabular-nums">' + esc(p.no) + "</b></div>" +
      '<div class="kv"><span>입찰공고 연결</span><b>' + (p.bid_linked === "Y" ? "연결됨" : "아직 없음") + "</b></div>" + link +
      '<button type="button" class="btn2 tap" data-act="copy" data-key="' + esc(p.no) + '" data-lab="등록번호 복사">' + ms("content_copy") + "<span>등록번호 복사</span></button>";
  }

  // ── 화면 ───────────────────────────────────────────────────────
  function viewLatest() {
    var now = nowKst(), all = inPeriod(D.bids, S.months, now);
    var c = counts(byTopic(all, S.tp), now), list = byStatus(byTopic(all, S.tp), S.st, now);
    var nOrg = D.orgs.length, upd = updated(), today = mmdd(now);
    if (!desk()) {
      return mHead("최신 사업공고", "m", [all.length + "건 · 진행 중 " + counts(all, now).open, upd]) +
        '<div class="xa-mc">' + statusChips(c, S.st, "st", true) + topicChips(S.tp, "tp", byStatus(all, S.st, now)) + "</div>" +
        '<div class="xa-ml">' + grouped(list, now, "") + "</div>" + footer();
    }
    var os = orgStats(all, now), ids = D.orgs.map(function (o) { return o.id; }).sort(function (a, b) {
      return os[b].n - os[a].n || orgOrder(a) - orgOrder(b);
    });
    var top = ids.slice(0, 6), rest = ids.slice(6), restN = rest.reduce(function (s, id) { return s + os[id].n; }, 0);
    var side = '<aside class="xa-side"><div class="xa-st"><b>기관별 건수</b><small>최근 ' + S.months + "개월</small></div>" +
      top.map(function (id) {
        return '<a class="xa-or' + (os[id].n ? "" : " off") + '" href="#/org/' + id + '"><b>' + esc(orgName(id)) + "</b><span>" + os[id].n + "<small>건</small></span></a>";
      }).join("") +
      (rest.length ? '<a class="xa-or off" href="#/org"><b>외 ' + rest.length + "개 기관</b><span>" + restN + "<small>건</small></span></a>" : "") +
      '<a class="xa-more tap" href="#/org">기관별로 보기</a></aside>';
    return '<div class="xa-wrap"><div>' + pHead("최신 사업공고", "m", [nOrg + "개 기관 · 일반용역 " + all.length + "건", upd, "D-day는 오늘(" + today + ") 기준"]) +
      '<div class="xa-chips">' + statusChips(c, S.st, "st", true) + topicChips(S.tp, "tp", byStatus(all, S.st, now)) + "</div>" +
      grouped(list, now, "") + "</div>" + side + "</div>" + footer();
  }
  function orgList(all, now, selId) {
    var os = orgStats(all, now);
    return '<div class="xa-orgs">' + sectors().map(function (s) {
      var ids = s.ids.slice().sort(function (a, b) { return os[b].n - os[a].n || orgOrder(a) - orgOrder(b); });
      var n = ids.reduce(function (t, id) { return t + os[id].n; }, 0);
      return '<div class="xa-card"><div class="xa-st"><b>' + esc(s.name) + "</b><small>" + n + "건</small></div>" +
        ids.map(function (id) {
          var st = os[id], off = !st.n;
          return '<a class="xa-co tap' + (off ? " off" : "") + (id === selId ? " sel" : "") + '" href="#/org/' + id + '"' + (id === selId ? ' aria-current="true"' : "") + ">" +
            '<span class="xa-av">' + esc(ABBR[id] || orgName(id).slice(0, 2)) + "</span>" +
            '<div class="tx"><b>' + esc(orgName(id)) + "</b><span>" +
            (off ? "최근 " + S.months + "개월 공고 없음" : "진행 중 " + st.open + " · 최근 " + mmdd(st.last) + " 게시") + "</span></div>" +
            '<span class="ct">' + st.n + "<small>건</small></span>" + ms("chevron_right") + "</a>";
        }).join("") + "</div>";
    }).join("") + "</div>";
  }
  function orgSummary(list, now) {
    var c = counts(list, now);
    return '<div class="xa-sum"><b>' + c.all + "건</b><span>진행 중 " + c.open + (c.noclose ? " (마감일 미표시 " + c.noclose + " 포함)" : "") +
      "</span><span>마감 " + c.closed + "</span>" + (c.cancel ? "<span>취소 " + c.cancel + "</span>" : "") + "</div>";
  }
  function viewOrg(id) {
    var now = nowKst(), all = inPeriod(D.bids, S.months, now), upd = updated();
    var nSec = sectors().length;
    if (id && !D.orgs.some(function (o) { return o.id === id; })) id = null;
    if (!desk()) {
      if (!id) {
        return mHead("기관별", "m", [D.orgs.length + "개 기관 · " + all.length + "건", upd]) + orgList(all, now, null) + footer();
      }
      var ol = all.filter(function (b) { return b.org_id === id; });
      var fl = byStatus(byTopic(ol, S.otp), S.ost, now);
      return '<div class="xa-top"><a class="bk tap" href="#/org">' + ms("arrow_back_ios_new") + "<span>기관별</span></a><span class=\"sp\"></span>" + themeBtn() + "</div>" +
        '<div class="xa-oh"><div class="xa-mt"><h1>' + esc(orgName(id)) + "</h1>" + ddBtn("m") + '</div><div class="xa-mm" style="margin-bottom:6px"><span>' +
        esc(sectorOf(id)) + "</span><span>" + esc(upd) + "</span></div>" + orgSummary(ol, now) + "</div>" +
        '<div class="xa-mc">' + statusChips(null, S.ost, "ost", false) + topicChips(S.otp, "otp", byStatus(ol, S.ost, now)) + "</div>" +
        '<div class="xa-ml" style="padding-top:8px">' + plain(fl, now) + "</div>" + footer();
    }
    if (!id) {
      var os = orgStats(all, now);
      id = D.orgs[0].id;
      sectors().some(function (s) {
        var ids = s.ids.filter(function (x) { return os[x].n; }).sort(function (a, b) { return os[b].n - os[a].n || orgOrder(a) - orgOrder(b); });
        if (ids.length) { id = ids[0]; return true; } return false;
      });
    }
    var l = all.filter(function (b) { return b.org_id === id; });
    var f2 = byStatus(byTopic(l, S.otp), S.ost, now);
    return pHead("기관별 사업공고", "m", [D.orgs.length + "개 기관 · " + nSec + "개 업권 · " + all.length + "건", upd]) +
      '<div class="xa-og"><div>' + orgList(all, now, id) + "</div><div>" +
      '<div class="xa-on">' + esc(orgName(id)) + '</div><div class="xa-oh">' + orgSummary(l, now) + "</div>" +
      '<div class="xa-chips">' + statusChips(null, S.ost, "ost", false) + topicChips(S.otp, "otp", byStatus(l, S.ost, now)) + "</div>" +
      plain(f2, now) + "</div></div>" + footer();
  }
  function searchResults() {
    var now = nowKst(), q = S.q.trim();
    if (!q) return '<p class="a-hint">공고명 · 기관 · 발주부서 · 공고번호로 찾아요</p>';
    var hit = inPeriod(D.bids, S.sMonths, now).filter(function (b) { return match(b, q); });
    var list = byStatus(hit, S.sst, now);
    return '<div class="xa-ms" data-count="' + list.length + '">‘' + esc(q) + "’ <b>" + list.length + "건</b> · 최근 " + S.sMonths + "개월 · 게시일 최신순</div>" +
      '<div class="xa-ml">' + grouped(list, now, q) + "</div>";
  }
  function viewSearch() {
    var box = '<label class="srch">' + ms("search") + '<span class="sr">검색어</span><input id="q" type="search" placeholder="공고명 · 기관 · 공고번호" autocomplete="off" value="' + esc(S.q) + '">' +
      '<button type="button" class="cl" data-act="clear" aria-label="검색어 지우기"' + (S.q ? "" : " hidden") + ">" + ms("cancel", true) + "</button></label>";
    var chips = '<div class="xa-mc">' + statusChips(null, S.sst, "sst", false) + "</div>";
    if (!desk()) {
      return mHead("검색", "s", [D.orgs.length + "개 기관 · 공고명 · 기관 · 공고번호"]) + box + chips +
        '<div id="sr">' + searchResults() + "</div>" + footer();
    }
    return pHead("검색", "s", [D.orgs.length + "개 기관 · 공고명 · 기관 · 발주부서 · 공고번호", updated()]) + box +
      '<div class="xa-chips">' + statusChips(null, S.sst, "sst", false) + "</div>" +
      '<div id="sr">' + searchResults() + "</div>" + footer();
  }

  // ── 상세(시트·모달) ─────────────────────────────────────────────
  function detail(b) {
    var now = nowKst(), rel = (b.related || []).map(function (k) { return BY[k] || { key: k }; });
    var hist = [b].concat(rel).map(function (x, i) {
      var cur = i === 0;
      return '<li class="' + (cur ? "" : "o") + '"><i></i><div><b>' + esc(x.key) + (x.status ? " · " + esc(x.status) : "") + "</b>" +
        (cur ? '<span class="bd p">현재</span>' : "") + "<small>" + (x.posted ? esc(mdhm(x.posted)) + " 게시" : "보드 기간 밖 차수") + "</small></div></li>";
    }).join("");
    var tp = esc(b.topic || "기타") + (b.status && b.status !== "등록공고" ? " · " + esc(b.status) : "");
    return '<div class="dt-h">' + badge(b, now) + '<span class="tp">' + tp + "</span></div>" +
      '<h2 class="dt-t">' + (info(b, now).cancel ? '<s class="cx">' + esc(b.title) + "</s>" : esc(b.title)) + "</h2>" +
      '<div class="kv"><span>발주기관</span><b>' + esc(b.org) + "</b></div>" +
      '<div class="kv"><span>발주부서</span><b>' + esc(b.dept || "–") + "</b></div>" +
      '<div class="kv"><span>배정 · 추정</span><b>배정 ' + esc(amtFull(b.budget)) + "<small>추정 " + esc(amtFull(b.est)) + "</small></b></div>" +
      '<div class="kv"><span>낙찰방법</span><b>' + esc(b.award || "–") + "</b></div>" +
      '<div class="kv"><span>게시 → 마감</span><b>' + esc(mdhm(b.posted) || "–") + " → " + esc(b.closes ? mdhm(b.closes) : "마감일 미표시") + "</b></div>" +
      '<div class="kv"><span>공고번호</span><b style="font-variant-numeric:tabular-nums">' + esc(b.key) + "</b></div>" +
      '<div class="hh">차수 이력 <small>' + (rel.length ? (rel.length + 1) + "건 연결" : "연결된 차수 없음") + '</small></div><ul class="hist">' + hist + "</ul>" +
      (b.url ? '<a class="btn1 tap" href="' + esc(b.url) + '" target="_blank" rel="noopener noreferrer">나라장터에서 보기 ' + ms("open_in_new") + "</a>" : "") +
      '<button type="button" class="btn2 tap" data-act="copy" data-key="' + esc(b.key) + '">' + ms("content_copy") + "<span>공고번호 복사</span></button>";
  }
  function openDetail(key) {
    var b = BY[key];
    if (!b) { sheetEl.innerHTML = ""; return false; }
    sheetEl.innerHTML = '<div class="scrim" data-act="close"></div><div class="sheet" role="dialog" aria-modal="true" aria-label="공고 상세" tabindex="-1"><div class="hd"></div>' +
      '<button type="button" class="x tap" data-act="close" aria-label="닫기">' + ms("close") + "</button>" + detail(b) + "</div>";
    try { sheetEl.querySelector(".sheet").focus({ preventScroll: true }); } catch (e) { /* 무시 */ }
    return true;
  }
  function openPre(no) {
    var p = PBY[no];
    if (!p) { sheetEl.innerHTML = ""; return false; }
    sheetEl.innerHTML = '<div class="scrim" data-act="close"></div><div class="sheet" role="dialog" aria-modal="true" aria-label="사전규격 상세" tabindex="-1"><div class="hd"></div>' +
      '<button type="button" class="x tap" data-act="close" aria-label="닫기">' + ms("close") + "</button>" + pdetail(p) + "</div>";
    try { sheetEl.querySelector(".sheet").focus({ preventScroll: true }); } catch (e) { /* 무시 */ }
    return true;
  }
  function openPeriod(which) {
    var cur = which === "s" ? S.sMonths : S.months;
    sheetEl.innerHTML = '<div class="scrim" data-act="close"></div><div class="sheet pick" role="dialog" aria-modal="true" aria-label="조회 기간"><div class="hd"></div>' +
      '<button type="button" class="x tap" data-act="close" aria-label="닫기">' + ms("close") + "</button><h4>조회 기간</h4><p class=\"s\">게시일 기준 · 최대 3개월</p>" +
      [1, 3].map(function (m) {
        return '<button type="button" class="opt tap' + (m === cur ? " on" : "") + '" data-act="setp" data-w="' + which + '" data-m="' + m + '"><div class="tx"><b>최근 ' + m + "개월</b><span>" +
          esc(cutoff(nowKst().slice(0, 10), m).replace(/-/g, ".")) + " 이후 게시</span></div>" + (m === cur ? ms("check_circle", true) : "") + "</button>";
      }).join("") + "</div>";
  }
  function closeSheet() {
    var wasBid = /^#\/(bid|prespec)\/./.test(location.hash);
    sheetEl.innerHTML = "";
    if (wasBid) {
      if (S.inApp && history.length > 1) { S.inApp = false; history.back(); }
      else location.hash = S.base || "#/latest";
    }
  }

  // ── 라우팅 ─────────────────────────────────────────────────────
  function parse(hash) {
    var h = hash || location.hash || "#/latest", m;
    if ((m = /^#\/bid\/(.+)$/.exec(h))) return { v: "bid", key: decodeURIComponent(m[1]) };
    if ((m = /^#\/prespec\/([^?]+)$/.exec(h))) return { v: "pdet", no: decodeURIComponent(m[1]) };
    if (/^#\/prespec(?:[?\/]|$)/.test(h)) return { v: "prespec" };
    if ((m = /^#\/org(?:\/([^?\/]+))?/.exec(h))) return { v: "org", id: m[1] ? decodeURIComponent(m[1]) : null };
    if ((m = /^#\/search(?:\?(.*))?$/.exec(h))) {
      var q = ""; (m[1] || "").split("&").forEach(function (kv) { var p = kv.split("="); if (p[0] === "q") q = decodeURIComponent((p[1] || "").replace(/\+/g, " ")); });
      return { v: "search", q: q };
    }
    return { v: "latest" };
  }
  function setTabs(v) {
    [].forEach.call(document.querySelectorAll("[data-tab]"), function (a) {
      var on = a.getAttribute("data-tab") === v;
      a.classList.toggle("on", on);
      if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
      var ic = a.querySelector(".ms");
      if (ic && a.closest(".nav")) ic.classList.toggle("f", on);
    });
  }
  function renderBase(r) {
    if (r.v === "org") app.innerHTML = viewOrg(r.id);
    else if (r.v === "prespec") app.innerHTML = viewPre();
    else if (r.v === "search") { S.q = r.q; app.innerHTML = viewSearch(); }
    else app.innerHTML = viewLatest();
    setTabs(r.v);
    var g = document.getElementById("gnb-q");
    if (g && document.activeElement !== g) g.value = r.v === "search" ? S.q : "";
    document.title = (r.v === "prespec" ? "최신 사전규격 · " : r.v === "org" && r.id ? orgName(r.id) + " · " : r.v === "search" && S.q ? "‘" + S.q + "’ 검색 · " : "") + "금융권 사업공고 보드";
  }
  function render() {
    if (!D) return;
    var r = parse();
    if (r.v === "bid") {
      S.base = S.base || "#/latest";
      renderBase(parse(S.base));
      if (!BY[r.key]) { app.insertAdjacentHTML("afterbegin", '<p class="a-hint">해당 공고를 찾을 수 없습니다(최근 3개월 밖이거나 삭제됨)</p>'); return; }
      openDetail(r.key);
      return;
    }
    if (r.v === "pdet") {                         // 직접 진입이면 바탕 = 최신 사전규격
      S.base = S.base || "#/prespec";
      renderBase(parse(S.base));
      if (!PBY[r.no]) { app.insertAdjacentHTML("afterbegin", '<p class="a-hint">해당 사전규격을 찾을 수 없습니다(최근 3개월 밖이거나 삭제됨)</p>'); return; }
      openPre(r.no);
      return;
    }
    S.base = location.hash || "#/latest";
    sheetEl.innerHTML = "";
    renderBase(r);
  }

  // ── 테마 ───────────────────────────────────────────────────────
  function isDark() {
    var t = document.documentElement.getAttribute("data-theme");
    return t ? t === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  }
  function toggleTheme() {
    var t = isDark() ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem("fbb-theme", t); } catch (e) { /* 저장 불가 무시 */ }
    [].forEach.call(document.querySelectorAll('[data-act="theme"] .ms'), function (x) { x.textContent = t === "dark" ? "light_mode" : "dark_mode"; });
  }

  // ── 이벤트 ─────────────────────────────────────────────────────
  document.addEventListener("click", function (e) {
    var bid = e.target.closest("a.xa-bid");
    if (bid) { S.inApp = true; return; }
    var t = e.target.closest("[data-act]");
    if (!t) return;
    var a = t.getAttribute("data-act");
    if (a === "theme") return toggleTheme();
    if (a === "close") return closeSheet();
    if (a === "period") return openPeriod(t.getAttribute("data-w"));
    if (a === "setp") {
      var m = +t.getAttribute("data-m");
      if (t.getAttribute("data-w") === "s") S.sMonths = m; else S.months = m;
      sheetEl.innerHTML = ""; return render();
    }
    if (a === "chip") {
      var k = t.getAttribute("data-k"), v = t.getAttribute("data-v");
      if (k === "tp" || k === "otp" || k === "ptp") S[k] = S[k] === v ? "" : v; else S[k] = v;
      var y = window.scrollY; render(); window.scrollTo(0, y); return;
    }
    if (a === "pc") { S.pc = !S.pc; var y2 = window.scrollY; render(); window.scrollTo(0, y2); return; }
    if (a === "clear") { S.q = ""; history.replaceState(null, "", "#/search"); render(); var i = document.getElementById("q"); if (i) i.focus(); return; }
    if (a === "copy") {
      var key = t.getAttribute("data-key"), lab = t.querySelector("span:last-child"), lab0 = t.getAttribute("data-lab") || "공고번호 복사";
      var done = function () { if (lab) { lab.textContent = "복사했어요"; setTimeout(function () { lab.textContent = lab0; }, 1500); } };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(key).then(done, done); else done();
    }
  });
  var qTimer = null;
  document.addEventListener("input", function (e) {
    if (e.target.id === "q") {
      S.q = e.target.value;
      clearTimeout(qTimer);
      qTimer = setTimeout(function () {
        history.replaceState(null, "", S.q.trim() ? "#/search?q=" + encodeURIComponent(S.q.trim()) : "#/search");
        S.base = location.hash;
        var sr = document.getElementById("sr"); if (sr) sr.innerHTML = searchResults();
        var cl = document.querySelector(".srch .cl"); if (cl) cl.hidden = !S.q;
      }, 120);
    }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && sheetEl.innerHTML) closeSheet();
    if (e.key === "Enter" && e.target.id === "gnb-q") {
      var v = e.target.value.trim();
      location.hash = v ? "#/search?q=" + encodeURIComponent(v) : "#/search";
      e.target.blur();
    }
  });
  window.addEventListener("hashchange", function () {
    var r = parse();
    if (r.v !== "bid" && r.v !== "pdet") window.scrollTo(0, 0);
    render();
  });
  var onMq = function () { render(); };
  if (mq.addEventListener) mq.addEventListener("change", onMq); else if (mq.addListener) mq.addListener(onMq);

  fetch("data/bids.json", { cache: "no-cache" }).then(function (r) {
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }).then(function (d) {
    D = d; D.orgs = D.orgs || []; TOPICS = topicList(D); D.bids = (D.bids || []).slice().sort(function (a, b) { return a.posted < b.posted ? 1 : a.posted > b.posted ? -1 : 0; });
    D.bids.forEach(function (b) { BY[b.key] = b; });
    // 사전규격: 공개일 → 공개일시 → 등록번호 최신순(마감 건은 rls 없음)
    D.prespecs = (D.prespecs || []).slice().sort(function (a, b) {
      var x = (b.posted || "") + "|" + (b.rls || "0") + "|" + b.no, y = (a.posted || "") + "|" + (a.rls || "0") + "|" + a.no;
      return x < y ? -1 : x > y ? 1 : 0;
    });
    D.prespecs.forEach(function (p) { PBY[p.no] = p; });
    render();
  }).catch(function (e) {
    app.innerHTML = '<p class="a-hint">데이터를 불러오지 못했습니다(' + esc(e.message) + ")</p>";
  });
})();
