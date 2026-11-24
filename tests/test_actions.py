"""Unit tests for validation of the model's JSON (the shared contract)."""

import pytest

from fs_assistant.actions import (
    ALLOWED_ACTIONS,
    ACTION_JSON_SCHEMA,
    Action,
    ActionValidationError,
    MissingFieldError,
    validate_action,
)


def test_valid_create_directory():
    action = validate_action({"action": "create_directory", "path": "projects"})
    assert action == Action(action="create_directory", path="projects")


def test_action_name_is_normalised():
    assert validate_action({"action": " Create_File ", "path": "a.txt"}).action == "create_file"


def test_irrelevant_empty_fields_are_ignored():
    data = {"action": "create_file", "path": "a.txt", "new_name": "", "question": "", "recursive": False}
    assert validate_action(data).path == "a.txt"


def test_list_and_count_default_to_root():
    assert validate_action({"action": "list_directory"}).path == "."
    assert validate_action({"action": "count_files", "path": ""}).path == "."


def test_recursive_flag_accepts_bool_and_bool_strings():
    assert validate_action({"action": "count_files", "recursive": True}).recursive is True
    assert validate_action({"action": "count_files", "recursive": "true"}).recursive is True
    assert validate_action({"action": "count_files", "recursive": "false"}).recursive is False


@pytest.mark.parametrize("bad", [None, "text", 42, ["create_file"]])
def test_non_object_is_rejected(bad):
    with pytest.raises(ActionValidationError):
        validate_action(bad)


def test_missing_action_is_rejected():
    with pytest.raises(ActionValidationError):
        validate_action({"path": "a.txt"})


@pytest.mark.parametrize("name", ["run_command", "shell", "execute", "delete_directory", "rm -rf"])
def test_unknown_actions_are_rejected(name):
    with pytest.raises(ActionValidationError):
        validate_action({"action": name, "path": "x"})


def test_wrong_field_type_is_rejected():
    with pytest.raises(ActionValidationError):
        validate_action({"action": "create_file", "path": ["a", "b"]})
    with pytest.raises(ActionValidationError):
        validate_action({"action": "count_files", "recursive": "maybe"})


def test_too_long_path_is_rejected():
    with pytest.raises(ActionValidationError):
        validate_action({"action": "create_file", "path": "a" * 500})


@pytest.mark.parametrize("data, field", [
    ({"action": "create_file"}, "path"),
    ({"action": "create_directory", "path": "  "}, "path"),
    ({"action": "rename_file", "path": "a.txt"}, "new_name"),
    ({"action": "delete_file"}, "path"),
])
def test_missing_required_field_gives_a_question(data, field):
    with pytest.raises(MissingFieldError) as info:
        validate_action(data)
    assert info.value.field_name == field
    assert info.value.question.endswith("?")


def test_schema_lists_exactly_the_allowed_actions():
    assert ACTION_JSON_SCHEMA["properties"]["action"]["enum"] == list(ALLOWED_ACTIONS)


def test_to_dict_shows_relevant_fields_only():
    assert Action("rename_file", path="a", new_name="b").to_dict() == {
        "action": "rename_file", "path": "a", "new_name": "b"}
    assert Action("clarify", question="Which?").to_dict() == {"action": "clarify", "question": "Which?"}


def test_create_directory_with_files():
    action = validate_action({"action": "create_directory", "path": "Desktop/m", "files": ["a", "b", "a", " "]})
    assert action.files == ["a", "b"]                       # duplicates and blanks removed
    assert action.to_dict() == {"action": "create_directory", "path": "Desktop/m", "files": ["a", "b"]}


def test_files_given_as_text_are_split():
    assert validate_action({"action": "create_directory", "path": "m", "files": "a.txt, b.txt"}).files == ["a.txt", "b.txt"]


def test_files_ignored_for_other_actions():
    assert validate_action({"action": "create_file", "path": "x.txt", "files": ["a"]}).files == []


def test_files_wrong_type_is_rejected():
    with pytest.raises(ActionValidationError):
        validate_action({"action": "create_directory", "path": "m", "files": [1, 2]})
