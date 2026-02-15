# tui-explorer

A [yazi](https://github.com/sxyazi/yazi)-inspired three-pane terminal file manager built with [Textual](https://github.com/Textualize/textual).

## Features

- Three-pane layout (parent / current / preview) like yazi
- Yazi-style keybindings for navigation and file operations
- File preview with text content, directory listings, and binary detection
- Yank/paste (copy & move) workflow
- Open files in `$EDITOR` (defaults to `vim`)
- Create, rename, and delete files/directories
- Toggle hidden files

## Keybindings

| Key | Action |
|-----|--------|
| `j` / `k` | Move cursor down / up |
| `l` / `Enter` | Open directory or edit file |
| `h` | Go to parent directory |
| `g` / `G` | Jump to top / bottom |
| `~` | Go to home directory |
| `.` | Toggle hidden files |
| `a` | Create file (or directory if name ends with `/`) |
| `r` | Rename |
| `D` | Delete |
| `y` | Yank (copy) |
| `x` | Yank (cut) |
| `p` | Paste |
| `P` | Paste (overwrite) |
| `Y` / `X` | Cancel yank |
| `q` | Quit |

## Install

Requires Python 3.14+.

```sh
uv sync
uv run python app.py
```

## Configuration

Set `$EDITOR` to choose which editor opens on `Enter`:

```sh
export EDITOR=nvim
```
