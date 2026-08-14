# pytest-auditor

A static quality audit tool for pytest test suites. Analyses every test file
using Python's AST — no test execution needed. Produces a rich terminal report
and a self-contained HTML report.

**59 checks across 9 categories.** Single runtime dependency: `rich`.
Works as a standalone script, via `make`, or as a pytest plugin.

---

## File structure

```
pytest-auditor/
  Makefile
  README.md
  __main__.py              ← CLI entry point + pytest plugin

  core/
    models.py              ← dataclasses and shared constants
    ast_helpers.py         ← pure AST inspection functions
    checks.py              ← issue-generating check logic

  reporting/
    config.py              ← pyproject.toml / pytest.ini / coverage.json reading
    terminal.py            ← rich terminal reporter
    html_report.py         ← self-contained HTML report generator

  scanning/
    file_analyzer.py       ← single file analysis
    suite_scanner.py       ← full directory scan and aggregation
    targeted.py            ← single file / single test scan
    scanner.py             ← re-exports public scan API
```

---

## Quickest start — make

```bash
make audit                             # scan ./tests → pytest_audit.html
make audit TESTS=src/tests             # custom path
make audit TESTS=~/myproject/tests     # ~ paths work
make audit HTML=reports/out.html       # custom output path
make audit-strict                      # fail if score < 80
make audit-strict SCORE=90             # custom threshold
```

---

## Usage — standalone script

```bash
pip install rich

# Full suite scan
python __main__.py                          # scan ./tests
python __main__.py path/to/tests            # custom path
python __main__.py tests --html out.html    # custom HTML output
python __main__.py tests --json out.json    # JSON output (CI/badges)
python __main__.py tests --fail-under 80    # exit 1 if score < 80
python __main__.py tests --no-terminal      # HTML only, no terminal

# Single file
python __main__.py --file path/to/test_orders.py

# Single test function (checks test + its fixtures + called helpers)
python __main__.py --file path/to/test_orders.py --test test_create_order
```

---

## Usage — pytest plugin

Copy the project folder next to your root `conftest.py` and add `HERE` to
`sys.path`, then:

```bash
pytest --quality-report
pytest --quality-report --report-html=reports/audit.html
pytest --quality-report --report-fail-under=75
pytest --quality-report --report-json=audit.json
```

---

## Coverage integration

```bash
pytest --cov=myapp --cov-report=json
python __main__.py tests        # reads coverage.json automatically
```

Coverage below 80% deducts points from the quality score.

---

## All 59 checks

### T — Test quality (24 checks)

| Code | Level   | Check |
|------|---------|-------|
| T001 | Error   | No assert statements — test proves nothing |
| T002 | Warning | >5 assertions — split or use parametrize |
| T003 | Warning | Loop with assert inside — use @parametrize |
| T004 | Warning | Float compared with == — use pytest.approx() |
| T005 | Warning | Hardcoded /tmp path — use tmp_path fixture |
| T006 | Error   | Fixture called as a function instead of declared as parameter |
| T007 | Info    | Async test without @pytest.mark.asyncio |
| T008 | Info    | @parametrize without readable id= names |
| T009 | Info    | @parametrize with only 1 case — use a regular test |
| T010 | Info    | @parametrize with >20 cases — consider loading from CSV/JSON |
| T012 | Info    | print() found — likely debugging code left behind |
| T013 | Warning | Bare except / except Exception: pass — swallows failures silently |
| T014 | Warning | @skip without reason= — document why |
| T015 | Warning | @xfail without reason= — document why |
| T016 | Warning | Duplicate test name in same file — silent collection conflict |
| T017 | Info    | Test body >30 lines — consider splitting |
| T018 | Info    | Multiple pytest.raises blocks — each should be its own test |
| T019 | Warning | assert True / assert 1==1 — placeholder proves nothing |
| T020 | Info    | Bare `assert result` (single name) — use assert result == expected |
| T021 | Info    | assert len(x) > 0 — use assert x or assert x == [expected] |
| T022 | Info    | asyncio.sleep(0) — usually unnecessary in tests |
| T023 | Warning | asyncio.run() inside test — use async def + asyncio_mode='auto' |
| T024 | Info    | Parametrize id with spaces/brackets — makes -k filtering awkward |

### FX — Fixtures (8 checks)

| Code | Level   | Check |
|------|---------|-------|
| FX01 | Warning | Statements after a top-level return — unreachable teardown; use yield |
| FX02 | Warning | assert inside fixture before yield — shows as ERROR not FAILED |
| FX03 | Info    | Fixture body >30 lines — consider splitting |
| FX04 | Warning | autouse=True + session scope — affects every test in the entire run |
| FX05 | Error   | Fixture scope mismatch — outer scope < inner (will raise ScopeError) |
| FX06 | Warning | Fixture yields more than once — only first yield is used |
| FX07 | Info    | Fixture parameter shadows a Python builtin (id, type, list…) |
| FX08 | Info    | Fixture name shadows a same-named fixture in a parent conftest.py |

### MK — Mocking (7 checks)

| Code | Level   | Check |
|------|---------|-------|
| MK01 | Info    | Mock patched but no assert_called* — patch may never be verified |
| MK02 | Info    | unittest.mock.patch used directly — prefer mocker.patch |
| MK03 | Info    | mock.ANY used 3+ times — assertions too permissive |
| MK04 | Info    | Direct unittest.mock import — prefer mocker fixture (pytest-mock) |
| MK05 | Warning | MagicMock()/Mock() at module level — shared between all tests |
| MK06 | Warning | Patch target has no module path — use 'myapp.module.name' |
| MK07 | Info    | Same mock target patched twice in one test — likely copy-paste error |

### N — Naming (7 checks)

| Code | Level   | Check |
|------|---------|-------|
| N001 | Warning | File doesn't follow naming convention (test_*.py or *_test.py) |
| N002 | Warning | Function named check_/verify_ that is never called — pytest won't collect it |
| N003 | Warning | Class doesn't start with Test — its tests won't be collected |
| N004 | Warning | Class inherits from TestCase — pytest fixtures won't inject |
| N005 | Info    | Test class with no test methods |
| N006 | Warning | Vague test name (test_it, test_foo, test_run…) |
| N007 | Info    | Test name ends with a number (test_login1) — use descriptive names |

### OR — Organisation (4 checks)

| Code | Level   | Check |
|------|---------|-------|
| OR08 | Warning | Same fixture name in multiple conftest.py files — inner shadows outer |
| OR09 | Info    | All tests in classes but no class-scoped fixture — plain functions may be simpler |
| OR11 | Info    | No __init__.py in tests directory — cross-file imports may fail |
| OR12 | Info    | Tests nested >4 directories deep — hard to navigate |

### S — Suite structure (4 checks)

| Code | Level   | Check |
|------|---------|-------|
| S001 | Info    | No conftest.py in tests root |
| S002 | Info    | Test file >200 lines — consider splitting |
| S003 | Info    | Test file with no tests or fixtures |
| S004 | Info    | No tests have any marks — includes pytestmark module assignments |

### SA — Safety (2 checks)

| Code | Level   | Check |
|------|---------|-------|
| SA01 | Warning | open(..., 'w') with a non-tmp path — use tmp_path |
| SA02 | Warning | os.environ modified directly — use monkeypatch.setenv() |

### M — Marks (1 check)

| Code | Level   | Check |
|------|---------|-------|
| M001 | Warning | Unregistered custom mark — add to markers in pyproject.toml |

### F — File (3 checks)

| Code | Level   | Check |
|------|---------|-------|
| F001 | Error   | Syntax error in test file |
| F002 | Error   | File cannot be parsed |
| F003 | Warning | Possible hardcoded credential (password=, token=, api_key=…) |

---

## Excluded directories

Never scanned — virtualenvs, caches, build artefacts:

```
.venv  venv  .env  env
.tox  .nox
node_modules
.git  .hg  .svn
__pycache__
.mypy_cache  .pytest_cache  .ruff_cache
build  dist  *.egg-info
.eggs  htmlcov  site-packages
```

---

## Quality score

Starts at 100 and deducts:

| Item | Deduction |
|------|-----------| 
| Each error | 8 points |
| Each warning | 3 points |
| Each info | 1 point |
| Coverage < 80% | 0.5 × (80 − coverage%) |
| Test debt > 10% | 0.3 × debt% |

**Grades:** 90–100 Excellent · 80–89 Good · 65–79 Needs work · 50–64 Poor · <50 Critical

---

## HTML report features

- Quality score ring with colour-coded grade
- 10 stat cards — tests, files, fixtures, coverage, errors, warnings, info,
  test debt %, isolation score, async count
- Filterable issues table — search by text or filter by level
- Files tab — per-file summary with issue counts
- Tests tab — every test with assert count, line count, marks, flags
- Fixtures tab — scope, body length, autouse/return flags
- By directory tab — which subdirectory has the most errors
- Fixture scope breakdown chart
- Issues per file chart (top 10)
- Configuration panel — registered marks, conftest.py locations
- Full codes reference — all 59 checks

---

## Code structure

| File | Lines | Responsibility |
|------|-------|----------------|
| `__main__.py` | 153 | CLI + pytest plugin, path resolution |
| `core/models.py` | 110 | Dataclasses, constants, regex patterns |
| `core/ast_helpers.py` | 482 | Pure AST queries — no side effects |
| `core/checks.py` | 443 | Issue generators — take a node, return list[Issue] |
| `reporting/config.py` | 90 | Read pyproject.toml, pytest.ini, coverage.json |
| `reporting/terminal.py` | 174 | Rich terminal output |
| `reporting/html_report.py` | 554 | Self-contained HTML report |
| `scanning/file_analyzer.py` | 149 | Single file → FileReport |
| `scanning/suite_scanner.py` | 184 | Directory → SuiteReport, metrics, score |
| `scanning/targeted.py` | 223 | Single file or single test audit |
| `scanning/scanner.py` | 32 | Re-exports public scan API |

---

## Requirements

- Python 3.10+
- `rich` — `pip install rich`
- `coverage.json` optional — produced by `coverage json` for coverage integration