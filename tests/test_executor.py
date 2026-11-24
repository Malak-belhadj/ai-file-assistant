"""Tests for the Executor: confirmations, error translation, dispatch."""

import pytest

from fs_assistant.actions import Action
from fs_assistant.executor import Executor


@pytest.fixture
def executor(ops):
    return Executor(ops)


def test_create_file_and_directory(executor, workspace, say_yes):
    assert executor.execute(Action("create_directory", path="projects"), say_yes).success
    assert executor.execute(Action("create_file", path="projects/main.py"), say_yes).success
    assert (workspace.root / "projects" / "main.py").is_file()
    assert say_yes.questions == []            # no confirmation needed for new items


def test_delete_requires_confirmation_and_yes_deletes(executor, workspace, say_yes):
    (workspace.root / "old.txt").write_text("x")
    result = executor.execute(Action("delete_file", path="old.txt"), say_yes)
    assert result.success
    assert len(say_yes.questions) == 1
    assert "delete 'old.txt'" in say_yes.questions[0]
    assert not (workspace.root / "old.txt").exists()


def test_delete_cancelled_when_user_says_no(executor, workspace, say_no):
    (workspace.root / "keep.txt").write_text("x")
    result = executor.execute(Action("delete_file", path="keep.txt"), say_no)
    assert not result.success
    assert "Cancelled" in result.message
    assert (workspace.root / "keep.txt").exists()


def test_delete_missing_file_does_not_ask(executor, say_yes):
    result = executor.execute(Action("delete_file", path="ghost.txt"), say_yes)
    assert not result.success
    assert "does not exist" in result.message
    assert say_yes.questions == []


def test_delete_folder_is_refused_without_asking(executor, workspace, say_yes):
    (workspace.root / "dir").mkdir()
    result = executor.execute(Action("delete_file", path="dir"), say_yes)
    assert not result.success
    assert say_yes.questions == []
    assert (workspace.root / "dir").is_dir()


def test_overwrite_existing_file_needs_confirmation(executor, workspace, say_no, say_yes):
    (workspace.root / "a.txt").write_text("original")
    result = executor.execute(Action("create_file", path="a.txt", content="new"), say_no)
    assert not result.success and "Cancelled" in result.message
    assert (workspace.root / "a.txt").read_text() == "original"

    result = executor.execute(Action("create_file", path="a.txt", content="new"), say_yes)
    assert result.success and "overwritten" in result.message
    assert (workspace.root / "a.txt").read_text() == "new"


def test_rename_onto_existing_file_needs_confirmation(executor, workspace, say_no):
    (workspace.root / "a.txt").write_text("A")
    (workspace.root / "b.txt").write_text("B")
    result = executor.execute(Action("rename_file", path="a.txt", new_name="b.txt"), say_no)
    assert not result.success
    assert len(say_no.questions) == 1
    assert (workspace.root / "a.txt").exists() and (workspace.root / "b.txt").read_text() == "B"


def test_duplicate_directory_is_an_error_not_a_crash(executor, say_yes):
    executor.execute(Action("create_directory", path="d"), say_yes)
    result = executor.execute(Action("create_directory", path="d"), say_yes)
    assert not result.success and "already exists" in result.message


def test_path_traversal_returns_error(executor, say_yes, tmp_path):
    result = executor.execute(Action("create_file", path="../../evil.txt"), say_yes)
    assert not result.success
    assert "outside the workspace" in result.message
    assert not (tmp_path / "evil.txt").exists()


def test_list_and_count(executor, workspace, say_yes):
    (workspace.root / "a.txt").write_text("")
    listing = executor.execute(Action("list_directory", path="."), say_yes)
    assert listing.details == ["a.txt"]
    count = executor.execute(Action("count_files", path="."), say_yes)
    assert count.message.startswith("There is 1 file")


def test_clarify_and_unsupported(executor, say_yes):
    clarify = executor.execute(Action("clarify", question="Which file?"), say_yes)
    assert clarify.success and clarify.message == "Which file?"
    unsupported = executor.execute(Action("unsupported", message="I can't browse the web."), say_yes)
    assert not unsupported.success and "I can't browse the web." in unsupported.message


def test_unknown_action_is_rejected(executor, say_yes):
    result = executor.execute(Action("format_disk", path="."), say_yes)
    assert not result.success and "not supported" in result.message


def test_create_directory_with_files(executor, workspace, say_yes):
    result = executor.execute(Action("create_directory", path="m", files=["a", "b.txt"]), say_yes)
    assert result.success
    assert result.message == "Folder 'm' is ready with 2 new file(s)."
    assert (workspace.root / "m" / "a").is_file() and (workspace.root / "m" / "b.txt").is_file()


def test_add_files_to_existing_folder_and_skip_existing(executor, workspace, say_no):
    (workspace.root / "m").mkdir()
    (workspace.root / "m" / "a").write_text("keep")
    result = executor.execute(Action("create_directory", path="m", files=["a", "b"]), say_no)
    assert not result.success                      # 'a' existed and overwrite was refused
    assert "1 of 2" in result.message
    assert (workspace.root / "m" / "a").read_text() == "keep"
    assert (workspace.root / "m" / "b").is_file()


def test_folder_with_files_cannot_escape(executor, tmp_path, say_yes):
    result = executor.execute(Action("create_directory", path="m", files=["../../evil.txt"]), say_yes)
    assert not (tmp_path / "evil.txt").exists()
    assert "Error" in " ".join(result.details)
