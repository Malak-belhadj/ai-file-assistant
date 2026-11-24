"""Unit tests for the workspace sandbox (path safety)."""

import os

import pytest

from fs_assistant.workspace import Workspace, WorkspaceError


def test_simple_relative_path_stays_inside(workspace):
    assert workspace.resolve("main.py") == workspace.root / "main.py"


def test_nested_path_and_backslashes(workspace):
    expected = workspace.root / "projects" / "src" / "app.py"
    assert workspace.resolve("projects/src/app.py") == expected
    assert workspace.resolve("projects\\src\\app.py") == expected


def test_dot_and_empty_mean_root(workspace):
    assert workspace.resolve(".") == workspace.root
    assert workspace.resolve("") == workspace.root
    assert workspace.resolve("./") == workspace.root


def test_workspace_prefix_added_by_model_is_removed(workspace):
    assert workspace.resolve("workspace/main.py") == workspace.root / "main.py"
    assert workspace.resolve("workspace") == workspace.root


@pytest.mark.parametrize("bad", [
    "../secret.txt",
    "..",
    "projects/../../escape.txt",
    "a/b/../../../x",
])
def test_parent_traversal_is_blocked(workspace, bad):
    with pytest.raises(WorkspaceError):
        workspace.resolve(bad)


@pytest.mark.parametrize("bad", [
    "/etc/passwd",
    "\\Windows\\system.ini",
    "C:\\Windows\\system.ini",
    "c:/Users/someone/file.txt",
    "~/notes.txt",
])
def test_absolute_paths_are_blocked(workspace, bad):
    with pytest.raises(WorkspaceError):
        workspace.resolve(bad)


@pytest.mark.parametrize("bad", ["bad:name.txt", "what?.txt", "a*b", "x|y", "<x>", 'q"uote'])
def test_invalid_characters_are_blocked(workspace, bad):
    with pytest.raises(WorkspaceError):
        workspace.resolve(bad)


@pytest.mark.parametrize("bad", ["CON", "nul.txt", "com1", "LPT9.log", "aux"])
def test_windows_reserved_names_are_blocked(workspace, bad):
    with pytest.raises(WorkspaceError):
        workspace.resolve(bad)


@pytest.mark.parametrize("bad", ["name.", "folder /x.txt", "folder./x.txt"])
def test_trailing_dot_or_space_is_blocked(workspace, bad):
    with pytest.raises(WorkspaceError):
        workspace.resolve(bad)


def test_surrounding_whitespace_is_trimmed(workspace):
    assert workspace.resolve("  notes.txt  ") == workspace.root / "notes.txt"


def test_root_rejected_when_not_allowed(workspace):
    with pytest.raises(WorkspaceError):
        workspace.resolve(".", allow_root=False)


@pytest.mark.skipif(os.name == "nt", reason="creating symlinks needs admin rights on Windows")
def test_symlink_pointing_outside_is_blocked(workspace, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace.root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(WorkspaceError):
        workspace.resolve("link/file.txt")


def test_relative_display(workspace):
    assert workspace.relative(workspace.root) == "."
    assert workspace.relative(workspace.root / "a" / "b.txt") == "a/b.txt"


def test_ensure_exists_creates_folder(tmp_path):
    ws = Workspace(tmp_path / "new_ws")
    assert not ws.root.exists()
    ws.ensure_exists()
    assert ws.root.is_dir()


# ---- friendly folder names (Desktop, Documents...) ---------------------------
def make_home(tmp_path):
    """A fake user folder whose Desktop lives inside OneDrive (common on Windows)."""
    home = tmp_path / "home"
    desktop = home / "OneDrive" / "Desktop"
    documents = home / "Documents"
    desktop.mkdir(parents=True)
    documents.mkdir(parents=True)
    ws = Workspace(home, aliases={"desktop": desktop, "documents": documents,
                                  "outside": tmp_path / "elsewhere"})
    return ws, desktop, documents


def test_desktop_alias_points_to_real_desktop(tmp_path):
    ws, desktop, _ = make_home(tmp_path)
    assert ws.resolve("Desktop/m/a.txt") == desktop / "m" / "a.txt"
    assert ws.resolve("desktop") == desktop          # case-insensitive


def test_relative_uses_friendly_name(tmp_path):
    ws, desktop, documents = make_home(tmp_path)
    assert ws.relative(desktop / "m" / "a.txt") == "Desktop/m/a.txt"
    assert ws.relative(desktop) == "Desktop"
    assert ws.relative(documents / "r.txt") == "Documents/r.txt"


def test_alias_outside_workspace_is_ignored(tmp_path):
    ws, _, _ = make_home(tmp_path)
    assert "outside" not in ws.aliases
    assert ws.resolve("outside/x.txt") == ws.root / "outside" / "x.txt"


@pytest.mark.parametrize("bad", ["AppData/Roaming/evil.txt", "appdata", "Local Settings/x"])
def test_protected_system_folders_are_blocked(tmp_path, bad):
    ws, _, _ = make_home(tmp_path)
    with pytest.raises(WorkspaceError):
        ws.resolve(bad)


def test_cannot_escape_through_alias(tmp_path):
    ws, _, _ = make_home(tmp_path)
    with pytest.raises(WorkspaceError):
        ws.resolve("Desktop/../../../secret.txt")
