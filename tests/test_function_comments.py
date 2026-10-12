"""Function comments are detected around decorators without matching strings."""
import pytest

from scanning.scanner import scan_file, scan_test


# Exercise multiline decorators and comments on either side of them.
@pytest.mark.parametrize('prefix', [
    '# Explain the behavior.\n',
    '# Explain the behavior.\n@pytest.mark.parametrize("value", [1, 2])\n',
    '@pytest.mark.parametrize("value", [1, 2])\n# Explain the behavior.\n',
    '@pytest.mark.unit\n# Explain the behavior.\n@pytest.mark.parametrize("value", [1, 2])\n',
    '# Explain the behavior.\n@pytest.mark.parametrize(\n    "value",\n    [1, 2],\n)\n',
], ids=['plain', 'before-decorator', 'after-decorator', 'between-decorators', 'multiline'])
def test_function_comment_is_accepted(write_test_file, prefix):
    path = write_test_file('import pytest\n' + prefix + 'def test_value(value):\n    assert value > 0\n')
    report = scan_file(path)
    assert not any(i.code == 'DOC01' for f in report.files for i in f.issues)


# A body comment or a docstring does not replace the requested preceding comment.
@pytest.mark.parametrize('source', [
    'def test_value():\n    assert 1 + 1 == 2\n',
    'def test_value():\n    # Body comment.\n    assert 1 + 1 == 2\n',
    'def test_value():\n    """Docstring."""\n    assert 1 + 1 == 2\n',
    'import pytest\n@pytest.mark.parametrize("value", [1, 2])\ndef test_value(value):\n    assert value > 0\n',
    'text = "# Not a comment"\ndef test_value():\n    assert 1 + 1 == 2\n',
], ids=['missing', 'body-only', 'docstring-only', 'decorated-missing', 'string'])
@pytest.mark.parametrize('focused', [False, True], ids=['file', 'single-test'])
def test_missing_comment_is_reported_in_file_and_focused_scans(write_test_file, source, focused):
    path = write_test_file(source)
    report = scan_test(path, 'test_value') if focused else scan_file(path)
    assert any(i.code == 'DOC01' for f in report.files for i in f.issues)


# Helper and async function definitions follow the same comment placement rules.
def test_helper_and_async_comments_are_checked(write_test_file):
    path = write_test_file('def helper():\n    return 1\n\n# Explain async verification.\nasync def test_value():\n    assert helper() == 1\n')
    report = scan_file(path)
    findings = [i for f in report.files for i in f.issues if i.code == 'DOC01']
    assert len(findings) == 1
    assert findings[0].line == 1
