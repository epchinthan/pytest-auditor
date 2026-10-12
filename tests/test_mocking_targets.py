"""Patch target warnings distinguish dotted strings from object attributes."""
import pytest

from scanning.scanner import scan_file


@pytest.mark.parametrize('calls,expected', [
    ("monkeypatch.setattr(module, 'first', replacement)\n    monkeypatch.setattr(module, 'second', replacement)", set()),
    ("monkeypatch.setattr('web_server.audit', replacement)", set()),
    ("mocker.patch.object(module, 'first')", set()),
    ("mocker.patch('web_server.audit')", set()),
    ("mocker.patch('audit')", {'MK06'}),
    ("mocker.patch('web_server.audit')\n    mocker.patch('web_server.audit')", {'MK07'}),
], ids=['object-setattr', 'string-setattr', 'patch-object', 'dotted-target',
        'invalid-target', 'duplicate-target'])
def test_patch_target_diagnostics(write_test_file, calls, expected):
    path = write_test_file(
        'def test_target(monkeypatch, mocker, module, replacement):\n    '
        + calls + '\n    assert replacement is not None\n'
    )
    report = scan_file(path)
    codes = {issue.code for file in report.files for issue in file.issues
             if issue.code in {'MK06', 'MK07'}}
    assert codes == expected
