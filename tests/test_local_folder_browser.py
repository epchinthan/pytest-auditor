"""Local folder picker listings: visible entries, supported files, and stable ordering."""
from web_sources import browse


# The picker lists folders before Python files and hides caches, dotfiles, and unrelated files.
def test_browse_returns_sorted_visible_python_files_and_directories(tmp_path):
    (tmp_path / 'nested').mkdir()
    (tmp_path / '.git').mkdir()
    (tmp_path / 'node_modules').mkdir()
    (tmp_path / 'test_beta.py').write_text('')
    (tmp_path / 'test_alpha.py').write_text('')
    (tmp_path / '.hidden.py').write_text('')
    (tmp_path / 'notes.txt').write_text('')
    listing = browse(str(tmp_path))
    assert [entry['name'] for entry in listing['entries']] == ['nested', 'test_alpha.py', 'test_beta.py']
    assert [entry['directory'] for entry in listing['entries']] == [True, False, False]
    assert listing['parent'] == str(tmp_path.parent)
