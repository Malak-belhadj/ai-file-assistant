"""Real filesystem operations, always restricted to the workspace.

Each method:
  1. converts the user path into a safe absolute path with Workspace.resolve()
  2. checks the situation (exists? is it a file? ...)
  3. performs the operation with Python's standard library (pathlib)
  4. returns an ActionResult with a clear message, OR raises a
     FileOperationError subclass with a user-friendly message.

No shell commands are ever executed.
"""

from __future__ import annotations

import os
from pathlib import Path

from .actions import ActionResult
from .config import MAX_LIST_ENTRIES, MAX_RECURSIVE_COUNT
from .workspace import Workspace, WorkspaceError


class FileOperationError(Exception):
    """Base class for all expected filesystem problems."""


class PathNotFoundError(FileOperationError):
    pass


class AlreadyExistsError(FileOperationError):
    """Raised when a target already exists. `path` is the relative path."""

    def __init__(self, message: str, path: str, is_file: bool):
        super().__init__(message)
        self.path = path
        self.is_file = is_file


class WrongTypeError(FileOperationError):
    """A file was expected but a folder was found, or the other way round."""


class FileSystemOperations:
    """All supported operations. Create one instance per workspace."""

    def __init__(self, workspace: Workspace):
        self.workspace = workspace

    # -- helpers --------------------------------------------------------------
    def _safe(self, user_path: str, allow_root: bool = True) -> Path:
        try:
            return self.workspace.resolve(user_path, allow_root=allow_root)
        except WorkspaceError as exc:
            raise FileOperationError(str(exc)) from exc

    def _rel(self, path: Path) -> str:
        return self.workspace.relative(path)

    @staticmethod
    def _plural(count: int, word: str) -> str:
        return f"{count} {word}" if count == 1 else f"{count} {word}s"

    def file_exists(self, user_path: str) -> bool:
        """True if `user_path` is an existing FILE inside the workspace."""
        return self._safe(user_path, allow_root=False).is_file()

    # -- operations -----------------------------------------------------------
    def create_file(self, user_path: str, content: str = "", overwrite: bool = False) -> ActionResult:
        """Create a file (and any missing parent folders).

        Raises AlreadyExistsError if the file exists and overwrite is False.
        """
        target = self._safe(user_path, allow_root=False)
        rel = self._rel(target)

        if target.is_dir():
            raise WrongTypeError(f"'{rel}' is a folder, not a file.")
        if target.exists() and not overwrite:
            raise AlreadyExistsError(f"A file named '{rel}' already exists.", rel, True)

        # A parent path component might be an existing FILE, e.g. "notes.txt/a.txt".
        for parent in reversed(target.parents):
            if parent.is_relative_to(self.workspace.root) and parent.is_file():
                raise WrongTypeError(f"'{self._rel(parent)}' is a file, so it cannot contain other files.")

        created_parents = [p for p in target.parents
                           if p.is_relative_to(self.workspace.root) and not p.exists()]
        target.parent.mkdir(parents=True, exist_ok=True)
        existed = target.exists()
        target.write_text(content, encoding="utf-8")

        if existed:
            message = f"File '{rel}' overwritten successfully."
        else:
            message = f"File '{rel}' created successfully."
        if created_parents:
            folder = self._rel(target.parent)
            message += f" (Folder '{folder}' was created for it.)"
        return ActionResult(True, message)

    def create_directory(self, user_path: str, exist_ok: bool = False) -> ActionResult:
        """Create a folder (and missing parents). With exist_ok=True an
        existing folder is accepted, so files can be added to it."""
        target = self._safe(user_path, allow_root=False)
        rel = self._rel(target)
        if target.is_dir():
            if exist_ok:
                return ActionResult(True, f"Directory '{rel}' already exists.")
            raise AlreadyExistsError(f"A folder named '{rel}' already exists.", rel, False)
        if target.exists():
            raise AlreadyExistsError(f"A file named '{rel}' already exists.", rel, True)
        for parent in target.parents:
            if parent.is_relative_to(self.workspace.root) and parent.is_file():
                raise WrongTypeError(f"'{self._rel(parent)}' is a file, so it cannot contain folders.")
        target.mkdir(parents=True)
        return ActionResult(True, f"Directory '{rel}' created successfully.")

    def list_directory(self, user_path: str = ".") -> ActionResult:
        target = self._safe(user_path)
        rel = self._rel(target)
        if not target.exists():
            raise PathNotFoundError(f"The folder '{rel}' does not exist.")
        if not target.is_dir():
            raise WrongTypeError(f"'{rel}' is a file, not a folder.")

        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        where = "the workspace" if rel == "." else f"'{rel}'"
        if not entries:
            return ActionResult(True, f"{where[0].upper() + where[1:]} is empty.")

        lines = [e.name + "/" if e.is_dir() else e.name for e in entries[:MAX_LIST_ENTRIES]]
        if len(entries) > MAX_LIST_ENTRIES:
            lines.append(f"... and {len(entries) - MAX_LIST_ENTRIES} more")
        folders = sum(1 for e in entries if e.is_dir())
        files = len(entries) - folders
        summary = (f"Contents of {where} ({self._plural(files, 'file')}, "
                   f"{self._plural(folders, 'folder')}):")
        return ActionResult(True, summary, lines)

    def count_files(self, user_path: str = ".", recursive: bool = False) -> ActionResult:
        """Count FILES (folders are not counted).

        recursive=False -> only files directly inside the folder.
        recursive=True  -> also files inside all sub-folders.
        """
        target = self._safe(user_path)
        rel = self._rel(target)
        if not target.exists():
            raise PathNotFoundError(f"The folder '{rel}' does not exist.")
        if not target.is_dir():
            raise WrongTypeError(f"'{rel}' is a file, not a folder.")

        count = 0
        stopped_early = False
        if recursive:
            seen = 0
            for _dirpath, _dirnames, filenames in os.walk(target):
                count += len(filenames)
                seen += len(filenames) + len(_dirnames)
                if seen >= MAX_RECURSIVE_COUNT:
                    stopped_early = True
                    break
        else:
            count = sum(1 for p in target.iterdir() if p.is_file())
        where = "the workspace" if rel == "." else f"'{rel}'"
        scope = "including sub-folders" if recursive else "not counting sub-folders"
        if stopped_early:
            return ActionResult(True, f"There are more than {count} files in {where} ({scope}); "
                                      "I stopped counting because the folder is very large.")
        verb = "is" if count == 1 else "are"
        return ActionResult(True, f"There {verb} {self._plural(count, 'file')} in {where} ({scope}).")

    def rename_file(self, user_path: str, new_name: str, overwrite: bool = False) -> ActionResult:
        """Rename a file. If `new_name` has no folder part, the file stays in
        the same folder ("notes.txt" -> "ideas.txt"). Raises AlreadyExistsError
        if the destination exists and overwrite is False."""
        source = self._safe(user_path, allow_root=False)
        src_rel = self._rel(source)
        if not source.exists():
            raise PathNotFoundError(f"The file '{src_rel}' does not exist.")
        if not source.is_file():
            raise WrongTypeError(f"'{src_rel}' is a folder. Only files can be renamed.")

        cleaned = new_name.strip().replace("\\", "/")
        if "/" in cleaned:
            destination = self._safe(cleaned, allow_root=False)
        else:
            try:
                Workspace.validate_name(cleaned)
            except WorkspaceError as exc:
                raise FileOperationError(str(exc)) from exc
            destination = self._safe(f"{self._rel(source.parent)}/{cleaned}", allow_root=False)
        dst_rel = self._rel(destination)

        if destination == source:
            raise FileOperationError(f"The file is already called '{src_rel}'.")
        if destination.is_dir():
            raise WrongTypeError(f"A folder named '{dst_rel}' already exists.")
        if destination.exists() and not overwrite:
            raise AlreadyExistsError(f"A file named '{dst_rel}' already exists.", dst_rel, True)
        if not destination.parent.is_dir():
            raise PathNotFoundError(f"The folder '{self._rel(destination.parent)}' does not exist.")

        source.replace(destination)
        return ActionResult(True, f"File '{src_rel}' renamed to '{dst_rel}' successfully.")

    def delete_file(self, user_path: str) -> ActionResult:
        """Delete ONE file. Folders are never deleted. The caller (Executor)
        is responsible for asking the user for confirmation first."""
        target = self._safe(user_path, allow_root=False)
        rel = self._rel(target)
        if not target.exists():
            raise PathNotFoundError(f"The file '{rel}' does not exist.")
        if not target.is_file():
            raise WrongTypeError(f"'{rel}' is a folder. For safety, only files can be deleted.")
        target.unlink()
        return ActionResult(True, f"File '{rel}' deleted successfully.")
