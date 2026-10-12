"""Scoring policy: size normalization, severity, caps, and unavailable scores."""
import pytest

from core.models import FileReport, Issue, SuiteReport
from scanning.suite_scanner import _aggregate, _compute_score


# Synthetic reports isolate scoring policy from parser and filesystem behavior.
def scored_report(tests=100, *, fixtures=0, errors=0, warnings=0, infos=0,
                  coverage=None, debt=0, extra_issues=()):
    report = SuiteReport(root='/tests', generated_at='', coverage_pct=coverage, test_debt_pct=debt)
    issues = list(extra_issues)
    for severity, count, code in [('error', errors, 'T001'), ('warning', warnings, 'T019'), ('info', infos, 'N007')]:
        issues.extend(Issue(severity, code, 'Observed condition', '/tests/test_app.py', line)
                      for line in range(1, count + 1))
    report.files = [FileReport('/tests/test_app.py', test_count=tests, fixture_count=fixtures, issues=issues)]
    _aggregate(report)
    _compute_score(report)
    return report


# Keep warning density fixed at 20% while changing suite size.
@pytest.mark.parametrize('size', [10, 100, 1000], ids=['small', 'medium', 'large'])
def test_same_finding_rate_has_same_score(size):
    report = scored_report(size, warnings=size // 5)
    assert report.score == 95
    assert report.score_breakdown['deductions']['Warnings'] == 5


# Expected values lock down severity weights, rounding, and maximum deductions.
@pytest.mark.parametrize('options,expected', [
    ({}, 100),
    ({'errors': 10}, 70),
    ({'warnings': 10}, 98),
    ({'infos': 10}, 100),
    ({'errors': 100}, 40),
    ({'warnings': 1000}, 75),
    ({'infos': 5000}, 95),
    ({'errors': 100, 'warnings': 100, 'infos': 100, 'coverage': 0, 'debt': 100}, 0),
], ids=['clean', 'error-rate', 'warning-rate', 'rounding', 'widespread-errors',
        'warning-cap', 'suggestion-cap', 'all-components-maxed'])
def test_severity_weights_and_caps(options, expected):
    assert scored_report(**options).score == expected


# Missing coverage is neutral; existing coverage and skipped-test debt are separate inputs.
@pytest.mark.parametrize('options,expected', [
    ({'coverage': None}, 100),
    ({'coverage': 80}, 100),
    ({'coverage': 100}, 100),
    ({'coverage': 0}, 95),
    ({'debt': 10}, 100),
    ({'debt': 100}, 95),
], ids=['missing-coverage', 'target-coverage', 'high-coverage', 'zero-coverage',
        'allowed-debt', 'full-debt'])
def test_optional_coverage_and_debt(options, expected):
    assert scored_report(**options).score == expected


def test_fixtures_contribute_to_analysis_units():
    report = scored_report(10, fixtures=10, warnings=4)
    assert report.score_breakdown['units'] == 20
    assert report.score == 95


# Reports can contain repeated rows, but one location must only affect scoring once.
def test_duplicate_locations_count_once():
    issue = Issue('warning', 'T019', 'Placeholder', '/tests/test_app.py', 1)
    report = scored_report(1, extra_issues=[issue, issue])
    assert report.total_issues == 2
    assert report.score_breakdown['unique_findings']['warning'] == 1
    assert report.score == 75


# Navigation notes and delegated assertions are informational rather than test defects.
@pytest.mark.parametrize('code', ['INFO', 'T001'], ids=['helper-reference', 'delegated-verification'])
def test_helper_notes_do_not_reduce_score(code):
    note = Issue('info', code, 'Helper verifies result', '/tests/test_app.py', 1)
    assert scored_report(1, extra_issues=[note]).score == 100


# An empty scan is unassessed, not a suite whose quality is zero.
def test_empty_scan_has_no_score_or_deductions():
    report = scored_report(0)
    assert report.score is None
    assert report.score_breakdown['status'] == 'no_tests'
    assert report.score_breakdown['deductions'] == {}


# Unparseable files count as analysis units so errors cannot disappear from the score.
def test_unreadable_files_make_score_provisional():
    issue = Issue('error', 'F001', 'Bad syntax', '/tests/test_broken.py', 1)
    report = scored_report(10, extra_issues=[issue])
    assert report.score_breakdown['units'] == 11
    assert report.score_breakdown['status'] == 'provisional'
    assert report.score < 100


# One error must cap the result even when thousands of clean tests dilute its rate.
@pytest.mark.parametrize('size', [1, 100, 10000], ids=['single-test', 'suite', 'large-suite'])
def test_any_error_caps_the_score_without_raising_lower_scores(size):
    report = scored_report(size, errors=1)
    assert report.score == (40 if size == 1 else 70)
    assert report.score_breakdown['error_cap'] == 70
    assert 'cannot exceed 70/100' in report.score_breakdown['note']


def test_cap_reduction_is_included_in_score_breakdown():
    report = scored_report(100, errors=1)
    assert report.score_breakdown['deductions']['Error score cap'] == pytest.approx(29.4)
    assert round(100 - sum(report.score_breakdown['deductions'].values())) == report.score


def test_warning_only_suite_is_not_subject_to_error_cap():
    report = scored_report(100, warnings=1)
    assert report.score > 70
    assert report.score_breakdown['error_cap'] is None
    assert 'Error score cap' not in report.score_breakdown['deductions']
