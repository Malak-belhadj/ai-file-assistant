"""Unit tests for the real filesystem operations."""

import pytest

from fs_assistant.file_ops import (
    AlreadyExistsError,
    FileOperationError,
    PathNotFoundError,
    WrongTypeError,
)


# ---- create_file -----------------------------------------------------------
def test_create_file(ops, workspace):
    result = ops.create_file("main.py")
    assert result.success
    assert result.message == "File 'main.py' created successfully."
    assert (workspace.root / "main.py").is_file()


def test_create_file_with_content(ops, workspace):
    ops.create_file("readme.md", "Hello world")
    assert (workspace.root / "readme.md").read_text(encoding="utf-8") == "Hello world"


def test_create_file_in_existing_directory(ops, workspace):
    ops.create_directory("projects")
    result = ops.create_file("projects/app.py")
    assert result.success
    assert "(Folder" not in result.message
    assert (workspace.root / "projects" / "app.py").is_file()


def test_create_file_creates_missing_parent_folders(ops, workspace):
    result = ops.create_file("src/utils/helpers.py")
    assert result.success
    assert "Folder 'src/utils' was created" in result.message
    assert (workspace.root / "src" / "utils" / "helpers.py").is_file()


def test_create_file_refuses_to_overwrite(ops, workspace):
    ops.create_file("a.txt", "original")
    with pytest.raises(AlreadyExistsError) as info:
        ops.create_file("a.txt", "new")
    assert info.value.path == "a.txt"
    assert (workspace.root / "a.txt").read_text(encoding="utf-8") == "original"


def test_create_file_overwrite_when_allowed(ops, workspace):
    ops.create_file("a.txt", "original")
    result = ops.create_file("a.txt", "new", overwrite=True)
    assert "overwritten" in result.message
    assert (workspace.root / "a.txt").read_text(encoding="utf-8") == "new"


def test_create_file_where_folder_exists(ops):
    ops.create_directory("docs")
    with pytest.raises(WrongTypeError):
        ops.create_file("docs")


def test_create_file_inside_a_file_is_rejected(ops):
    ops.create_file("notes.txt")
    with pytest.raises(WrongTypeError):
        ops.create_file("notes.txt/inner.txt")


def test_create_file_outside_workspace_is_rejected(ops, tmp_path):
    with pytest.raises(FileOperationError):
        ops.create_file("../escape.txt")
    assert not (tmp_path / "escape.txt").exists()


# ---- create_directory --------------------------------------------------------
def test_create_directory(ops, workspace):
    result = ops.create_directory("projects")
    assert result.message == "Directory 'projects' created successfully."
    assert (workspace.root / "projects").is_dir()


def test_create_nested_directory(ops, workspace):
    ops.create_directory("a/b/c")
    assert (workspace.root / "a" / "b" / "c").is_dir()


def test_create_duplicate_directory(ops):
    ops.create_directory("projects")
    with pytest.raises(AlreadyExistsError):
        ops.create_directory("projects")


def test_create_directory_with_file_name_taken(ops):
    ops.create_file("data")
    with pytest.raises(AlreadyExistsError):
        ops.create_directory("data")


# ---- list_directory ----------------------------------------------------------
def test_list_empty_workspace(ops):
    result = ops.list_directory(".")
    assert result.success
    assert result.message == "The workspace is empty."
    assert result.details == []


def test_list_shows_folders_first_then_files(ops):
    ops.create_file("b.txt")
    ops.create_file("A.txt")
    ops.create_directory("zeta")
    result = ops.list_directory(".")
    assert result.details == ["zeta/", "A.txt", "b.txt"]
    assert "2 files, 1 folder" in result.message


def test_list_subdirectory(ops):
    ops.create_file("projects/main.py")
    result = ops.list_directory("projects")
    assert result.details == ["main.py"]


def test_list_missing_directory(ops):
    with pytest.raises(PathNotFoundError):
        ops.list_directory("nope")


def test_list_a_file_is_rejected(ops):
    ops.create_file("x.txt")
    with pytest.raises(WrongTypeError):
        ops.list_directory("x.txt")


# ---- count_files -------------------------------------------------------------
def test_count_non_recursive_ignores_folders_and_subfolders(ops):
    ops.create_file("main.py")
    ops.create_directory("projects")
    ops.create_file("projects/inner.py")
    result = ops.count_files(".", recursive=False)
    assert result.message == "There is 1 file in the workspace (not counting sub-folders)."


def test_count_recursive(ops):
    ops.create_file("main.py")
    ops.create_file("projects/a.py")
    ops.create_file("projects/deep/b.py")
    result = ops.count_files(".", recursive=True)
    assert result.message == "There are 3 files in the workspace (including sub-folders)."


def test_count_empty_folder(ops):
    ops.create_directory("empty")
    assert ops.count_files("empty").message.startswith("There are 0 files in 'empty'")


def test_count_missing_folder(ops):
    with pytest.raises(PathNotFoundError):
        ops.count_files("missing")


# ---- rename_file -------------------------------------------------------------
def test_rename_in_same_folder(ops, workspace):
    ops.create_file("projects/a.py", "x")
    result = ops.rename_file("projects/a.py", "b.py")
    assert result.message == "File 'projects/a.py' renamed to 'projects/b.py' successfully."
    assert (workspace.root / "projects" / "b.py").read_text(encoding="utf-8") == "x"
    assert not (workspace.root / "projects" / "a.py").exists()


def test_rename_missing_file(ops):
    with pytest.raises(PathNotFoundError):
        ops.rename_file("ghost.txt", "x.txt")


def test_rename_folder_is_rejected(ops):
    ops.create_directory("dir")
    with pytest.raises(WrongTypeError):
        ops.rename_file("dir", "dir2")


def test_rename_refuses_to_overwrite(ops, workspace):
    ops.create_file("a.txt", "A")
    ops.create_file("b.txt", "B")
    with pytest.raises(AlreadyExistsError):
        ops.rename_file("a.txt", "b.txt")
    assert (workspace.root / "b.txt").read_text(encoding="utf-8") == "B"


def test_rename_overwrite_when_allowed(ops, workspace):
    ops.create_file("a.txt", "A")
    ops.create_file("b.txt", "B")
    ops.rename_file("a.txt", "b.txt", overwrite=True)
    assert (workspace.root / "b.txt").read_text(encoding="utf-8") == "A"
    assert not (workspace.root / "a.txt").exists()


def test_rename_to_outside_workspace_is_rejected(ops, tmp_path):
    ops.create_file("a.txt")
    with pytest.raises(FileOperationError):
        ops.rename_file("a.txt", "../stolen.txt")
    assert not (tmp_path / "stolen.txt").exists()


def test_rename_to_invalid_name_is_rejected(ops):
    ops.create_file("a.txt")
    with pytest.raises(FileOperationError):
        ops.rename_file("a.txt", "bad?.txt")


def test_rename_to_same_name(ops):
    ops.create_file("a.txt")
    with pytest.raises(FileOperationError):
        ops.rename_file("a.txt", "a.txt")


# ---- delete_file -------------------------------------------------------------
def test_delete_file(ops, workspace):
    ops.create_file("old.log")
    result = ops.delete_file("old.log")
    assert result.message == "File 'old.log' deleted successfully."
    assert not (workspace.root / "old.log").exists()


def test_delete_missing_file(ops):
    with pytest.raises(PathNotFoundError):
        ops.delete_file("ghost.txt")


def test_delete_folder_is_refused(ops, workspace):
    ops.create_directory("keep")
    with pytest.raises(WrongTypeError):
        ops.delete_file("keep")
    assert (workspace.root / "keep").is_dir()


def test_delete_outside_workspace_is_refused(ops, tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_text("important")
    with pytest.raises(FileOperationError):
        ops.delete_file("../victim.txt")
    assert victim.exists()


def test_delete_workspace_root_is_refused(ops):
    with pytest.raises(FileOperationError):
        ops.delete_file(".")
