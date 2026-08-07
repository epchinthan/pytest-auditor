"""
pytest_auditor/html_report.py  v3
Self-contained HTML report — no external CDN.
"""
from __future__ import annotations
from pathlib import Path
from .analyse import SuiteReport


def _sc(score: int) -> str:
    if score >= 85: return "#16a34a"
    if score >= 65: return "#d97706"
    return "#dc2626"

def _badge(level: str) -> str:
    S = {"error":   ("background:#fee2e2;color:#991b1b;border:1px solid #fca5a5", "✖"),
         "warning": ("background:#fef3c7;color:#92400e;border:1px solid #fcd34d", "⚠"),
         "info":    ("background:#dbeafe;color:#1e40af;border:1px solid #93c5fd", "ℹ")}
    st, ic = S.get(level, ("","?"))
    return f'<span style="font-size:11px;font-weight:600;padding:2px 7px;border-radius:4px;{st}">{ic} {level}</span>'

def generate_html(report: SuiteReport, out_path: Path) -> None:
    sc = report.score
    sc_col = _sc(sc)
    cov    = f"{report.coverage_pct:.1f}%" if report.coverage_pct is not None else "—"
    cov_col = ("#16a34a" if (report.coverage_pct or 0) >= 80
               else "#d97706" if (report.coverage_pct or 0) >= 60 else "#dc2626")

    # ── issues rows ───────────────────────────────────────────────────────
    issue_rows = []
    for fr in report.files:
        if not fr.issues: continue
        rel = fr.path.replace(report.root, "").lstrip("/\\") or fr.path
        for i in fr.issues:
            loc = f":{i.line}" if i.line else ""
            issue_rows.append(
                f'<tr>'
                f'<td><code style="font-size:12px">{rel}{loc}</code></td>'
                f'<td>{_badge(i.level)}</td>'
                f'<td><code style="font-size:11px;color:#6b7280">{i.code}</code></td>'
                f'<td style="font-size:13px">{i.message}</td>'
                f'</tr>'
            )
    issues_html = "\n".join(issue_rows) or (
        '<tr><td colspan="4" style="text-align:center;color:#16a34a;padding:20px">✔ No issues</td></tr>'
    )

    # ── file rows ─────────────────────────────────────────────────────────
    file_rows = []
    for fr in report.files:
        if fr.test_count == 0 and fr.fixture_count == 0 and not fr.issues: continue
        rel = fr.path.replace(report.root, "").lstrip("/\\") or fr.path
        ne = sum(1 for i in fr.issues if i.level == "error")
        nw = sum(1 for i in fr.issues if i.level == "warning")
        ni = sum(1 for i in fr.issues if i.level == "info")
        badges = (f'<span style="color:#dc2626;font-weight:600">✖ {ne}</span> ' if ne else "") + \
                 (f'<span style="color:#d97706;font-weight:600">⚠ {nw}</span> ' if nw else "") + \
                 (f'<span style="color:#1e40af">ℹ {ni}</span>' if ni else "")
        bg = "#fee2e2" if ne else "#fef3c7" if nw else "#f0fdf4" if not fr.issues else "#ffffff"
        file_rows.append(
            f'<tr style="background:{bg}">'
            f'<td><code style="font-size:12px">{rel}</code></td>'
            f'<td style="text-align:center">{fr.test_count}</td>'
            f'<td style="text-align:center">{fr.fixture_count}</td>'
            f'<td style="text-align:center">{fr.line_count or "—"}</td>'
            f'<td style="text-align:center">{fr.async_count or "—"}</td>'
            f'<td>{badges or "<span style=\'color:#16a34a\'>✔</span>"}</td>'
            f'</tr>'
        )

    # ── tests rows ────────────────────────────────────────────────────────
    test_rows = []
    for fr in report.files:
        rel = fr.path.replace(report.root, "").lstrip("/\\") or fr.path
        for t in fr.tests:
            marks_html = " ".join(
                f'<span style="font-size:10px;background:#dbeafe;color:#1e40af;'
                f'padding:1px 5px;border-radius:3px">@{m}</span>'
                for m in t.get("marks", [])
            )
            flags = []
            if t.get("issue_no_assert"):   flags.append('<span style="color:#dc2626;font-weight:600">no assert</span>')
            if t.get("issue_many_asserts"):flags.append(f'<span style="color:#d97706">{t["asserts"]} asserts</span>')
            if t.get("issue_loop"):        flags.append('<span style="color:#d97706">loop+assert</span>')
            if t.get("issue_float"):       flags.append('<span style="color:#d97706">float==</span>')
            if t.get("issue_hardpath"):    flags.append('<span style="color:#d97706">/tmp</span>')
            if t.get("issue_fixture_call"):flags.append('<span style="color:#dc2626">fixture called</span>')
            if t.get("issue_sleep"):       flags.append('<span style="color:#d97706">sleep()</span>')
            if t.get("issue_print"):       flags.append('<span style="color:#6b7280">print()</span>')
            if t.get("issue_bare_except"): flags.append('<span style="color:#d97706">bare except</span>')
            if t.get("issue_assert_true"): flags.append('<span style="color:#d97706">assert True</span>')
            if t.get("issue_long_test"):   flags.append('<span style="color:#6b7280">long</span>')
            if t.get("issue_mock_unasserted"): flags.append('<span style="color:#6b7280">mock?</span>')
            if t.get("issue_environ"):     flags.append('<span style="color:#d97706">os.environ</span>')
            if t.get("issue_asyncio_run"): flags.append('<span style="color:#d97706">asyncio.run</span>')
            if t.get("issue_vague_name"):  flags.append('<span style="color:#d97706">vague name</span>')
            row_bg = "#fee2e2" if t.get("issue_no_assert") or t.get("issue_fixture_call") else "#ffffff"
            cls = f"[{t['class']}] " if t.get("class") else ""
            test_rows.append(
                f'<tr style="background:{row_bg}" data-line="{t["line"]}">'
                f'<td><code style="font-size:11px">{rel}:{t["line"]}</code></td>'
                f'<td style="font-size:12px">{cls}<strong>{t["name"]}</strong></td>'
                f'<td style="text-align:center">{t["asserts"]}</td>'
                f'<td style="text-align:center">{t.get("lines","—")}</td>'
                f'<td>{"⚡" if t["async"] else ""}</td>'
                f'<td>{marks_html}</td>'
                f'<td>{" ".join(flags)}</td>'
                f'</tr>'
            )

    # ── fixture rows ──────────────────────────────────────────────────────
    SC_COLORS = {"function":"#dbeafe","class":"#dcfce7","module":"#fef3c7","session":"#f3e8ff"}
    fx_rows = []
    for fr in report.files:
        rel = fr.path.replace(report.root, "").lstrip("/\\") or fr.path
        for fx in fr.fixtures:
            sc_bg = SC_COLORS.get(fx["scope"], "#f3f4f6")
            flags = []
            if fx.get("autouse"): flags.append('<span style="background:#fef3c7;color:#92400e;padding:1px 5px;border-radius:3px;font-size:10px">autouse</span>')
            if not fx.get("yield"): flags.append('<span style="background:#fee2e2;color:#991b1b;padding:1px 5px;border-radius:3px;font-size:10px">return</span>')
            fx_rows.append(
                f'<tr>'
                f'<td><code style="font-size:12px">{rel}:{fx["line"]}</code></td>'
                f'<td><code style="font-size:13px;font-weight:600">{fx["name"]}</code></td>'
                f'<td><span style="background:{sc_bg};padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600">{fx["scope"]}</span></td>'
                f'<td style="text-align:center">{"⚡" if fx["async"] else ""}</td>'
                f'<td style="text-align:center">{fx["bodylen"]}</td>'
                f'<td>{" ".join(flags)}</td>'
                f'</tr>'
            )

    # ── scope chart ───────────────────────────────────────────────────────
    from collections import Counter
    all_fx   = [fx for fr in report.files for fx in fr.fixtures]
    scopes   = Counter(fx["scope"] for fx in all_fx)
    SC_MAP   = {"function":"#1c99c7","class":"#16a34a","module":"#d97706","session":"#7c3aed"}
    total_fx = sum(scopes.values()) or 1
    scope_bars = ""
    for sc_name, cnt in sorted(scopes.items(), key=lambda x: -x[1]):
        pct = cnt / total_fx * 100
        c   = SC_MAP.get(sc_name, "#6b7280")
        scope_bars += (
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
            f'<div style="width:80px;font-size:12px;font-weight:500;color:#374151">{sc_name}</div>'
            f'<div style="flex:1;background:#e5e7eb;border-radius:4px;height:18px">'
            f'<div style="width:{pct:.0f}%;background:{c};height:100%;border-radius:4px;'
            f'display:flex;align-items:center;padding-left:6px">'
            f'<span style="color:white;font-size:11px;font-weight:600">{cnt}</span></div></div>'
            f'<div style="width:32px;font-size:11px;color:#6b7280;text-align:right">{pct:.0f}%</div>'
            f'</div>'
        )

    # ── issues per file chart ─────────────────────────────────────────────
    sorted_files = sorted([f for f in report.files if f.issues], key=lambda x: -len(x.issues))[:10]
    max_iss = max((len(f.issues) for f in sorted_files), default=1)
    issue_chart = ""
    for fr in sorted_files:
        rel = Path(fr.path).name
        n = len(fr.issues)
        ne = sum(1 for i in fr.issues if i.level == "error")
        nw = sum(1 for i in fr.issues if i.level == "warning")
        issue_chart += (
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:5px">'
            f'<div style="width:160px;font-size:11px;color:#374151;overflow:hidden;'
            f'text-overflow:ellipsis;white-space:nowrap" title="{fr.path}">{rel}</div>'
            f'<div style="flex:1;background:#e5e7eb;border-radius:3px;height:16px;display:flex">'
            f'<div style="width:{ne/max_iss*100:.0f}%;background:#dc2626;height:100%;border-radius:3px 0 0 3px"></div>'
            f'<div style="width:{nw/max_iss*100:.0f}%;background:#d97706;height:100%"></div>'
            f'</div><div style="width:24px;font-size:11px;color:#6b7280;text-align:right">{n}</div>'
            f'</div>'
        )

    # ── dir breakdown ─────────────────────────────────────────────────────
    dir_rows = ""
    for d, info in sorted(report.dir_breakdown.items(), key=lambda x: -x[1]["issues"]):
        dir_rows += (
            f'<tr><td><code style="font-size:12px">{d}</code></td>'
            f'<td style="text-align:center">{info["tests"]}</td>'
            f'<td style="text-align:center;color:{"#dc2626" if info["errors"] else "#374151"}">'
            f'{info["errors"] or "—"}</td>'
            f'<td style="text-align:center;color:{"#d97706" if info["issues"] else "#16a34a"}">'
            f'{info["issues"] or "✔"}</td>'
            f'</tr>'
        )

    conftest_list = "".join(
        f'<li style="font-size:12px;margin:2px 0"><code>{p}</code></li>'
        for p in report.conftest_paths
    ) or '<li style="color:#6b7280;font-size:12px">None found</li>'

    marks_list = " ".join(
        f'<span style="background:#dbeafe;color:#1e40af;padding:2px 8px;'
        f'border-radius:12px;font-size:12px;font-weight:500">@{m}</span>'
        for m in report.registered_marks
    ) or '<span style="color:#6b7280;font-size:12px">None registered</span>'

    debt_col = "#dc2626" if report.test_debt_pct > 15 else "#d97706" if report.test_debt_pct > 5 else "#16a34a"
    iso_col  = "#16a34a" if report.isolation_score >= 70 else "#d97706"

    # ── full codes reference ───────────────────────────────────────────────
    CODES = [
        # Test quality
        ("T001","error",  "No assert statements — test proves nothing"),
        ("T002","warning","Too many assertions (>5) — split or use parametrize"),
        ("T003","warning","Loop with assert inside — use @parametrize instead"),
        ("T004","warning","Float compared with == — use pytest.approx()"),
        ("T005","warning","Hardcoded /tmp path — use tmp_path fixture"),
        ("T006","error",  "Fixture called as function instead of declared as parameter"),
        ("T007","info",   "Async test without @pytest.mark.asyncio"),
        ("T008","info",   "@parametrize without readable id= names"),
        ("T009","info",   "@parametrize with only 1 case — use a regular test"),
        ("T010","info",   "@parametrize with >20 cases — consider loading from CSV/JSON"),
        ("T011","warning","time.sleep() in test — mock time instead"),
        ("T012","info",   "print() found — likely debugging code left behind"),
        ("T013","warning","Bare except / except Exception: pass — swallows failures"),
        ("T014","warning","@skip without reason= — document why it's skipped"),
        ("T015","warning","@xfail without reason= — document why it's expected to fail"),
        ("T016","warning","Duplicate test name — silent collection conflict"),
        ("T017","info",   "Test body >30 lines — consider splitting into smaller tests"),
        ("T018","info",   "Multiple pytest.raises in one test — each should be its own test"),
        ("T019","warning","assert True / assert 1==1 — placeholder proves nothing"),
        ("T020","info",   "'assert result' (bare name) — use assert result == expected"),
        ("T021","info",   "assert len(x) > 0 — use assert x or assert x == [expected]"),
        ("T022","info",   "asyncio.sleep(0) — usually unnecessary in tests"),
        ("T023","warning","asyncio.run() inside test — use async def + asyncio_mode='auto'"),
        ("T024","info",   "Parametrize id with spaces/brackets — makes -k filtering awkward"),
        # Mocking
        ("MK01","info",   "Mock patched but no assert_called* — patch may never be verified"),
        ("MK02","info",   "unittest.mock.patch used directly — prefer mocker.patch"),
        ("MK03","info",   "mock.ANY used 3+ times — assertions too permissive"),
        ("MK04","info",   "Direct unittest.mock import — prefer mocker fixture (pytest-mock)"),
        ("MK05","warning","MagicMock()/Mock() at module level — shared between all tests"),
        ("MK06","warning","Patch target has no module path — use 'myapp.module.name'"),
        ("MK07","info",   "Same mock target patched twice — likely copy-paste error"),
        # Naming
        ("N001","warning","File doesn't follow naming convention (test_*.py or *_test.py)"),
        ("N002","warning","Function named check_/verify_ — pytest won't collect it"),
        ("N003","warning","Class doesn't start with Test — tests won't be collected"),
        ("N004","warning","Class inherits from TestCase — pytest fixtures won't inject"),
        ("N005","info",   "Test class with no test methods"),
        ("N006","warning","Vague test name (test_it, test_foo, test_1…)"),
        ("N007","info",   "Numbered test name (test_login1)"),
        # Fixtures
        ("FX01","info",   "Fixture with many statements uses return — consider yield"),
        ("FX02","warning","assert inside fixture — shows as ERROR not FAILED"),
        ("FX03","info",   "Fixture body >30 lines — consider splitting"),
        ("FX04","warning","autouse=True + session scope — affects every test in the run"),
        ("FX05","error",  "Fixture scope mismatch — outer scope < inner scope (ScopeError)"),
        ("FX06","warning","Fixture yields more than once — only first yield is used"),
        ("FX07","info",   "Fixture parameter name shadows a Python builtin"),
        ("FX08","info",   "Fixture name shadows a fixture from a parent conftest.py"),
        ("FX09","info",   "Fixture used by only 1 test — consider inlining the setup"),
        # Suite structure
        ("S001","info",   "No conftest.py in tests root"),
        ("S002","info",   "Test file >200 lines — consider splitting"),
        ("S003","info",   "Test file with no tests or fixtures"),
        ("S004","info",   "No tests have any marks — consider tagging slow/integration"),
        # Organisation
        ("OR08","warning","Same fixture name in multiple conftest.py files — shadows outer"),
        ("OR09","info",   "All tests in classes but no class-scoped fixture — plain functions may be simpler"),
        ("OR10","info",   "No imports from production code — file may not test real logic"),
        ("OR11","info",   "No __init__.py in tests — cross-file imports may fail"),
        ("OR12","info",   "Tests nested >4 directories deep — hard to navigate"),
        # Files
        ("F001","error",  "Syntax error in test file"),
        ("F002","error",  "File cannot be parsed"),
        ("F003","warning","Possible hardcoded credential (password=, token=, api_key=…)"),
        # Safety
        ("SA01","warning","open(..., 'w') with non-tmp path — use tmp_path to avoid residue"),
        ("SA02","warning","os.environ modified directly — use monkeypatch.setenv() instead"),
        # Marks
        ("M001","warning","Unregistered custom mark — add to markers in pyproject.toml"),
    ]

    level_colors = {"error":"#dc2626","warning":"#d97706","info":"#1e40af"}
    codes_rows = "\n".join(
        f'<tr><td style="padding:3px 8px 3px 0"><code>{c}</code></td>'
        f'<td style="color:{level_colors.get(l,"#374151")};font-size:12px">{l}</td>'
        f'<td style="font-size:12px;color:#374151">{desc}</td></tr>'
        for c, l, desc in CODES
    )

    # ── metrics cards ─────────────────────────────────────────────────────
    debt_label = ("Low" if report.test_debt_pct <= 5
                  else "Moderate" if report.test_debt_pct <= 15 else "High")
    iso_label  = ("Good" if report.isolation_score >= 70
                  else "Moderate" if report.isolation_score >= 40 else "Low")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>pytest Audit Report</title>
<style>
* {{ box-sizing:border-box;margin:0;padding:0 }}
body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
        background:#f8fafc;color:#1a2f3a;font-size:14px }}
.header {{ background:#004d65;color:white;padding:20px 32px }}
.header h1 {{ font-size:22px;font-weight:700 }}
.header h1 span {{ color:#1c99c7 }}
.header p {{ color:#93c5fd;font-size:12px;margin-top:4px }}
.subbar {{ background:#1c99c7;padding:6px 32px;font-size:12px;color:#e0f2fe }}
.container {{ max-width:1400px;margin:0 auto;padding:20px }}
.cards {{ display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
          gap:10px;margin-bottom:20px }}
.card {{ background:white;border-radius:10px;padding:14px 18px;
         border:1px solid #e2e8f0;box-shadow:0 1px 4px rgba(0,0,0,.06) }}
.card .val {{ font-size:26px;font-weight:700;color:#004d65 }}
.card .lbl {{ font-size:11px;color:#6b7280;text-transform:uppercase;
              letter-spacing:.05em;margin-top:2px }}
.score-wrap {{ display:flex;align-items:center;gap:14px }}
.score-ring {{ width:84px;height:84px;position:relative;display:inline-block }}
svg.ring {{ transform:rotate(-90deg) }}
.score-num {{ position:absolute;top:50%;left:50%;
              transform:translate(-50%,-50%);font-size:20px;font-weight:800;
              color:{sc_col} }}
section {{ background:white;border-radius:10px;border:1px solid #e2e8f0;
           box-shadow:0 1px 4px rgba(0,0,0,.06);margin-bottom:16px;overflow:hidden }}
.sec-head {{ background:#004d65;color:white;padding:9px 16px;
             font-size:13px;font-weight:600;display:flex;align-items:center;gap:8px }}
.sec-head .cnt {{ background:rgba(255,255,255,.2);padding:1px 8px;
                  border-radius:10px;font-size:11px }}
table {{ width:100%;border-collapse:collapse;font-size:13px }}
th {{ background:#f1f5f9;color:#374151;font-weight:600;font-size:11px;
      text-transform:uppercase;letter-spacing:.04em;
      padding:7px 12px;border-bottom:1px solid #e2e8f0;text-align:left }}
td {{ padding:6px 12px;border-bottom:1px solid #f1f5f9;vertical-align:middle }}
tr:last-child td {{ border-bottom:none }}
tr:hover td {{ background:#f8fafc }}
.tabs {{ display:flex;gap:0;border-bottom:2px solid #e2e8f0;background:#f8fafc }}
.tab {{ padding:9px 18px;font-size:13px;font-weight:500;cursor:pointer;
        border-bottom:2px solid transparent;margin-bottom:-2px;color:#6b7280 }}
.tab.active {{ color:#004d65;border-bottom-color:#1c99c7;font-weight:600 }}
.tab-pane {{ display:none;padding:14px 16px }}
.tab-pane.active {{ display:block }}
.chart-section {{ padding:14px 16px }}
input[type=search] {{ padding:5px 11px;border:1px solid #e2e8f0;border-radius:6px;
                      font-size:13px;width:260px;outline:none }}
input[type=search]:focus {{ border-color:#1c99c7 }}
.filter-bar {{ padding:9px 16px;background:#f8fafc;border-bottom:1px solid #e2e8f0;
               display:flex;gap:8px;align-items:center;flex-wrap:wrap }}
.btn {{ padding:4px 10px;border-radius:5px;cursor:pointer;font-size:12px;
        font-weight:600;border:1px solid }}
.grid2 {{ display:grid;grid-template-columns:1fr 1fr;gap:14px }}
.footer {{ text-align:center;color:#9ca3af;font-size:11px;padding:16px;margin-top:6px }}
</style>
</head>
<body>
<div class="header">
  <h1><span>pytest</span> Audit Report</h1>
  <p>{report.root} · {report.generated_at}</p>
</div>
<div class="subbar">Klarrio · #STREAMINGAHEAD · python -m pytest_auditor &lt;path&gt; or pytest --quality-report</div>

<div class="container">

<!-- stat cards -->
<div class="cards">
  <div class="card">
    <div class="score-wrap">
      <div class="score-ring">
        <svg class="ring" width="84" height="84" viewBox="0 0 84 84">
          <circle cx="42" cy="42" r="35" fill="none" stroke="#e5e7eb" stroke-width="7"/>
          <circle cx="42" cy="42" r="35" fill="none" stroke="{sc_col}" stroke-width="7"
                  stroke-dasharray="{2*3.14159*35*sc/100:.1f} {2*3.14159*35*(100-sc)/100:.1f}"
                  stroke-linecap="round"/>
        </svg>
        <div class="score-num">{sc}</div>
      </div>
      <div>
        <div style="font-size:15px;font-weight:700;color:{sc_col}">
          {'Excellent' if sc>=90 else 'Good' if sc>=80 else 'Needs work' if sc>=65 else 'Poor' if sc>=50 else 'Critical'}
        </div>
        <div style="font-size:11px;color:#6b7280;margin-top:2px">Quality score</div>
      </div>
    </div>
  </div>
  <div class="card"><div class="val">{report.total_tests}</div><div class="lbl">Tests</div></div>
  <div class="card"><div class="val">{report.total_files}</div><div class="lbl">Files</div></div>
  <div class="card"><div class="val">{report.total_fixtures}</div><div class="lbl">Fixtures</div></div>
  <div class="card"><div class="val" style="color:{cov_col}">{cov}</div><div class="lbl">Coverage</div></div>
  <div class="card"><div class="val" style="color:#dc2626">{report.errors}</div><div class="lbl">Errors</div></div>
  <div class="card"><div class="val" style="color:#d97706">{report.warnings}</div><div class="lbl">Warnings</div></div>
  <div class="card"><div class="val" style="color:#1e40af">{report.infos}</div><div class="lbl">Info</div></div>
  <div class="card">
    <div class="val" style="color:{debt_col}">{report.test_debt_pct:.0f}%</div>
    <div class="lbl">Test debt</div>
    <div style="font-size:10px;color:#9ca3af;margin-top:2px">{report.skip_count} skip · {report.xfail_count} xfail · {debt_label}</div>
  </div>
  <div class="card">
    <div class="val" style="color:{iso_col}">{report.isolation_score:.0f}%</div>
    <div class="lbl">Isolation</div>
    <div style="font-size:10px;color:#9ca3af;margin-top:2px">fn-scoped fixtures · {iso_label}</div>
  </div>
</div>

<!-- issues -->
<section>
  <div class="sec-head">
    ✖ Issues <span class="cnt">{report.total_issues}</span>
    <div style="margin-left:auto;font-size:11px;display:flex;gap:6px">
      <span style="background:rgba(220,38,38,.25);color:#fca5a5;padding:2px 7px;border-radius:8px">✖ error=8pts</span>
      <span style="background:rgba(217,119,6,.25);color:#fcd34d;padding:2px 7px;border-radius:8px">⚠ warn=3pts</span>
      <span style="background:rgba(29,130,199,.25);color:#93c5fd;padding:2px 7px;border-radius:8px">ℹ info=1pt</span>
    </div>
  </div>
  <div class="filter-bar">
    <input type="search" id="iss-q" placeholder="Filter issues…" oninput="filterTbl('iss-tbl',this.value)">
    <button class="btn" style="background:#fee2e2;color:#991b1b;border-color:#fca5a5" onclick="filterLvl('error')">✖ Errors</button>
    <button class="btn" style="background:#fef3c7;color:#92400e;border-color:#fcd34d" onclick="filterLvl('warning')">⚠ Warnings</button>
    <button class="btn" style="background:#f1f5f9;color:#374151;border-color:#e2e8f0" onclick="filterLvl('')">All</button>
  </div>
  <table id="iss-tbl">
    <thead><tr><th>File</th><th>Level</th><th>Code</th><th>Message</th></tr></thead>
    <tbody>{issues_html}</tbody>
  </table>
</section>

<!-- files / tests / fixtures tabs -->
<section>
  <div class="sec-head">📁 Tests &amp; Fixtures</div>
  <div class="tabs">
    <div class="tab active" onclick="tab(this,'t-files')">Files ({report.total_files})</div>
    <div class="tab" onclick="tab(this,'t-tests')">Tests ({report.total_tests})</div>
    <div class="tab" onclick="tab(this,'t-fixtures')">Fixtures ({report.total_fixtures})</div>
    <div class="tab" onclick="tab(this,'t-dirs')">By directory</div>
  </div>

  <div class="tab-pane active" id="t-files">
    <table>
      <thead><tr><th>File</th><th>Tests</th><th>Fixtures</th><th>Lines</th><th>Async</th><th>Issues</th></tr></thead>
      <tbody>{"".join(file_rows)}</tbody>
    </table>
  </div>

  <div class="tab-pane" id="t-tests">
    <div class="filter-bar">
      <input type="search" placeholder="Filter tests…" oninput="filterTbl('tst-tbl',this.value)">
    </div>
    <table id="tst-tbl">
      <thead><tr><th>File:line</th><th>Test</th><th>Asserts</th><th>Lines</th><th>Async</th><th>Marks</th><th>Flags</th></tr></thead>
      <tbody>{"".join(test_rows)}</tbody>
    </table>
  </div>

  <div class="tab-pane" id="t-fixtures">
    <table>
      <thead><tr><th>File:line</th><th>Fixture</th><th>Scope</th><th>Async</th><th>Body lines</th><th>Flags</th></tr></thead>
      <tbody>{"".join(fx_rows) or "<tr><td colspan='6' style='text-align:center;color:#6b7280;padding:12px'>No fixtures</td></tr>"}</tbody>
    </table>
  </div>

  <div class="tab-pane" id="t-dirs">
    <table>
      <thead><tr><th>Directory</th><th>Tests</th><th>Errors</th><th>Issues</th></tr></thead>
      <tbody>{dir_rows or "<tr><td colspan='4' style='text-align:center;color:#6b7280;padding:12px'>—</td></tr>"}</tbody>
    </table>
  </div>
</section>

<!-- charts row -->
<div class="grid2">
  <section>
    <div class="sec-head">📊 Fixture scope breakdown</div>
    <div class="chart-section">
      {scope_bars or '<p style="color:#6b7280;font-size:13px">No fixtures</p>'}
    </div>
  </section>
  <section>
    <div class="sec-head">📊 Issues per file (top 10)</div>
    <div class="chart-section">
      <div style="display:flex;gap:12px;margin-bottom:8px;font-size:11px">
        <span><span style="display:inline-block;width:10px;height:10px;background:#dc2626;border-radius:2px"></span> Error</span>
        <span><span style="display:inline-block;width:10px;height:10px;background:#d97706;border-radius:2px"></span> Warning</span>
      </div>
      {issue_chart or '<p style="color:#16a34a;font-size:13px">✔ No issues</p>'}
    </div>
  </section>
</div>

<!-- config + codes -->
<div class="grid2">
  <section>
    <div class="sec-head">⚙ Configuration &amp; suite metrics</div>
    <div class="chart-section">
      <div style="margin-bottom:12px">
        <div style="font-size:11px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;margin-bottom:5px">Registered marks</div>
        <div>{marks_list}</div>
      </div>
      <div style="margin-bottom:12px">
        <div style="font-size:11px;font-weight:600;color:#6b7280;text-transform:uppercase;letter-spacing:.05em;margin-bottom:5px">conftest.py files</div>
        <ul style="list-style:none;padding:0">{conftest_list}</ul>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px">
        <div style="background:#f8fafc;padding:8px 10px;border-radius:6px;border:1px solid #e2e8f0">
          <div style="font-size:20px;font-weight:700;color:{debt_col}">{report.test_debt_pct:.1f}%</div>
          <div style="font-size:11px;color:#6b7280">Test debt ({report.skip_count} skip + {report.xfail_count} xfail)</div>
        </div>
        <div style="background:#f8fafc;padding:8px 10px;border-radius:6px;border:1px solid #e2e8f0">
          <div style="font-size:20px;font-weight:700;color:{iso_col}">{report.isolation_score:.0f}%</div>
          <div style="font-size:11px;color:#6b7280">Isolation (fn-scoped fixtures)</div>
        </div>
        <div style="background:#f8fafc;padding:8px 10px;border-radius:6px;border:1px solid #e2e8f0">
          <div style="font-size:20px;font-weight:700;color:#004d65">{report.async_count}</div>
          <div style="font-size:11px;color:#6b7280">Async tests</div>
        </div>
        <div style="background:#f8fafc;padding:8px 10px;border-radius:6px;border:1px solid #e2e8f0">
          <div style="font-size:20px;font-weight:700;color:#004d65">{len(report.conftest_paths)}</div>
          <div style="font-size:11px;color:#6b7280">conftest.py files</div>
        </div>
      </div>
    </div>
  </section>

  <section>
    <div class="sec-head">🔍 All issue codes ({len(CODES)} checks)</div>
    <div class="chart-section" style="max-height:400px;overflow-y:auto">
      <table style="font-size:12px">
        <thead><tr><th>Code</th><th>Level</th><th>Check</th></tr></thead>
        <tbody>{codes_rows}</tbody>
      </table>
    </div>
  </section>
</div>

<div class="footer">pytest Auditor v3 · <strong>python -m pytest_auditor &lt;path&gt;</strong> · <strong>pytest --quality-report</strong></div>
</div>

<script>
function tab(el,id){{
  el.closest('section').querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  el.closest('section').querySelectorAll('.tab-pane').forEach(p=>p.classList.remove('active'));
  el.classList.add('active');
  document.getElementById(id).classList.add('active');
}}
function filterTbl(id,q){{
  const lq=q.toLowerCase();
  document.getElementById(id).querySelectorAll('tbody tr').forEach(r=>{{
    r.style.display=r.textContent.toLowerCase().includes(lq)?'':'none';
  }});
}}
function filterLvl(lvl){{
  document.getElementById('iss-tbl').querySelectorAll('tbody tr').forEach(r=>{{
    r.style.display=(!lvl||r.textContent.includes(lvl))?'':'none';
  }});
}}
</script>
</body>
</html>"""

    out_path.write_text(html, encoding="utf-8")