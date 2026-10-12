"""Collection and verification regressions using explicit, controlled input suites."""
import pytest

from scanning.scanner import scan, scan_test


# Collection must agree across suite scans, file scans, and focused scans.
@pytest.mark.parametrize('mode', ['suite', 'file', 'test'])
def test_pytest_tests_are_found_in_every_scan_mode(scan_source, mode):
    report = scan_source('''
        def test_checkout():
            assert 1 + 1 == 2
    ''', mode=mode)
    assert report.total_tests == 1
    assert report.total_files == 1
    assert next(test for file in report.files for test in file.tests)['framework'] == 'pytest'
    assert report.score is not None


# Compatibility checks use unittest source as data; all tests here are pytest functions.
@pytest.mark.parametrize('header,base', [
    ('import unittest', 'unittest.TestCase'),
    ('import unittest as ut', 'ut.TestCase'),
    ('from unittest import TestCase as Case', 'Case'),
], ids=['qualified', 'module-alias', 'class-alias'])
@pytest.mark.parametrize('mode', ['suite', 'file', 'test'])
def test_testcase_aliases_are_discovered_with_assertions(scan_source, header, base, mode):
    # This is source data for the auditor; the regression case itself is pytest.
    source = header + f'''
class CheckoutCases({base}):
    def test_checkout(self):
        self.assertEqual(2, 2)
        with self.assertRaises(ValueError):
            int('invalid')
'''
    report = scan_source(source, mode=mode)
    test = next(test for file in report.files for test in file.tests)
    assert (test['framework'], test['class'], test['asserts']) == ('unittest', 'CheckoutCases', 2)
    assert not {'T001', 'N003', 'N004', 'T047'} & {issue.code for file in report.files for issue in file.issues}


def test_unrelated_assert_method_is_not_unittest_verification(scan_source):
    report = scan_source('''
        class TestCheckout:
            def test_checkout(self):
                self.assertEqual(2, 2)
    ''')
    assert any(issue.code == 'T001' and issue.level == 'error'
               for file in report.files for issue in file.issues)


# Method names only need to be unique within their own class namespace.
def test_repeated_method_names_in_different_classes_are_valid(scan_source):
    report = scan_source('''
        class TestOrders:
            def test_checkout(self):
                assert 1 + 1 == 2
        class TestPayments:
            def test_checkout(self):
                assert 2 + 2 == 4
    ''')
    assert report.total_tests == 2
    assert not any(issue.code == 'T016' for file in report.files for issue in file.issues)


# An injected factory is a callable value, not a direct call to its fixture definition.
@pytest.mark.parametrize('signature,expected_error', [
    ('make_item', False), ('', True),
], ids=['injected-factory', 'direct-fixture-call'])
def test_callable_fixture_values_are_not_direct_fixture_calls(scan_source, signature, expected_error):
    report = scan_source(f'''import pytest
@pytest.fixture
def make_item():
    def create():
        return 42
    return create

def test_checkout({signature}):
    assert make_item() == 42
''')
    assert any(issue.code == 'T006' for file in report.files for issue in file.issues) == expected_error


# Discovery should exclude helper modules and virtual-environment contents.
def test_suite_ignores_non_test_files_and_excluded_directories(write_test_file):
    path = write_test_file('def test_checkout():\n    assert 1 + 1 == 2')
    write_test_file('def test_unused():\n    assert True', name='helper.py')
    write_test_file('def test_cached():\n    assert True', name='.venv/test_cached.py')
    report = scan(path.parent)
    assert [test['name'] for file in report.files for test in file.tests] == ['test_checkout']


def test_focused_scan_reports_missing_test(write_test_file):
    path = write_test_file('def test_checkout():\n    assert 1 + 1 == 2')
    with pytest.raises(ValueError, match='not found'):
        scan_test(path, 'test_missing')
