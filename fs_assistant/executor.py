"""Runs a validated Action using FileSystemOperations.

The Executor is the "safety gate" between the model's decision and the disk:
  * only the actions in a fixed table can run (no shell, no eval)
  * deleting a file ALWAYS requires the user's confirmation
  * overwriting an existing file ALWAYS requires the user's confirmation
  * every expected error becomes a friendly ActionResult instead of a crash

`confirm` is a function supplied by the CLI: it receives a yes/no question
and returns True only if the user explicitly agreed. Tests pass a fake one.
"""

from __future__ import annotations

from typing import Callable

from .actions import (
    CLARIFY,
    COUNT_FILES,
    CREATE_DIRECTORY,
    CREATE_FILE,
    DELETE_FILE,
    LIST_DIRECTORY,
    RENAME_FILE,
    UNSUPPORTED,
    Action,
    ActionResult,
)
from .file_ops import AlreadyExistsError, FileOperationError, FileSystemOperations

ConfirmFunction = Callable[[str], bool]


class Executor:
    def __init__(self, file_ops: FileSystemOperations):
        self.file_ops = file_ops
        self._handlers: dict[str, Callable[[Action, ConfirmFunction], ActionResult]] = {
            CREATE_FILE: self._create_file,
            CREATE_DIRECTORY: self._create_directory,
            LIST_DIRECTORY: self._list_directory,
            COUNT_FILES: self._count_files,
            RENAME_FILE: self._rename_file,
            DELETE_FILE: self._delete_file,
            CLARIFY: self._clarify,
            UNSUPPORTED: self._unsupported,
        }

    def execute(self, action: Action, confirm: ConfirmFunction) -> ActionResult:
        handler = self._handlers.get(action.action)
        if handler is None:
            return ActionResult(False, f"The action '{action.action}' is not supported.")
        try:
            return handler(action, confirm)
        except FileOperationError as exc:
            return ActionResult(False, str(exc))
        except PermissionError:
            return ActionResult(False, "Permission denied: the file may be open in another program.")
        except OSError as exc:
            return ActionResult(False, f"The operating system reported an error: {exc.strerror or exc}")

    # -- handlers -----------------------------------------------------------
    def _create_file(self, action: Action, confirm: ConfirmFunction) -> ActionResult:
        try:
            return self.file_ops.create_file(action.path, action.content)
        except AlreadyExistsError as exc:
            if not exc.is_file:
                raise
            if confirm(f"'{exc.path}' already exists. Overwrite it? Its current content will be lost."):
                return self.file_ops.create_file(action.path, action.content, overwrite=True)
            return ActionResult(False, f"Cancelled. '{exc.path}' was not changed.")

    def _create_directory(self, action: Action, confirm: ConfirmFunction) -> ActionResult:
        if not action.files:
            return self.file_ops.create_directory(action.path)

        # Folder + files in one request, e.g. "folder m with files a and b".
        folder_result = self.file_ops.create_directory(action.path, exist_ok=True)
        folder = self.file_ops.workspace.relative(
            self.file_ops.workspace.resolve(action.path, allow_root=False))
        details = [folder_result.message]
        created = 0
        for name in action.files:
            sub_action = Action(action=CREATE_FILE, path=f"{folder}/{name}")
            try:
                result = self._create_file(sub_action, confirm)
            except FileOperationError as exc:
                result = ActionResult(False, str(exc))
            created += result.success
            details.append(("" if result.success else "Error: ") + result.message)
        ok = created == len(action.files)
        summary = (f"Folder '{folder}' is ready with {created} of {len(action.files)} file(s) created."
                   if not ok else
                   f"Folder '{folder}' is ready with {created} new file(s).")
        return ActionResult(ok, summary, details)

    def _list_directory(self, action: Action, confirm: ConfirmFunction) -> ActionResult:
        return self.file_ops.list_directory(action.path)

    def _count_files(self, action: Action, confirm: ConfirmFunction) -> ActionResult:
        return self.file_ops.count_files(action.path, action.recursive)

    def _rename_file(self, action: Action, confirm: ConfirmFunction) -> ActionResult:
        try:
            return self.file_ops.rename_file(action.path, action.new_name)
        except AlreadyExistsError as exc:
            if confirm(f"'{exc.path}' already exists. Replace it with '{action.path}'?"):
                return self.file_ops.rename_file(action.path, action.new_name, overwrite=True)
            return ActionResult(False, "Cancelled. Nothing was renamed.")

    def _delete_file(self, action: Action, confirm: ConfirmFunction) -> ActionResult:
        # Check first so we never ask to confirm deleting something that is missing.
        if not self.file_ops.file_exists(action.path):
            # delete_file raises the precise error (missing / is a folder).
            return self.file_ops.delete_file(action.path)
        if confirm(f"Are you sure you want to permanently delete '{action.path}'?"):
            return self.file_ops.delete_file(action.path)
        return ActionResult(False, f"Cancelled. '{action.path}' was not deleted.")

    def _clarify(self, action: Action, confirm: ConfirmFunction) -> ActionResult:
        return ActionResult(True, action.question)

    def _unsupported(self, action: Action, confirm: ConfirmFunction) -> ActionResult:
        message = action.message or "I can't do that."
        return ActionResult(
            False,
            f"{message} I can create, list, count, rename and delete files and folders. Type 'help' for examples.",
        )
