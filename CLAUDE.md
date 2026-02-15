# CLAUDE.md

## Project overview

tui-explorer is a yazi-inspired three-pane terminal file manager. Single-file Python app built on Textual.

## Tech stack

- Python 3.14+, single file: `app.py`
- [Textual](https://textual.textualize.io/) TUI framework
- Uses `rich.markup` for styled text rendering
- Dependency management: `uv` (see `pyproject.toml`)

## Architecture

Everything lives in `app.py`. Key classes:

- `Explorer(App)` — main app, holds all state and keybindings
- `ParentPane`, `FileList`, `PreviewPane` — the three panes (left, center, right)
- `StatusBar` — bottom bar showing path, counts, and yank state
- `InputDialog`, `ConfirmDialog`, `MessageDialog` — modal screens for user interaction

State flows top-down: `Explorer` owns `current_dir`, `show_hidden`, and yank state (`_yank_path`, `_yank_cut`), then syncs child widgets via `_sync_all()`.

## Running

```sh
uv sync
uv run python app.py
```

## Conventions

- Keybindings follow yazi defaults — check yazi docs before changing
- File operations use `shutil` (copy2, copytree, move, rmtree)
- Editor integration suspends the TUI via `self.suspend()` and calls `$EDITOR`
- Binary files are detected by extension using `PreviewPane.BINARY_EXTENSIONS`
- User-facing warnings/errors use centered `MessageDialog`, not `self.notify()`
- Destructive actions (delete) use `ConfirmDialog` for confirmation
