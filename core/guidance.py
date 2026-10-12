"""Plain-language explanations and next steps shared by every report format."""

# Keep the observed message on the issue; this catalog explains its consequence
# and gives a concrete next step rather than treating a static finding as proof.
_DATA = '''
T001|No recognized verification was found. Running code without checking its result can let regressions pass.|Assert a meaningful result, use pytest.raises for an expected exception, or use a Playwright expect matcher. If a helper verifies the result, review that helper.
T002|Many assertions can make a failing test difficult to diagnose and may combine unrelated behaviors.|Keep assertions for one behavior together; split independent scenarios or parametrize repeated inputs.
T003|A failure in a loop stops later cases and hides which input failed.|Parametrize independent cases so pytest reports each separately. Keep a loop when it represents one workflow.
T004|Binary floating-point rounding can make exact equality unreliable.|Use assert actual == pytest.approx(expected), with a tolerance appropriate to the calculation.
T005|A fixed temporary path can collide between tests or concurrent runs.|Build the path from tmp_path so each test receives an isolated directory.
T006|Calling a pytest fixture directly bypasses pytest's fixture setup and cleanup.|Request the fixture as a test parameter. If repeated construction is needed, have the fixture return a factory.
T007|An async test needs an async pytest runner; otherwise it may be skipped or fail collection.|Use the appropriate asyncio/anyio mark or configure asyncio_mode='auto'. Async Playwright also requires its async pytest plugin.
T008|Generated parameter IDs may make failing cases hard to identify.|Supply ids= or pytest.param(..., id='descriptive-case').
T009|A single parameter row adds machinery without exercising multiple cases.|Use a regular test or add genuinely different cases.
T010|A large inline case list can be hard to maintain and review.|Group cases by behavior or load well-documented test data from a separate file.
T012|Print output is often leftover debugging and can obscure useful failure output.|Remove debug prints or use logging/capsys when output is part of the behavior being tested.
T013|Catching and ignoring broad exceptions can turn a real failure into a passing test.|Catch a specific expected exception with pytest.raises; let unexpected exceptions fail the test.
T014|An unexplained skip makes it hard to know when the test should be restored.|Add reason= explaining the blocker and, where possible, an issue reference.
T015|An unexplained expected failure hides whether the failure is still intentional.|Add reason= and consider strict=True so an unexpected pass requires review.
T016|A later function with the same name replaces the earlier one, so pytest cannot collect both.|Give every test in the same namespace a unique descriptive name.
T017|Long test bodies can mix setup, actions, and multiple behaviors, making failures harder to follow.|Extract setup into fixtures and repeated operations into named helpers; keep the test's expected outcome visible.
T018|Several expected exceptions may represent separate behaviors with independent failure causes.|Separate independent cases or parametrize them; keep a combined flow only when the sequence matters.
T019|An assertion that is always true cannot detect a regression.|Replace the placeholder with a check of the real return value, state change, or observable behavior.
T020|Checking only truthiness may accept an incorrect non-empty result.|Compare the value or relevant fields to a specific expected result.
T021|Checking only that a collection is non-empty does not verify its contents.|Assert the expected collection or meaningful elements; retain a presence check when presence is the requirement.
T022|A zero-duration sleep yields control but does not wait for a specific condition.|Remove it if unnecessary, or wait for the event/state that the test actually requires.
T023|Starting a new event loop inside an async test can conflict with pytest's runner.|Use an async test and await the operation under the configured async pytest runner.
T024|Special characters in parameter IDs make selecting cases from the command line awkward.|Choose short, descriptive IDs using letters, digits, underscores, or hyphens.
T025|A broad exception expectation can pass for an unrelated implementation failure.|Use the specific exception type and match= for the expected message where useful.
T026|Only code reached before the first exception is executed inside the raises block.|Move setup outside pytest.raises and place only the operation expected to fail inside it.
T027|An unconstrained warning check can accept a warning unrelated to the intended behavior.|Specify the warning class and a stable message pattern with match=.
T028|Repeated parameter rows exercise the same input while appearing to add coverage.|Remove duplicate rows or change them to distinct edge cases.
T029|An unconditional failing assertion hides the reason the test intentionally failed.|Use pytest.fail('specific reason') or assert the actual condition you want to verify.
T030|A failure without a message gives little context to the person debugging it.|Pass a concise explanation to pytest.fail describing the unexpected state.
T031|An assertion inside except may never execute when no exception is raised.|Use pytest.raises so the test also fails when the expected exception is missing.
T032|A debugger call can pause or break unattended test runs.|Remove the call before committing or guard debugging outside the test suite.
T033|Equality can invoke custom comparison behavior; None is a singleton.|Use assert value is None or assert value is not None.
T034|Equality with a boolean can accept values such as 1 or 0 unintentionally.|Use truthiness when that is the requirement, or is True/is False when the exact boolean type matters.
T035|Pytest does not collect ordinary test classes that define __init__.|Move setup into fixtures or setup_method and remove the test class constructor.
T036|Pytest resolves fixtures by explicit parameter names, not arbitrary argument lists.|Replace *args/**kwargs in the test signature with explicit fixture parameters.
T037|Pytest cannot inject a parametrized name absent from the function signature.|Align the decorator's argument names with the test parameters.
T038|Repeated parameter names make the parametrization ambiguous or invalid.|List each parameter name once and align the case rows with that list.
T039|The number of values in a case must match the parametrized argument names.|Add/remove values or adjust the argument list so every row has the correct arity.
T040|A combined boolean assertion gives less precise diagnostics about which condition failed.|Use separate asserts for independently meaningful conditions.
T041|Skip and expected-failure marks express conflicting intentions for the same test.|Keep the mark matching the current behavior and document the reason.
T042|An unconditional skipif adds an unnecessary condition.|Use pytest.mark.skip(reason='...') for a permanent skip or a real condition for skipif.
T043|Default test parameter values can prevent pytest from requesting the intended fixture.|Remove defaults from fixture parameters; put configurable defaults in the fixture implementation.
T044|A warning check without a class does not clearly state the expected warning.|Pass the specific warning class to pytest.warns.
T045|Warning is so broad that unrelated warnings can satisfy the expectation.|Use a specific warning subclass and a stable match= pattern.
T046|Multiple operations inside a warning block make the source of the warning unclear.|Move setup outside the block and keep the operation expected to warn inside it.
T047|unittest exception assertions are less consistent with the rest of a pytest suite.|Prefer with pytest.raises(SpecificError, match='...') for new pytest tests.
FX01|Statements after a top-level return never execute, so intended cleanup is skipped.|Yield the resource and put cleanup after yield, preferably in a try/finally when needed.
FX02|Verification in fixture setup is reported as a setup error, obscuring the test outcome.|Keep behavioral assertions in the test. Use an explicit setup exception for a failed setup precondition.
FX03|A large fixture can combine several setup responsibilities.|Split independent setup into smaller fixtures with explicit dependencies.
FX04|A session-wide autouse fixture affects tests that did not explicitly request it.|Use a narrower scope or opt-in fixture unless the suite-wide effect is intentional.
FX05|A longer-lived fixture cannot depend on a shorter-lived fixture; pytest raises ScopeMismatch.|Narrow the requesting fixture's scope or widen the dependency only if sharing the resource is safe.
FX06|A pytest yield fixture must yield exactly once.|Yield a single resource and perform all cleanup after that yield.
FX07|A fixture parameter hides a Python builtin within the function.|Rename the fixture and parameter to describe the resource, such as record_id.
FX08|A local fixture replaces a parent fixture with the same name, which can change setup unexpectedly.|Verify the override is intentional; rename it when it represents a different resource.
FX09|Fixture dependencies are selected by name; default values do not define optional fixture dependencies.|Remove parameter defaults and handle configurable defaults inside the fixture.
FX10|Yield adds teardown semantics but this fixture has no visible cleanup.|Return the value unless yield is needed for a context manager or other lifecycle behavior.
FX11|The later fixture definition replaces the earlier one in the same module.|Keep one definition per fixture name or rename resources with different responsibilities.
FX12|A same-named dependency may be a deliberate parent-fixture override or an accidental cycle.|Confirm a parent fixture exists; otherwise use a different dependency name.
FX13|Positional scope arguments are unclear and do not match the modern fixture API.|Use @pytest.fixture(scope='module') or another explicit scope keyword.
FX14|Function scope is already pytest's default.|Remove scope='function' unless retaining it makes a project convention clearer.
FX15|yield_fixture is deprecated.|Use @pytest.fixture and keep the yield-based cleanup in the body.
FX16|Finalizer registration separates cleanup from the resource's lifecycle.|Prefer yield with cleanup after it when practical; retain finalizers when their dynamic behavior is required.
FX17|A test mark on a fixture does not configure its async fixture runner.|Use the async plugin's supported fixture decorator and loop-scope configuration.
MK01|A patched dependency may never be exercised or verified by this test.|Assert the relevant call/arguments or assert the observable result that depends on the patch.
MK02|Direct patching requires manual lifecycle management.|Consider mocker.patch for pytest-managed cleanup, or retain an explicit patch context manager.
MK03|Many ANY placeholders can allow incorrect arguments to go unnoticed.|Assert important argument values; use ANY only for values irrelevant to this behavior.
MK04|Direct mock imports may lead to inconsistent patch cleanup conventions.|Consider the mocker fixture for automatic cleanup; standard unittest.mock remains valid when managed explicitly.
MK05|A module-level mock retains call history and configured state between tests.|Create the mock in a function-scoped fixture or reset it reliably between tests.
MK06|An unqualified patch target may refer to the wrong namespace or be invalid.|Patch the name where the code under test looks it up, such as myapp.orders.client.
MK07|Patching the same target twice can accidentally replace the intended mock.|Keep one patch or document distinct nested lifetimes explicitly.
MK08|A lambda replacement can hide mock call tracking and is unnecessary for a constant result.|Use mocker.patch('module.name', return_value=value) when returning a fixed value.
N001|Pytest's default file patterns may not discover this file.|Use test_*.py or *_test.py, or explicitly configure and verify the project's collection patterns.
N002|Functions named check_/verify_ are not collected as pytest tests by default.|Rename intended tests to test_*; keep helpers only when a collected test calls them.
N003|Pytest's default class pattern may not discover tests in this class.|Rename intended test containers to Test* or explicitly configure collection.
N004|unittest.TestCase methods do not receive ordinary pytest fixture parameters.|Use plain pytest classes/functions or the supported unittest fixture setup patterns.
N005|An empty test class contributes no executable tests.|Add the intended test methods or remove the unused class.
N006|A vague name makes the intended behavior hard to understand in failure output.|Name the behavior and scenario, for example test_checkout_rejects_expired_card.
N007|A numeric suffix does not explain the difference between scenarios.|Use descriptive scenario names or parametrization with readable case IDs.
N008|Mixed pytest import styles make API usage less consistent.|Prefer import pytest and qualified API calls when that matches the project's convention.
OR08|A fixture name appears in several conftest files, so directory location changes which setup is used.|Review the hierarchy and document intentional overrides; rename unrelated fixtures.
OR09|Classes may add structure without providing a shared lifecycle.|Consider plain functions, but keep classes when they help group related browser workflows or behaviors.
OR11|Tests without a package marker may not support the cross-file imports the suite expects.|Add __init__.py if tests need package imports; keep namespace/importlib layouts when deliberately configured.
OR12|Deeply nested test paths make discovery and navigation harder.|Flatten unnecessary directories while preserving meaningful feature boundaries.
S001|There is no root conftest.py. This is a suggestion, not a requirement for a valid pytest suite.|Add one only if tests need shared fixtures or hooks; otherwise no change is necessary.
S002|A large test file can make related scenarios harder to find.|Split by feature or behavior while keeping shared setup in fixtures.
S003|This file has no recognized tests or fixtures, so it adds no discovered test coverage.|Add collected tests, rename a helper-only module, or remove an unused file.
S004|No marks were found, so selecting slow/integration groups may be harder.|Add marks only when the suite needs selective runs; register custom marks in pytest configuration.
SA01|Writing to a fixed filesystem location can leave residue or overwrite shared data.|Write under tmp_path and let pytest manage an isolated directory.
SA02|Direct environment changes can leak into later tests.|Use monkeypatch.setenv/delenv so the previous environment is restored automatically.
SA03|Changing the process working directory can affect unrelated tests.|Use monkeypatch.chdir so pytest restores the previous directory.
SA04|Changing sys.path can alter imports for the remainder of the process.|Use monkeypatch.syspath_prepend for temporary changes and automatic restoration.
M001|An unknown custom mark can produce warnings or fail when strict markers are enabled.|Register the mark in pytest.ini or tool.pytest.ini_options.markers in pyproject.toml.
M002|usefixtures on a fixture does not request the dependency as intended.|Declare the dependency as a parameter of the fixture function.
M003|An empty usefixtures mark requests nothing.|Remove it or supply the names of fixtures the test actually needs.
PW01|A fixed delay is neither a guarantee of readiness nor efficient when the UI is already ready.|Wait for a meaningful event/state or use expect(locator).to_be_visible(); await it in async tests.
PW02|Network inactivity may never occur in apps with polling and does not prove the UI is ready.|Assert the specific ready state, such as expect(page.get_by_role('heading')).to_be_visible().
PW03|A UI snapshot is checked once and can fail before an asynchronous update completes.|Use the matching retrying assertion, such as expect(locator).to_have_text('Saved'), instead of assert locator.inner_text() == 'Saved'.
PW04|An async expect matcher returns a coroutine; without await the verification does not run.|Write await expect(locator).to_be_visible() or await the appropriate matcher.
INFO|The test references a helper whose implementation may contain additional behavior.|Review the helper alongside the test; this navigation note does not reduce the score.
'''

GUIDANCE = {code: (why, fix) for code, why, fix in
            (line.split('|', 2) for line in _DATA.strip().splitlines())}


def explain(issue):
    if issue.code == 'T001' and issue.level == 'info':
        return ('Verification appears to be delegated to a helper rather than written directly in the test.',
                'Review the helper to confirm it verifies the intended result. This note does not reduce the score.')
    if issue.code == 'F001':
        return ('Python could not parse this file, so its tests could not be analyzed.',
                'Fix the syntax error at the reported line and rerun the audit. The score is provisional until the file parses.')
    if issue.code == 'F002':
        return ('The file could not be read or parsed, so its tests could not be analyzed.',
                'Check file permissions, encoding, and the reported parser error, then rerun the audit.')
    if issue.code == 'F003':
        return ('A literal assigned to a credential-like name may expose a real secret; this is a heuristic.',
                'Use an obvious dummy value for test data or load real credentials from the environment. Replace/rotate any real exposed secret.')
    return GUIDANCE.get(issue.code, ('Review the observed condition in the finding.',
                                     'Inspect the referenced file and line, then rerun the audit after addressing the cause.'))
