# pytest-auditor

A static quality audit tool for pytest test suites. Analyses every test file
using Python's AST — no test execution needed. Produces a rich terminal report
and a self-contained HTML report.

**97 checks across 9 categories.** Single runtime dependency: `rich`.
Works as a standalone script, via `make`, or as a pytest plugin.

---

## File structure

```
pytest-auditor/
  Makefile
  README.md
  __main__.py              ← CLI entry point + pytest plugin
  analyse.py               ← public entry point (import scan from here)

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

Copy the project folder next to your root `conftest.py`, then:

```bash
pytest --quality-report
pytest --quality-report --report-html=reports/audit.html
pytest --quality-report --report-fail-under=75
pytest --quality-report --report-json=audit.json
```

---

## Coverage integration

Run coverage from the root of the project being tested. For example, a project
named `inventory_service` might have this layout:

```text
inventory_service/
  pyproject.toml
  src/
    inventory_service/
      __init__.py
      orders.py
  tests/
    test_orders.py
```

Install the test dependencies in that project's uv environment:

```bash
uv add --dev pytest pytest-cov
```

To run the tests and display coverage for an importable package:

```bash
uv run python -m pytest tests --cov=inventory_service
```

`--cov` selects the Python package or source directory to measure; `tests`
selects the test directory to execute. The package name is not necessarily the
same as the project folder or distribution name. For a `src` layout, ensure
the package is installed in the uv environment using the project's packaging
configuration. If it is not installed, you can make `src` importable for pytest
by adding this to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

If `src/` contains several packages or standalone modules, measure the entire
source directory instead:

```bash
uv run python -m pytest tests --cov=src
```

To include coverage in the auditor's quality report, generate `coverage.json`
in the project root alongside the terminal and optional HTML coverage reports:

```bash
uv run python -m pytest tests --cov=src --cov-report=term-missing --cov-report=json:coverage.json --cov-report=html
```

Use `--cov=inventory_service` instead of `--cov=src` when measuring only that
package. Open `htmlcov/index.html` to browse the HTML coverage report.

If you already ran pytest with `--cov`, export its saved `.coverage` data
without rerunning the tests:

```bash
uv run python -m coverage json -o coverage.json
```

Then run the auditor from the same project root, replacing the script path
with the location of your pytest-auditor checkout. Install `rich` in this uv
environment if it is not already available (`uv add --dev rich`).

```bash
uv run python /path/to/pytest-auditor/__main__.py tests --html pytest_audit.html
```

The auditor automatically reads `coverage.json` from the scanned test directory
or its immediate parent, so scanning the project's `tests/` directory finds
the report in the project root. It reads existing coverage data; it does not
execute tests or collect coverage itself. Regenerate the report after source
or test changes to keep the audit current.

Coverage below 80% deducts points from the quality score.

---

## All 97 checks

### T — Test quality (37 checks)

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
| T025 | Warning | pytest.raises(Exception) too broad — use a specific exception type |
| T026 | Warning | pytest.raises block has multiple statements — only first can raise |
| T027 | Info    | pytest.warns() without match= — may accept unrelated warnings |
| T028 | Warning | Duplicate parametrize case values — copy-paste error |
| T029 | Warning | assert False literal — use pytest.fail('reason') instead |
| T030 | Info    | pytest.fail() called without a message |
| T031 | Warning | assert inside except block — use pytest.raises() instead |
| T032 | Warning | Debugger call left in test (pdb, breakpoint, etc.) |
| T033 | Warning | assert x == None — use assert x is None |
| T034 | Warning | assert x == True/False — use assert x / assert not x |
| T035 | Error   | Test class defines \_\_init\_\_ — breaks pytest collection |
| T036 | Warning | \*args/\*\*kwargs in test signature — fixtures cannot be injected |
| T037 | Error   | Parametrize argument name not present in test signature |
| T038 | Warning | Duplicate parametrize argument names |
| T039 | Error   | Parametrize row has wrong number of values |
| T040 | Warning | assert a and b — split into separate asserts for clearer failures |
| T041 | Warning | @skip and @xfail both applied — contradictory marks |
| T042 | Info    | skipif(True, ...) — use @pytest.mark.skip directly |
| T043 | Warning | Test parameter has default value — fixtures cannot have defaults |
| T044 | Warning | pytest.warns() with no warning type specified |
| T045 | Info    | pytest.warns(Warning) too broad — use a specific warning subclass |
| T046 | Info    | Multiple statements in pytest.warns block |
| T047 | Warning | self.assertRaises() used — prefer pytest.raises() |

### FX — Fixtures (17 checks)

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
| FX09 | Info    | Fixture parameter has a default value — fixtures don't support defaults |
| FX10 | Info    | Fixture yields with no teardown after yield — use return instead |
| FX11 | Warning | Fixture defined more than once in the same file |
| FX12 | Warning | Fixture requests another fixture with the same name — circular |
| FX13 | Warning | Fixture scope passed as positional arg — use scope='module' |
| FX14 | Info    | scope='function' is the default — remove redundant argument |
| FX15 | Warning | @pytest.yield_fixture is deprecated — use @pytest.fixture with yield |
| FX16 | Warning | request.addfinalizer() is old-style teardown — use yield instead |
| FX17 | Info    | @pytest.mark.asyncio on a fixture is unnecessary |

### MK — Mocking (8 checks)

| Code | Level   | Check |
|------|---------|-------|
| MK01 | Info    | Mock patched but no assert_called* — patch may never be verified |
| MK02 | Info    | unittest.mock.patch used directly — prefer mocker.patch |
| MK03 | Info    | mock.ANY used 3+ times — assertions too permissive |
| MK04 | Info    | Direct unittest.mock import — prefer mocker fixture (pytest-mock) |
| MK05 | Warning | MagicMock()/Mock() at module level — shared between all tests |
| MK06 | Warning | Patch target has no module path — use 'myapp.module.name' |
| MK07 | Info    | Same mock target patched twice in one test — likely copy-paste error |
| MK08 | Info    | mocker.patch(target, lambda: value) — use return_value= instead |

### N — Naming (8 checks)

| Code | Level   | Check |
|------|---------|-------|
| N001 | Warning | File doesn't follow naming convention (test_*.py or *_test.py) |
| N002 | Warning | Function named check_/verify_ that is never called — pytest won't collect it |
| N003 | Warning | Class doesn't start with Test — its tests won't be collected |
| N004 | Warning | Class inherits from TestCase — pytest fixtures won't inject |
| N005 | Info    | Test class with no test methods |
| N006 | Warning | Vague test name (test_it, test_foo, test_run…) |
| N007 | Info    | Test name ends with a number (test_login1) — use descriptive names |
| N008 | Info    | from pytest import X — prefer import pytest and use pytest.X |

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

### SA — Safety (4 checks)

| Code | Level   | Check |
|------|---------|-------|
| SA01 | Warning | open(..., 'w') with a non-tmp path — use tmp_path |
| SA02 | Warning | os.environ modified directly — use monkeypatch.setenv() |
| SA03 | Warning | os.chdir() used — changes process-wide cwd; use monkeypatch.chdir() |
| SA04 | Warning | sys.path modified directly — use monkeypatch.syspath_prepend() |

### M — Marks (3 checks)

| Code | Level   | Check |
|------|---------|-------|
| M001 | Warning | Unregistered custom mark — add to markers in pyproject.toml |
| M002 | Warning | @pytest.mark.usefixtures on a fixture has no effect |
| M003 | Info    | @pytest.mark.usefixtures() with no arguments — remove it |

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

The score measures finding density rather than subtracting points for every
finding across the entire suite. Larger suites no longer hit zero simply because
they contain more tests. The same finding rate produces the same base score.

An **analysis unit** is a test, fixture, or unreadable test file. Identical
findings (same file, line, code, and severity) count once. Starting at 100:

| Component | Deduction |
|-----------|-----------|
| Errors | 60 × min(1, unique errors / units) |
| Warnings | 25 × min(1, unique warnings / units) |
| Suggestions | 5 × min(1, unique info findings / units) |
| Coverage, when available | 5 × max(0, (80 − coverage%) / 80), capped at 5 |
| Test debt | 5 × max(0, (debt% − 10) / 90), capped at 5 |

Helper navigation and delegated-verification notes do not deduct points.
For example, 100 tests with 20 warnings and no other findings score **95/100**;
1,000 tests with 200 warnings also score **95/100**. A suite where every test
has an error loses 60 points even before other deductions.

If at least one error is found, the final score cannot exceed **70/100**.
The cap can lower a score but never raises an already lower score. Reports show
any extra reduction as “Error score cap”. CLI/CI score thresholds remain optional;
the web UI does not ask for a minimum score.

The final score is rounded to an integer. Reports show each component's
deduction and the number of analysis units. Empty scans have no numerical score (JSON `score: null`) and an explicit
“Not assessed / No tests found” status; scans with unreadable files are marked provisional.
This is a static maintainability signal, not a test pass rate or proof of correctness.
Existing CI thresholds should be reviewed because this replaces the old scoring scale.

Findings retain the observed message and add **why it matters** and a
**suggested fix** in the webpage, HTML, terminal, and JSON reports.

**Grades:** 90–100 Excellent · 80–89 Good · 65–79 Needs work · 50–64 Poor · <50 Critical

---

## Code structure

| File | Responsibility |
|------|----------------|
| `__main__.py` | CLI + pytest plugin, path resolution |
| `analyse.py` | Public entry point — import scan functions from here |
| `core/models.py` | Dataclasses, constants, regex patterns |
| `core/ast_helpers.py` | Pure AST queries — no side effects |
| `core/checks.py` | Issue generators — take a node, return list[Issue] |
| `reporting/config.py` | Read pyproject.toml, pytest.ini, coverage.json |
| `reporting/terminal.py` | Rich terminal output |
| `reporting/html_report.py` | Self-contained HTML report |
| `scanning/file_analyzer.py` | Single file → FileReport |
| `scanning/suite_scanner.py` | Directory → SuiteReport, metrics, score |
| `scanning/targeted.py` | Single file or single test audit |
| `scanning/scanner.py` | Re-exports public scan API |

---

## Requirements

- Python 3.10+
- `rich` — `pip install rich`
- `coverage.json` optional — produced by `coverage json` for coverage integration

## Local web UI

Start the browser interface from this checkout:

```bash
./run.sh
```

The launcher checks Python 3.10+, creates `.venv`, installs missing runtime
dependencies, and starts the app. It reuses the environment on later runs.
If Python is missing and `uv` is installed, it provisions Python 3.12. Otherwise,
it explains which prerequisite to install. It does not install system packages.
Use `./run.sh --port 9000` for another port, or `./run.sh --check` to prepare
the environment without starting the server. Dependency installation requires
network access only when packages are missing. Run `./run.sh --help` for usage.

You can also start it directly with `.venv/bin/python web_server.py`. Browser
binaries and development test dependencies are installed separately using the
test instructions below; they are not needed to run the application.

Open **http://127.0.0.1:6767**. Use `--port 9000` to choose another port.
The server binds to your machine's loopback interface and adds no dependencies.
Stop it with Ctrl+C.

Choose **Full suite**, **Single file**, or **Single test**, enter the local
path (absolute paths and `~` work). Single-test
mode also asks for the test function name. The UI uses the existing scanners,
including their automatic pytest configuration, fixture, and coverage discovery.
It does not execute tests or generate fresh coverage.

Results include score and explanations, coverage, debt, isolation, and
searchable views of issues, files, tests, fixtures, directories, and configuration.
The severity filter combines with search. Download the existing standalone HTML
report or the full JSON report without writing output files into your project.
For automation and pytest lifecycle integration, continue using the CLI/plugin.

Install development dependencies and run the pytest suite with:

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m playwright install chromium
python3 -m pytest -q
```

Use **Browse…** beside the local path to navigate folders or select a Python
file. The picker browses the filesystem on the machine running the server.
Hidden entries and excluded directories are omitted; paths can also be typed.

Choose **GitHub repository** as the source to download and audit a repository.
Enter `owner/repository` or its GitHub URL, optionally specify a branch, tag,
or commit, and enter a repository-relative path such as `tests` or
`tests/test_orders.py`. Leaving the path blank audits the repository root.
All three scan modes and report downloads work with GitHub sources.

Public repositories need no token. For private repositories, supply a GitHub
access token with repository contents read access. The token is used only for
that request, is not saved, and is cleared from the form afterward. Downloads
use GitHub's archive API and temporary files are removed after analysis. No
repository code is executed. Limits: 50 MB download, 150 MB extracted, and
20,000 archive entries; symbolic links are rejected. Network access to GitHub
is required, and API rate limits apply.

## Python Playwright tests

The auditor automatically recognizes browser tests through Playwright sync/async
imports (including aliases), imported type annotations, `expect()` matchers,
or characteristic locator/wait calls on the `page`/`context` fixtures. Detection
is per test, so ordinary unit tests in a mixed module retain their usual rules.
No Playwright installation or browser launch is required to audit source files.

- Playwright `expect(...).to_*()` / `not_to_*()` assertions, including async and
  soft assertions, contribute to assertion counts. Bare `expect()` calls and
  browser actions alone do not count as verification.
- Browser workflows do not receive the generic “more than five assertions” or
  “assert in a loop” warnings. Long browser tests receive advice about page
  objects and named steps. Naming, safety, collection, and async mark checks
  continue to apply.
- Playwright plugin marks (`only_browser`, `skip_browser`, `browser_context_args`)
  are accepted in detected browser files/tests. Known plugin fixture scopes
  participate in fixture scope checks; explicit fixture definitions override
  those defaults.
- Tests carry a `framework` field (`playwright` or `pytest`) in JSON and the
  webpage's Tests view; standalone HTML labels Playwright tests as well.

| Code | Level | Browser-specific check |
|------|-------|------------------------|
| PW01 | Warning | Fixed `wait_for_timeout` delay; prefer auto-waiting actions/assertions |
| PW02 | Warning | `networkidle` used for readiness; assert expected UI state |
| PW03 | Warning | Raw assert on UI snapshot methods; prefer retrying `expect()` matchers |
| PW04 | Warning | Async Playwright `expect()` matcher called without `await` |

These are static heuristics: external page-object/helper implementations,
dynamic aliases, and values captured earlier in separate statements are not
fully resolved. Existing coverage data and score deductions still apply;
Playwright findings contribute to the warning-density component.

In the Issues view, use **Sort by** to order findings by severity (errors first),
issue code (similar findings together), or file (then line number). Choose
ascending or descending order. Sorting combines with search and severity filters
and is also available in the downloaded standalone HTML report.


The scanner also recognizes `unittest.TestCase` subclasses regardless of class
name, including imported aliases and inheritance through local base classes.
Their `self.assert*()` assertions contribute to verification counts, and methods
are labeled `unittest` in the report. Ordinary TestCase methods are not required
to accept pytest fixtures or use pytest's exception assertion style.


`tests/test_web_ui_browser.py` contains real browser tests using the Playwright
`page` fixture and `expect()` assertions. They launch the local server and test
suite/file/test audits, results, explanations, sorting/filtering, folder selection,
GitHub form interactions, empty/error states, and JSON/HTML downloads. GitHub
network downloads are stubbed for deterministic browser tests.
`tests/test_browser_source_analysis.py` contains the source-snippet regression tests
for the auditor's Playwright-specific static rules.

Run only browser tests with `python3 -m pytest -q -m browser`, or run backend
and static-rule tests with `python3 -m pytest -q -m "not browser"`.
On a Linux system missing browser libraries, install them with
`python3 -m playwright install --with-deps chromium`.

The test suite separates discovery, scoring, reporting, web-source handling,
HTTP integration, static Playwright rules, and browser workflows into focused
modules. Shared fixtures in `tests/conftest.py` create isolated source files,
ZIP archives, and the local server. GitHub tests replace only the network
boundary and verify temporary checkout cleanup; browser tests run against the
real scanner and HTTP server.


Test modules are named by the behavior they cover:

| Module | Responsibility |
|--------|----------------|
| `test_suite_discovery.py` | Test collection and verification detection |
| `test_quality_scoring.py` | Score normalization, weighting, and limits |
| `test_report_exports.py` | Findings, displayed paths, and HTML/JSON report data |
| `test_browser_source_analysis.py` | Static Playwright source-analysis rules |
| `test_audit_requests.py` | Direct audit requests and temporary checkout cleanup |
| `test_http_endpoints.py` | Real HTTP routing, authentication, and request validation |
| `test_local_folder_browser.py` | Local folder picker listings |
| `test_github_sources.py` | GitHub URLs, downloads, and archive safety |
| `test_web_ui_browser.py` | Real browser interactions and downloaded reports |

Source snippets are test input data; comments distinguish them from the real
browser cases. Empty-scan checks at the scoring, report, and browser layers
verify different contracts. Serialization is verified at the HTTP/download
boundaries instead of repeating JSON round-trip assertions in every audit test.


## Docker launcher

`./run.sh` starts the application locally. To build and start it in Docker:

```bash
./rundocker.sh
```

Docker and its Compose plugin must be installed, with the daemon running.
The launcher waits for the app to be healthy, then prints
**http://127.0.0.1:6767**. It runs in the background and publishes only on localhost.
Python and runtime dependencies are installed in the image.

The checkout is mounted read-only at `/workspace`; enter `/workspace/tests`
in the UI to audit this repo. The folder picker browses container paths.
To audit another project or choose a different host port:

```bash
AUDIT_SOURCE_DIR=/path/to/project AUDITOR_PORT=9000 ./rundocker.sh
```

Stop and remove this application's containers and network:

```bash
./rundocker.sh stop
```

The built image remains cached for the next start. Host files are preserved.
Docker and local launchers need different ports when running at the same time.

## Azure launcher

```bash
./runazure.sh
```

The launcher signs in through Microsoft’s browser login when needed, discovers
an enabled subscription, and deploys a source ZIP to **Azure App Service for
Linux with managed Python 3.12**. Docker and Container Registry are not required.
Azure installs `requirements.txt` with Oryx and starts
`python web_server.py --host 0.0.0.0 --port 8000`. The launcher checks the actual
application over HTTPS before opening the URL.

Only application sources and web assets are uploaded; local projects, credentials,
virtual environments, and tooling are excluded. Reruns update the same app,
including switching a previous container deployment to managed Python. Existing
registries are left in place; delete an unused registry separately to stop its charges.

Defaults: resource group `pytest-auditor-rg`, plan `pytest-auditor-plan`, region
`westeurope`, and a deterministic app name based on subscription/resource group.
The default **B1** plan is billable. For limited free testing, use:

```bash
AZURE_APP_SERVICE_SKU=F1 ./runazure.sh
```

The SKU applies when creating a plan; existing plans keep their tier. F1 has daily
CPU limits and no Always On. Availability and quotas depend on subscription and
region. Existing resource-group location is reused; region admission or quota failures try
nearby European regions unless `AZURE_LOCATION` is explicitly set.

Overrides: `AZURE_SUBSCRIPTION`, `AZURE_RESOURCE_GROUP`, `AZURE_LOCATION`,
`AZURE_APP_NAME`, `AZURE_APP_SERVICE_PLAN`, and `AZURE_APP_SERVICE_SKU`.
Set `AZURE_OPEN_BROWSER=0` in CI. Initial login/MFA can require interaction;
`AZURE_NONINTERACTIVE=1` requires an existing login and prevents prompts.
`AZURE_MANAGED_IDENTITY=1` supports a configured Azure host.
The Azure CLI installs into `.azure-cli` if absent and uses its own Python.

Hosted audits use GitHub sources; local folders are not mounted in Azure.
Azure resources remain billable after the script exits.
For deployment failures, use `az webapp log deployment show --name APP --resource-group GROUP`;
for startup failures, use `az webapp log tail --name APP --resource-group GROUP`.
