# pytest-auditor

A quality audit tool for pytest test suites. Scans your tests directory,
checks for common mistakes and best practices, and produces a rich terminal
report + a self-contained HTML report.

## Install

```bash
# No install needed — just copy the pytest_auditor/ folder
pip install rich          # for terminal colours
```

## Run as standalone script

```bash
# Basic — scans ./tests, opens pytest_audit.html
python -m pytest_auditor

# Specify path
python -m pytest_auditor path/to/tests

# HTML report to custom path
python -m pytest_auditor tests --html reports/audit.html

# JSON output (for CI integration)
python -m pytest_auditor tests --json audit.json

# Fail if quality score is below 80
python -m pytest_auditor tests --fail-under 80

# Quiet (no terminal output)
python -m pytest_auditor tests --no-terminal --html report.html
```

## Run as pytest plugin

Copy `pytest_auditor/` next to your `conftest.py`, then:

```bash
# Run tests + audit report at the end
pytest --quality-report

# With custom HTML output path
pytest --quality-report --report-html=reports/audit.html

# Fail the build if quality score < 75
pytest --quality-report --report-fail-under=75

# With JSON for CI badges
pytest --quality-report --report-json=audit.json
```

## What it checks

| Code | Level   | Check                                              |
|------|---------|--------------------------------------------------- |
| T001 | Error   | Test has no assert statements                      |
| T002 | Warning | Test has >5 assertions — split or use parametrize  |
| T003 | Warning | Loop with assert inside — use @parametrize         |
| T004 | Warning | Float compared with == — use pytest.approx()       |
| T005 | Warning | Hardcoded /tmp path — use tmp_path fixture         |
| T006 | Error   | Fixture called as function instead of declared     |
| T007 | Info    | Async test without @pytest.mark.asyncio            |
| T008 | Info    | @parametrize without readable id= names            |
| M001 | Warning | Unregistered custom mark                           |
| N001 | Warning | File not named test_*.py or *_test.py              |
| N002 | Warning | Function named check_/verify_ — won't be collected |
| N003 | Warning | Class not named Test* — won't be collected         |
| F001 | Error   | Syntax error in test file                          |
| FX01 | Info    | Fixture has many statements but uses return        |
| S001 | Info    | Missing conftest.py in tests root                  |

## Quality score

Starts at 100 and deducts:
- **8 points** per error
- **3 points** per warning
- **1 point** per info
- **Up to 40 points** for coverage below 80%

Supply a `coverage.json` file (run `coverage json`) for coverage tracking.

## HTML report features

- Quality score ring with grade
- Summary stat cards
- Filterable issues table (by text or severity level)
- Per-file breakdown with issues highlighted
- All tests table with marks, assert counts, flags
- All fixtures table with scope and return type
- Fixture scope breakdown chart
- Issues-per-file bar chart
- Issue codes reference
- Configuration summary (marks, conftest.py files)
