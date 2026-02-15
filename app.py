"""tui-explorer: A yazi-inspired terminal file manager built with Textual."""

import os
import shutil
import stat
import pwd
import grp
from datetime import datetime
from pathlib import Path

from rich.markup import escape
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Footer, Header, Input, Label


def format_size(size: int) -> str:
    for unit in ("B", "K", "M", "G", "T"):
        if size < 1024:
            return f"{size:>5.1f}{unit}" if unit != "B" else f"{size:>5}{unit}"
        size /= 1024
    return f"{size:>5.1f}P"


def format_permissions(mode: int) -> str:
    perms = ""
    for who in (stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR,
                stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP,
                stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH):
        perms += "rwxrwxrwx"[len(perms)] if mode & who else "-"
    prefix = "d" if stat.S_ISDIR(mode) else "l" if stat.S_ISLNK(mode) else "-"
    return prefix + perms


class InputDialog(ModalScreen[str | None]):
    """Modal dialog with a text input field."""

    DEFAULT_CSS = """
    InputDialog {
        align: center middle;
    }
    InputDialog > Vertical {
        width: 50;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    InputDialog Label {
        margin-bottom: 1;
    }
    InputDialog Input {
        margin-bottom: 1;
    }
    InputDialog .buttons {
        height: 3;
        align-horizontal: right;
    }
    InputDialog Button {
        margin-left: 1;
    }
    """

    def __init__(self, title: str, default: str = "") -> None:
        super().__init__()
        self._title = title
        self._default = default

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._title)
            yield Input(value=self._default, id="input-field")
            with Horizontal(classes="buttons"):
                yield Button("OK", variant="primary", id="ok")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        inp = self.query_one("#input-field", Input)
        inp.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ok":
            self.dismiss(self.query_one("#input-field", Input).value.strip())
        else:
            self.dismiss(None)

    def on_input_submitted(self) -> None:
        self.dismiss(self.query_one("#input-field", Input).value.strip())

    def key_escape(self) -> None:
        self.dismiss(None)


class ConfirmDialog(ModalScreen[bool]):
    """Modal yes/no confirmation dialog."""

    DEFAULT_CSS = """
    ConfirmDialog {
        align: center middle;
    }
    ConfirmDialog > Vertical {
        width: 50;
        height: auto;
        border: thick $error;
        background: $surface;
        padding: 1 2;
    }
    ConfirmDialog Label {
        margin-bottom: 1;
    }
    ConfirmDialog .buttons {
        height: 3;
        align-horizontal: right;
    }
    ConfirmDialog Button {
        margin-left: 1;
    }
    """

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Label(self._message)
            with Horizontal(classes="buttons"):
                yield Button("Yes", variant="error", id="yes")
                yield Button("No", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def key_y(self) -> None:
        self.dismiss(True)

    def key_n(self) -> None:
        self.dismiss(False)

    def key_escape(self) -> None:
        self.dismiss(False)


class ParentPane(Widget):
    """Shows entries in the parent directory, highlighting the current dir."""

    current_dir: reactive[Path] = reactive(Path.home())
    show_hidden: reactive[bool] = reactive(True)

    DEFAULT_CSS = """
    ParentPane {
        width: 1fr;
        border-right: solid $surface-lighten-2;
        overflow-y: auto;
    }
    """

    def render_entries(self) -> str:
        parent = self.current_dir.parent
        if parent == self.current_dir:
            return str(self.current_dir)
        try:
            entries = sorted(parent.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return "[red]Permission denied[/]"
        if not self.show_hidden:
            entries = [e for e in entries if not e.name.startswith(".")]
        lines = []
        for entry in entries:
            name = escape(entry.name)
            if entry == self.current_dir:
                lines.append(f"[bold reverse] {name}/ [/]")
            elif entry.is_dir():
                lines.append(f"[bold cyan] {name}/[/]")
            else:
                lines.append(f" {name}")
        return "\n".join(lines)

    def render(self) -> str:
        return self.render_entries()

    def watch_current_dir(self) -> None:
        self.refresh()

    def watch_show_hidden(self) -> None:
        self.refresh()


class FileList(Widget):
    """Main pane: lists files in current directory with details."""

    current_dir: reactive[Path] = reactive(Path.home())
    cursor: reactive[int] = reactive(0)
    show_hidden: reactive[bool] = reactive(True)

    DEFAULT_CSS = """
    FileList {
        width: 2fr;
        overflow-y: auto;
    }
    """

    def get_entries(self) -> list[Path]:
        try:
            entries = sorted(
                self.current_dir.iterdir(),
                key=lambda p: (not p.is_dir(), p.name.lower()),
            )
        except PermissionError:
            return []
        if not self.show_hidden:
            entries = [e for e in entries if not e.name.startswith(".")]
        return entries

    def render_list(self) -> str:
        entries = self.get_entries()
        if not entries:
            return "[dim italic]  Empty directory[/]"
        lines = []
        for i, entry in enumerate(entries):
            try:
                st = entry.lstat()
                size = format_size(st.st_size)
                mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
            except OSError:
                size = "    ?"
                mtime = "               ?"

            name = escape(entry.name)
            if entry.is_dir():
                display = f"[bold cyan]{name}/[/]"
            elif entry.is_symlink():
                display = f"[magenta]{name}@[/]"
            elif os.access(entry, os.X_OK):
                display = f"[green]{name}*[/]"
            else:
                display = name

            prefix = "[reverse]" if i == self.cursor else ""
            suffix = "[/]" if i == self.cursor else ""
            lines.append(f"{prefix} {display}  [dim]{size}  {mtime}[/]{suffix}")
        return "\n".join(lines)

    def render(self) -> str:
        return self.render_list()

    def watch_current_dir(self) -> None:
        self.cursor = 0
        self.refresh()

    def watch_cursor(self) -> None:
        self.refresh()

    def watch_show_hidden(self) -> None:
        self.cursor = 0
        self.refresh()

    def selected_path(self) -> Path | None:
        entries = self.get_entries()
        if 0 <= self.cursor < len(entries):
            return entries[self.cursor]
        return None


class PreviewPane(Widget):
    """Right pane: previews selected file or directory contents."""

    preview_path: reactive[Path | None] = reactive(None)
    show_hidden: reactive[bool] = reactive(True)

    DEFAULT_CSS = """
    PreviewPane {
        width: 2fr;
        border-left: solid $surface-lighten-2;
        overflow-y: auto;
    }
    """

    MAX_PREVIEW_LINES = 80
    MAX_LINE_LEN = 200
    MAX_PREVIEW_BYTES = 64 * 1024  # 64 KB

    BINARY_EXTENSIONS = frozenset({
        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tiff", ".tif",
        ".svg", ".mp3", ".mp4", ".mkv", ".avi", ".mov", ".flac", ".wav", ".ogg",
        ".webm", ".zip", ".tar", ".gz", ".bz2", ".xz", ".zst", ".7z", ".rar",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".so", ".dylib", ".dll", ".exe", ".o", ".a", ".pyc", ".pyo",
        ".woff", ".woff2", ".ttf", ".otf", ".eot",
        ".db", ".sqlite", ".sqlite3",
        ".bin", ".dat", ".iso", ".img",
    })

    def render_preview(self) -> str:
        path = self.preview_path
        if path is None:
            return ""
        if not path.exists():
            return "[dim]Path does not exist[/]"

        # Show file/dir info header
        try:
            st = path.lstat()
            perms = format_permissions(st.st_mode)
            try:
                owner = pwd.getpwuid(st.st_uid).pw_name
            except KeyError:
                owner = str(st.st_uid)
            try:
                group = grp.getgrgid(st.st_gid).gr_name
            except KeyError:
                group = str(st.st_gid)
            size = format_size(st.st_size)
            mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            header = f"[dim]{perms}  {owner}:{group}  {size}  {mtime}[/]\n\n"
        except OSError:
            header = ""

        if path.is_dir():
            try:
                entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except PermissionError:
                return header + "[red]Permission denied[/]"
            if not self.show_hidden:
                entries = [e for e in entries if not e.name.startswith(".")]
            lines = []
            for e in entries[:50]:
                if e.is_dir():
                    lines.append(f"[bold cyan]{escape(e.name)}/[/]")
                else:
                    lines.append(escape(e.name))
            if len(entries) > 50:
                lines.append(f"[dim]... and {len(entries) - 50} more[/]")
            return header + "\n".join(lines)

        # Skip known binary extensions
        if path.suffix.lower() in self.BINARY_EXTENSIONS:
            return header + f"[dim italic]Binary file ({escape(path.suffix)})[/]"

        # Skip large files
        try:
            file_size = path.stat().st_size
        except OSError:
            file_size = 0
        if file_size > self.MAX_PREVIEW_BYTES:
            return header + f"[dim italic]File too large for preview ({format_size(file_size)})[/]"

        # Try reading as text — bail on null bytes (binary)
        try:
            raw = path.read_bytes()[:self.MAX_PREVIEW_BYTES]
            if b"\x00" in raw[:1024]:
                return header + "[dim italic]Binary file[/]"
            text = raw.decode("utf-8", errors="replace")
            lines = text.splitlines()[: self.MAX_PREVIEW_LINES]
            truncated = [ln[: self.MAX_LINE_LEN] for ln in lines]
            content = "\n".join(truncated)
            return header + escape(content)
        except Exception:
            return header + "[dim italic]Cannot read file[/]"

    def render(self) -> str:
        return self.render_preview()

    def watch_preview_path(self) -> None:
        self.refresh()

    def watch_show_hidden(self) -> None:
        self.refresh()


class StatusBar(Widget):
    """Bottom status bar showing current path and file info."""

    text: reactive[str] = reactive("")

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }
    """

    def render(self) -> str:
        return self.text


class Explorer(App):
    """A yazi-inspired three-pane terminal file manager."""

    CSS = """
    Screen {
        layout: vertical;
    }
    #panes {
        height: 1fr;
    }
    """

    TITLE = "tui-explorer"

    BINDINGS = [
        Binding("j,down", "cursor_down", "Down", show=True),
        Binding("k,up", "cursor_up", "Up", show=True),
        Binding("l,right,enter", "enter_dir", "Open", show=True),
        Binding("h,left", "parent_dir", "Back", show=True),
        Binding("g", "go_top", "Top"),
        Binding("shift+g", "go_bottom", "Bottom"),
        Binding("tilde", "go_home", "Home"),
        Binding("full_stop", "toggle_hidden", "Hidden", show=True),
        Binding("a", "create", "Create"),
        Binding("r", "rename", "Rename"),
        Binding("shift+d", "delete", "Delete"),
        Binding("q", "quit", "Quit", show=True),
    ]

    current_dir: reactive[Path] = reactive(Path.cwd())
    show_hidden: reactive[bool] = reactive(True)

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="panes"):
            yield ParentPane()
            yield FileList()
            yield PreviewPane()
        yield StatusBar()
        yield Footer()

    def on_mount(self) -> None:
        self._sync_all()

    def watch_current_dir(self) -> None:
        self._sync_all()

    def _sync_all(self) -> None:
        parent_pane = self.query_one(ParentPane)
        file_list = self.query_one(FileList)
        status_bar = self.query_one(StatusBar)

        parent_pane.current_dir = self.current_dir
        parent_pane.show_hidden = self.show_hidden
        file_list.current_dir = self.current_dir
        file_list.show_hidden = self.show_hidden
        self._update_preview()

        entries = file_list.get_entries()
        count_dirs = sum(1 for e in entries if e.is_dir())
        count_files = len(entries) - count_dirs
        status_bar.text = f" {escape(str(self.current_dir))}  \\[{count_dirs} dirs, {count_files} files]"

    def _update_preview(self) -> None:
        file_list = self.query_one(FileList)
        preview = self.query_one(PreviewPane)
        preview.show_hidden = self.show_hidden
        preview.preview_path = file_list.selected_path()

    def action_cursor_down(self) -> None:
        fl = self.query_one(FileList)
        entries = fl.get_entries()
        if fl.cursor < len(entries) - 1:
            fl.cursor += 1
            self._update_preview()

    def action_cursor_up(self) -> None:
        fl = self.query_one(FileList)
        if fl.cursor > 0:
            fl.cursor -= 1
            self._update_preview()

    def action_enter_dir(self) -> None:
        fl = self.query_one(FileList)
        selected = fl.selected_path()
        if selected and selected.is_dir():
            self.current_dir = selected

    def action_parent_dir(self) -> None:
        parent = self.current_dir.parent
        if parent != self.current_dir:
            old = self.current_dir
            self.current_dir = parent
            # Try to place cursor on the dir we just left
            fl = self.query_one(FileList)
            entries = fl.get_entries()
            for i, e in enumerate(entries):
                if e == old:
                    fl.cursor = i
                    self._update_preview()
                    break

    def action_go_top(self) -> None:
        fl = self.query_one(FileList)
        fl.cursor = 0
        self._update_preview()

    def action_go_bottom(self) -> None:
        fl = self.query_one(FileList)
        entries = fl.get_entries()
        if entries:
            fl.cursor = len(entries) - 1
            self._update_preview()

    def action_toggle_hidden(self) -> None:
        self.show_hidden = not self.show_hidden
        self._sync_all()

    def action_go_home(self) -> None:
        self.current_dir = Path.home()

    def _refresh_view(self) -> None:
        fl = self.query_one(FileList)
        self._sync_all()
        entries = fl.get_entries()
        if fl.cursor >= len(entries):
            fl.cursor = max(0, len(entries) - 1)
        self._update_preview()

    def action_create(self) -> None:
        def on_result(name: str | None) -> None:
            if name:
                if name.endswith("/"):
                    (self.current_dir / name.rstrip("/")).mkdir(exist_ok=True)
                else:
                    (self.current_dir / name).touch()
                self._refresh_view()

        self.push_screen(
            InputDialog("Create (end with / for dir):"), callback=on_result
        )

    def action_rename(self) -> None:
        fl = self.query_one(FileList)
        selected = fl.selected_path()
        if selected is None:
            return

        def on_result(new_name: str | None) -> None:
            if new_name and new_name != selected.name:
                selected.rename(self.current_dir / new_name)
                self._refresh_view()

        self.push_screen(
            InputDialog("Rename:", default=selected.name), callback=on_result
        )

    def action_delete(self) -> None:
        fl = self.query_one(FileList)
        selected = fl.selected_path()
        if selected is None:
            return

        def on_result(confirmed: bool) -> None:
            if confirmed:
                if selected.is_dir():
                    shutil.rmtree(selected)
                else:
                    selected.unlink()
                self._refresh_view()

        self.push_screen(
            ConfirmDialog(f"Delete '{selected.name}'?"), callback=on_result
        )


if __name__ == "__main__":
    Explorer().run()
