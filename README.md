# pytest-auditor

A static quality audit tool for pytest test suites. Scans your `tests/`
directory, analyses every file with Python's AST (no test execution needed),
and produces a rich terminal report + a self-contained HTML report.

**62 checks across 9 categories.** Zero dependencies beyond `rich` for
terminal colours. Works as a standalone script, a shell script, or a pytest plugin.

---

## File structure

```
your-project/
  run.sh                  ← shell script — install deps + run
  pytest_auditor/
    __init__.py
    __main__.py           ← CLI entry point + pytest plugin hooks
    analyse.py            ← core AST engine (62 checks)
    terminal.py           ← rich terminal reporter
    html_report.py        ← self-contained HTML report generator
    README.md
```

---

## Quickest start — shell script

```bash
chmod +x run.sh

./run.sh                        # scan ./tests → pytest_audit.html
./run.sh src/tests              # custom path
./run.sh tests --fail-under 80  # fail if score < 80
./run.sh tests --json out.json  # also write JSON
```

The script:
1. Finds Python 3.10+ on your system
2. Installs `rich` if not already present
3. Verifies all auditor files are in place
4. Runs the audit and prints the HTML output path

Exit codes: `0` = clean · `1` = score below `--fail-under` threshold · `2` = bad arguments

---

## Usage — standalone script

```bash
pip install rich

# Scan ./tests (default)
python -m pytest_auditor

# Specify path
python -m pytest_auditor path/to/tests

# Custom HTML output path
python -m pytest_auditor tests --html reports/audit.html

# JSON output (CI dashboards, badges)
python -m pytest_auditor tests --json audit.json

# Fail if quality score below threshold
python -m pytest_auditor tests --fail-under 80

# Suppress terminal output (HTML only)
python -m pytest_auditor tests --no-terminal --html report.html
```

---

## Usage — pytest plugin

Copy `pytest_auditor/` next to your root `conftest.py`, then:

```bash
# Run tests + audit at the end
pytest --quality-report

# Custom HTML path
pytest --quality-report --report-html=reports/audit.html

# Fail build if score < 75
pytest --quality-report --report-fail-under=75

# JSON output
pytest --quality-report --report-json=audit.json
```

---

## Coverage integration

Run `coverage json` before the auditor to include coverage data:

```bash
pytest --cov=myapp --cov-report=json
python -m pytest_auditor tests
# or:
./run.sh tests
```

The auditor reads `coverage.json` automatically from the project root.
Coverage below 80% deducts up to 40 points from the quality score.

---

## All 62 checks

### T — Test quality (24 checks)

| Code | Level   | Check |
|------|---------|-------|
| T001 | Error   | No assert statements — test proves nothing |
| T002 | Warning | >5 assertions — consider splitting or using parametrize |
| T003 | Warning | Loop with assert inside — use @pytest.mark.parametrize |
| T004 | Warning | Float compared with == — use pytest.approx() |
| T005 | Warning | Hardcoded /tmp path — use tmp_path fixture |
| T006 | Error   | Fixture called as a function instead of declared as parameter |
| T007 | Info    | Async test without @pytest.mark.asyncio |
| T008 | Info    | @parametrize without readable id= names |
| T009 | Info    | @parametrize with only 1 case — use a regular test |
| T010 | Info    | @parametrize with >20 cases — consider loading from CSV/JSON |
| T011 | Warning | time.sleep() in test — mock time instead |
| T012 | Info    | print() found — likely debugging code left behind |
| T013 | Warning | Bare except / except Exception: pass — swallows failures silently |
| T014 | Warning | @skip without reason= — document why it's skipped |
| T015 | Warning | @xfail without reason= — document why it's expected to fail |
| T016 | Warning | Duplicate test name in same file — silent collection conflict |
| T017 | Info    | Test body >30 lines — consider splitting into smaller tests |
| T018 | Info    | Multiple pytest.raises blocks — each should be its own test |
| T019 | Warning | assert True / assert 1==1 — placeholder that proves nothing |
| T020 | Info    | Bare assert result (single name) — use assert result == expected |
| T021 | Info    | assert len(x) > 0 — use assert x or assert x == [expected] |
| T022 | Info    | asyncio.sleep(0) — usually unnecessary in tests |
| T023 | Warning | asyncio.run() inside test — use async def + asyncio_mode='auto' |
| T024 | Info    | Parametrize id with spaces/brackets — makes -k filtering awkward |

### FX — Fixtures (9 checks)

| Code | Level   | Check |
|------|---------|-------|
| FX01 | Info    | Fixture with many statements uses return — consider yield for teardown |
| FX02 | Warning | assert inside fixture — shows as ERROR not FAILED |
| FX03 | Info    | Fixture body >30 lines — consider splitting into smaller fixtures |
| FX04 | Warning | autouse=True + session scope — affects every test in the entire run |
| FX05 | Error   | Fixture scope mismatch — outer scope < inner scope (will raise ScopeError) |
| FX06 | Warning | Fixture yields more than once — only first yield is used |
| FX07 | Info    | Fixture parameter name shadows a Python builtin (id, type, list…) |
| FX08 | Info    | Fixture name shadows a same-named fixture in a parent conftest.py |
| FX09 | Info    | Fixture used by only 1 test — consider inlining the setup |

### MK — Mocking (7 checks)

| Code | Level   | Check |
|------|---------|-------|
| MK01 | Info    | Mock patched but no assert_called* found — patch may never be verified |
| MK02 | Info    | unittest.mock.patch used directly — prefer mocker.patch (pytest-mock) |
| MK03 | Info    | mock.ANY used 3+ times — assertions are too permissive |
| MK04 | Info    | Direct unittest.mock import — prefer mocker fixture from pytest-mock |
| MK05 | Warning | MagicMock()/Mock() at module level — shared between all tests |
| MK06 | Warning | Patch target has no module path — use 'myapp.module.name' not 'name' |
| MK07 | Info    | Same mock target patched twice in one test — likely copy-paste error |

### N — Naming (7 checks)

| Code | Level   | Check |
|------|---------|-------|
| N001 | Warning | File doesn't follow naming convention (test_*.py or *_test.py) |
| N002 | Warning | Function named check_/verify_ — pytest won't collect it |
| N003 | Warning | Class doesn't start with Test — its tests won't be collected |
| N004 | Warning | Class inherits from TestCase — pytest fixtures won't inject |
| N005 | Info    | Test class with no test methods |
| N006 | Warning | Vague test name (test_it, test_foo, test_1, test_run…) |
| N007 | Info    | Numbered test name (test_login1, test_2) — use descriptive names |

### OR — Organisation (5 checks)

| Code | Level   | Check |
|------|---------|-------|
| OR08 | Warning | Same fixture name in multiple conftest.py files — inner shadows outer |
| OR09 | Info    | All tests in classes but no class-scoped fixture — plain functions may be simpler |
| OR10 | Info    | No imports from production code — file may not test any real logic |
| OR11 | Info    | No __init__.py in tests directory — cross-file imports may fail |
| OR12 | Info    | Tests nested >4 directories deep — hard to navigate |

### S — Suite structure (4 checks)

| Code | Level   | Check |
|------|---------|-------|
| S001 | Info    | No conftest.py in tests root — add one for shared fixtures |
| S002 | Info    | Test file >200 lines — consider splitting into multiple modules |
| S003 | Info    | Test file with no tests or fixtures |
| S004 | Info    | No tests have any marks — consider tagging slow/integration/smoke tests |

### SA — Safety (2 checks)

| Code | Level   | Check |
|------|---------|-------|
| SA01 | Warning | open(..., 'w') with a non-tmp path — use tmp_path to avoid residue |
| SA02 | Warning | os.environ modified directly — use monkeypatch.setenv() so it reverts |

### M — Marks (1 check)

| Code | Level   | Check |
|------|---------|-------|
| M001 | Warning | Unregistered custom mark — add to markers in pyproject.toml |

### F — File (3 checks)

| Code | Level   | Check |
|------|---------|-------|
| F001 | Error   | Syntax error in test file |
| F002 | Error   | File cannot be parsed |
| F003 | Warning | Possible hardcoded credential (password=, token=, api_key= with literal value) |

---

## Quality score

Starts at 100 and deducts:

| Item | Deduction |
|------|-----------|
| Each error | 8 points |
| Each warning | 3 points |
| Each info | 1 point |
| Coverage < 80% | 0.5 × (80 − coverage%) — up to 40 points |
| Test debt > 10% | 0.3 × debt% — up to 15 points |

**Grades:** 90–100 Excellent · 80–89 Good · 65–79 Needs work · 50–64 Poor · <50 Critical

---

## HTML report features

- **Quality score ring** with colour-coded grade
- **10 stat cards** — tests, files, fixtures, coverage, errors, warnings, info,
  test debt %, isolation score, async count
- **Filterable issues table** — search by text, filter by error / warning / info
- **Files tab** — per-file summary with issue counts colour-highlighted
- **Tests tab** — every test with assert count, line count, marks, and issue flags
- **Fixtures tab** — all fixtures with scope, body length, autouse/return flags
- **By directory tab** — which subdirectory has the most errors
- **Fixture scope breakdown chart** — visual bar chart by scope
- **Issues per file chart** — top 10 files by issue count (errors vs warnings)
- **Configuration panel** — registered marks, conftest.py locations, suite metrics
- **Full codes reference** — all 62 checks in a scrollable table

---

## Terminal output example

```
  pytest-auditor
  Quality audit for your pytest test suite

[1/4]  Checking Python
  ✔  Found Python 3.12.3

[2/4]  Installing dependencies
  ✔  rich already installed

[3/4]  Locating pytest_auditor
  ✔  pytest_auditor/ found

[4/4]  Running audit
  →  Tests path : /your/project/tests
  →  HTML output: /your/project/pytest_audit.html

  Quality score   72/100  Needs work
  ████████████████████████████░░░░░░░░░░░░

  Test files     8      Total tests     64
  Fixtures       12     Coverage        78.3%
  Errors         1      Warnings        9
  Info notes     6      conftest.py     2

  ✖ T001:42   test_user_empty: no assert statements
  ⚠ T003:87   test_prices: loop with assert — use @parametrize
  ⚠ SA02:103  test_env: os.environ modified directly
  ℹ MK07:211  test_api: same mock target patched twice

  ✔  Done.  Open pytest_audit.html in your browser.
```

---

## Requirements

- Python 3.10+
- `rich` — terminal colours (`pip install rich`)
- No other runtime dependencies
- `coverage.json` optional — produced by `coverage json` for coverage integration