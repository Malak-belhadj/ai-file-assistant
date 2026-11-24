"""Workspace sandbox: turns a user/model path into a SAFE absolute path.

Every filesystem operation must call `Workspace.resolve()` first. It
guarantees that the final path is inside the workspace folder (by default
your user folder, e.g. C:\\Users\\MALAK), so the language model can never
touch system files such as C:\\Windows.

Friendly folder names are understood: "Desktop/m", "Documents/report.txt"
and "Downloads" are mapped to your REAL Desktop, Documents and Downloads
folders, even when Windows keeps them inside OneDrive.

Blocked examples:
    "../secret.txt"            -> escapes the workspace
    "C:\\Windows\\system.ini"  -> absolute path
    "/etc/passwd"              -> absolute path
    "AppData/..."              -> protected program-settings folder
    "CON", "nul.txt"           -> reserved device names on Windows
    "bad:name?.txt"            -> characters Windows does not allow
"""

from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath

# Characters Windows forbids in file names (we block them on every OS so the
# project behaves the same on all team members' computers).
INVALID_CHARS = set('<>:"|?*')

# Reserved device names on Windows (with or without an extension).
RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# Top-level folders the assistant must never touch (program settings etc.).
DEFAULT_PROTECTED = {"appdata", "application data", "local settings"}

_DRIVE_PATTERN = re.compile(r"^[a-zA-Z]:")

# Windows registry names of the "known folders" we support as aliases.
_WINDOWS_SHELL_FOLDERS = {
    "desktop": "Desktop",
    "documents": "Personal",
    "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "pictures": "My Pictures",
    "music": "My Music",
    "videos": "My Video",
}


class WorkspaceError(Exception):
    """Raised when a path is unsafe or invalid. The message is user-friendly."""


def detect_known_folders() -> dict[str, Path]:
    """Return the real locations of Desktop, Documents, Downloads...

    On Windows these can be moved (for example into OneDrive), so we read
    them from the registry. On other systems we use ~/Desktop etc.
    """
    home = Path.home()
    folders = {name: home / name.capitalize() for name in _WINDOWS_SHELL_FOLDERS}
    if os.name == "nt":
        try:
            import winreg

            key_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                for alias, value_name in _WINDOWS_SHELL_FOLDERS.items():
                    try:
                        raw, _type = winreg.QueryValueEx(key, value_name)
                        folders[alias] = Path(os.path.expandvars(raw))
                    except OSError:
                        pass
        except OSError:
            pass
    return folders


class Workspace:
    """A folder that the assistant is allowed to modify."""

    def __init__(self, root: Path | str, aliases: dict[str, Path] | None = None,
                 protected: set[str] | None = None):
        self.root = Path(root).resolve()
        if aliases is None:
            aliases = detect_known_folders()
        # Keep only aliases that point inside the workspace (safety first).
        self.aliases: dict[str, Path] = {}
        for name, path in aliases.items():
            try:
                resolved = Path(path).resolve()
            except OSError:
                continue
            if resolved != self.root and resolved.is_relative_to(self.root):
                self.aliases[name.lower()] = resolved
        self.protected = {p.lower() for p in (DEFAULT_PROTECTED if protected is None else protected)}

    def ensure_exists(self) -> None:
        """Create the workspace folder if it does not exist yet."""
        self.root.mkdir(parents=True, exist_ok=True)

    # -- validation helpers -------------------------------------------------
    @staticmethod
    def validate_name(name: str) -> None:
        """Check ONE path component (a single file or folder name)."""
        if name in ("", "."):
            raise WorkspaceError("A file or folder name cannot be empty.")
        if name == "..":
            raise WorkspaceError("'..' is not allowed: paths cannot point outside the workspace.")
        bad = sorted(set(name) & INVALID_CHARS)
        if bad:
            raise WorkspaceError(
                f"The name '{name}' contains characters that are not allowed: {' '.join(bad)}"
            )
        if any(ord(ch) < 32 for ch in name):
            raise WorkspaceError(f"The name '{name}' contains control characters.")
        if name != name.rstrip(" ."):
            raise WorkspaceError(f"The name '{name}' cannot end with a space or a dot.")
        if name.split(".")[0].upper() in RESERVED_NAMES:
            raise WorkspaceError(f"'{name}' is a reserved name on Windows.")

    def resolve(self, user_path: str, allow_root: bool = True) -> Path:
        """Return the absolute, safe path for `user_path`.

        Args:
            user_path: relative path given by the model, e.g. "Desktop/m/a.txt".
                       "" or "." means the workspace root.
            allow_root: if False, the workspace root itself is rejected
                        (you cannot rename or delete the workspace).
        Raises:
            WorkspaceError: if the path is invalid or outside the workspace.
        """
        if user_path is None:
            user_path = ""
        text = str(user_path).strip().replace("\\", "/")

        # Remove a leading "./" and a leading "<workspace name>/" that small
        # models sometimes add (the user sees the folder name in the banner).
        while text.startswith("./"):
            text = text[2:]
        root_name = self.root.name.lower()
        if root_name and text.lower() in (root_name, root_name + "/"):
            text = ""
        elif root_name and text.lower().startswith(root_name + "/"):
            text = text[len(self.root.name) + 1:]

        if text.startswith("/") or text.startswith("~") or _DRIVE_PATTERN.match(text):
            raise WorkspaceError(
                f"Absolute paths like '{user_path}' are not allowed. "
                f"Use a path inside {self.root}, e.g. 'Desktop/notes.txt'."
            )

        parts = [p for p in PurePosixPath(text).parts if p not in ("", ".")]
        for part in parts:
            self.validate_name(part)

        if parts and parts[0].lower() in self.protected:
            raise WorkspaceError(f"'{parts[0]}' is a protected system folder.")

        base = self.root
        if parts and parts[0].lower() in self.aliases:
            base = self.aliases[parts[0].lower()]   # e.g. "Desktop" -> OneDrive\Desktop
            parts = parts[1:]

        candidate = base.joinpath(*parts) if parts else base
        resolved = candidate.resolve()     # also follows symbolic links

        if resolved != self.root and not resolved.is_relative_to(self.root):
            raise WorkspaceError(f"'{user_path}' points outside the workspace ({self.root}).")
        if not allow_root and resolved == self.root:
            raise WorkspaceError("This operation cannot be applied to the workspace itself.")
        return resolved

    def relative(self, path: Path) -> str:
        """Display a path relative to the workspace ('.' for the root).

        Known folders are shown by their friendly name ("Desktop/m").
        """
        resolved = Path(path).resolve()
        for name, alias_path in self.aliases.items():
            if resolved == alias_path or resolved.is_relative_to(alias_path):
                rest = resolved.relative_to(alias_path).as_posix()
                label = name.capitalize()
                return label if rest == "." else f"{label}/{rest}"
        try:
            rel = resolved.relative_to(self.root)
        except ValueError:
            return str(path)
        text = rel.as_posix()
        return text if text else "."
