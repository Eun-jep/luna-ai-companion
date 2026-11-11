"""paths.py: user data lives outside the project; migration moves, never overwrites, and never runs against the real data in a test."""
import importlib
import os

from luna import paths


def test_data_dir_is_not_the_project_folder():
    assert paths.DATA_DIR != paths.ROOT
    assert paths.ROOT not in paths.DATA_DIR.parents


def test_under_test_is_detected():
    assert paths.under_test()


def test_default_dir_in_tests_is_temporary(monkeypatch):
    monkeypatch.delenv('LUNA_DATA_DIR', raising=False)
    reloaded = importlib.reload(paths)
    assert 'luna-data-' in reloaded.DATA_DIR.name
    assert reloaded.DATA_DIR.is_dir()


def test_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv('LUNA_DATA_DIR', str(tmp_path / 'mine'))
    reloaded = importlib.reload(paths)
    assert reloaded.DATA_DIR == tmp_path / 'mine'
    assert reloaded.data_file('memory.json') == tmp_path / 'mine' / 'memory.json'
    monkeypatch.delenv('LUNA_DATA_DIR')
    importlib.reload(paths)


def test_migrate_moves_files_and_folders(tmp_path):
    old, new = tmp_path / 'old', tmp_path / 'new'
    old.mkdir()
    (old / 'memory.json').write_text('{"a": 1}', encoding='utf-8')
    (old / 'memory-backups').mkdir()
    (old / 'memory-backups' / 'b.json').write_text('{}', encoding='utf-8')
    (old / 'app.py').write_text('code', encoding='utf-8')   # not user data: stays
    moved = paths.migrate(old, new)
    assert set(moved) == {'memory.json', 'memory-backups'}
    assert (new / 'memory.json').read_text(encoding='utf-8') == '{"a": 1}'
    assert (new / 'memory-backups' / 'b.json').is_file()
    assert (old / 'app.py').is_file() and not (old / 'memory.json').exists()


def test_migrate_never_overwrites(tmp_path):
    old, new = tmp_path / 'old', tmp_path / 'new'
    old.mkdir()
    new.mkdir()
    (old / 'keys.dat').write_bytes(b'OLD')
    (new / 'keys.dat').write_bytes(b'NEW')
    assert paths.migrate(old, new) == []
    assert (new / 'keys.dat').read_bytes() == b'NEW'
    assert (old / 'keys.dat').read_bytes() == b'OLD'


def test_migrate_without_target_never_touches_real_data_in_a_test(tmp_path, monkeypatch):
    monkeypatch.delenv('LUNA_DATA_DIR', raising=False)
    (tmp_path / 'memory.json').write_text('{}', encoding='utf-8')
    assert paths.migrate(tmp_path) == []
    assert (tmp_path / 'memory.json').is_file()


def test_legacy_list_covers_what_the_modules_store():
    for name in ('memory.json', 'journal.jsonl', 'keys.dat', 'providers.json', 'ui-state.json', 'actions.json', 'songs', 'edit_backups'):
        assert name in paths.LEGACY
    assert os.sep not in ''.join(paths.LEGACY)
