# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

A Typer CLI that browses [ashbalala.com](https://ashbalala.com/) (a text-to-speech audiobook catalog on the bndzgl/zoogletools platform), lets the user pick a book, then extracts each entry from that book page's `#playlist` and can download the audio.

## Architecture

Everything lives in the `src/ashbala/` package (import root is `ashbala`):

- `models.py` — frozen dataclasses `Book` (title/url/author/meta, with a `slug` property) and `Track` (index/title/audio_url/cover_url).
- `scraper.py` — `fetch_catalog()` and `fetch_tracks(book_url)`, both plain `requests` + BeautifulSoup. **Key parsing facts:** the homepage catalog is `a.no-pjax[data-link-type="page"]` anchors nested in `<li>` (the `<li>` parent check excludes header/category links that share the class). On a book page the "tracks" are `#playlist > div.track` nodes carrying `data-title` / `data-audio` / `data-cover` — there is **no** HTML `<track>` element, so select by the `.track` class, not the tag.
- `download.py` — `download_tracks()` (streaming, skip-existing) and `write_manifest()` (CSV + JSON). Adapted from the original standalone `download_playlist.py`.
- `cli.py` — the Typer `app` (entry point `ashbala`). Commands: `list [QUERY]` and `get [BOOK]`. `get` resolves a full URL / slug / title-substring, or prompts interactively when the arg is omitted or matches many; `--download`, `--manifest`, `--out` control side effects.

Both the catalog and playlists are in the static HTML — no JS rendering is needed.

## Run

```bash
uv run ashbala get "12 miles below"          # resolve by substring, show tracks
uv run ashbala get <url|slug> --download      # download audio to ./<slug>/
uv run ashbala list "sword"                    # filter the catalog
uv run ashbala get                             # interactive browse + pick
```

Interactive selection needs a TTY; with many matches and no TTY the CLI exits asking you to refine the query.

## Toolchain

This project uses [uv](https://docs.astral.sh/uv/) for dependency and environment management, with the `uv_build` backend. It targets **Python >=3.14** (`.python-version` pins 3.14). Do not hand-edit `uv.lock`.

```bash
uv sync                    # install/update the environment from pyproject.toml + uv.lock
uv add <package>           # add a runtime dependency (updates pyproject.toml + lock)
uv add --dev <package>     # add a dev-only dependency
uv run python -c "import ashbala; print(ashbala.hello())"   # run code in the env
uv run <cmd>               # run any command inside the project venv
```

No test runner, linter, or formatter is configured yet. When adding tests, prefer `uv add --dev pytest` and run with `uv run pytest` (single test: `uv run pytest path::test_name`).

## Layout

`src/`-layout package (`src/ashbala/`). The package ships `py.typed`, so it is distributed as typed — keep public functions fully type-annotated so downstream type checkers see the hints.

## Stack conventions

- **requests** + **bs4** (BeautifulSoup) — HTTP fetching and HTML scraping/parsing (`scraper.py`).
- **typer** — the CLI framework (`cli.py`).
- **rich** — terminal tables / status spinners (`Console`, `Table`). `rich-gradient` is available but not yet used.
- **loguru** — logging; use `loguru.logger`, not the stdlib `logging` module. `cli.py` routes it to stderr (WARNING, or DEBUG with `-v`), so library code should just `logger.info/debug` and let the CLI configure sinks.
