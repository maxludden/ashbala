"""Typer CLI for browsing ashbalala.com and extracting book playlists."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import requests
import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from ashbala import download as dl
from ashbala.models import Book, Track
from ashbala.scraper import fetch_catalog, fetch_tracks

app = typer.Typer(
    add_completion=False,
    help="Browse ashbalala.com and extract a book's audio playlist.",
    no_args_is_help=False,
)
console = Console()


@app.callback()
def _configure(verbose: bool = typer.Option(False, "--verbose", "-v", help="Show debug logging.")) -> None:
    """Route loguru to stderr at DEBUG when ``--verbose`` is set, else WARNING."""
    logger.remove()
    logger.add(sys.stderr, level="DEBUG" if verbose else "WARNING", format="{message}")


def _resolve_book(query: Optional[str]) -> Book:
    """Turn a URL / slug / title-substring (or nothing) into one Book.

    A full ``http(s)`` URL is used directly. Otherwise the catalog is fetched
    and filtered; on multiple hits (or no query) the user picks interactively.
    """
    if query and query.startswith(("http://", "https://")):
        slug = query.rstrip("/").split("/")[-1]
        return Book(title=slug, url=query)

    with console.status("Loading catalog from ashbalala.com…"):
        catalog = fetch_catalog()

    matches = _filter(catalog, query) if query else catalog
    if not matches:
        console.print(f"[red]No book matches[/red] {query!r}. Try a shorter search term.")
        raise typer.Exit(1)
    if len(matches) == 1:
        return matches[0]
    return _pick(matches)


def _filter(catalog: list[Book], query: str) -> list[Book]:
    """Filter ``catalog`` by ``query``.

    An exact slug match wins outright; otherwise every book whose title or slug
    contains ``query`` (case-insensitive) is returned.
    """
    q = query.lower()
    exact = [b for b in catalog if b.slug == q]
    if exact:
        return exact
    return [b for b in catalog if q in b.title.lower() or q in b.slug]


def _pick(matches: list[Book]) -> Book:
    """Prompt the user to choose one book from ``matches`` via a numbered table.

    Shows at most 40 rows. Requires an interactive TTY.

    Raises:
        typer.Exit: If there is no TTY to prompt on, or the choice is out of range.
    """
    if not sys.stdin.isatty():
        console.print(f"[red]{len(matches)} books match[/red]; refine the query (no TTY to prompt).")
        raise typer.Exit(1)

    shown = matches[:40]
    table = Table(title=f"{len(matches)} matches" + (" (showing 40)" if len(matches) > 40 else ""))
    table.add_column("#", justify="right", style="cyan")
    table.add_column("Title", style="bold")
    table.add_column("Author", style="green")
    for i, b in enumerate(shown, 1):
        table.add_row(str(i), b.title, b.author)
    console.print(table)

    choice = typer.prompt("Select a book number", type=int)
    if not 1 <= choice <= len(shown):
        console.print("[red]Out of range.[/red]")
        raise typer.Exit(1)
    return shown[choice - 1]


def _print_tracks(book: Book, tracks: list[Track]) -> None:
    """Render ``tracks`` for ``book`` as a Rich table on the console."""
    table = Table(title=f"{book.title} — {len(tracks)} track(s)")
    table.add_column("#", justify="right", style="cyan")
    table.add_column("Title", style="bold")
    table.add_column("Audio URL", style="dim", overflow="fold")
    for t in tracks:
        table.add_row(str(t.index), t.title, t.audio_url)
    console.print(table)


@app.command("list")
def list_books(query: Optional[str] = typer.Argument(None, help="Filter titles by substring.")) -> None:
    """List catalog books (optionally filtered)."""
    try:
        catalog = fetch_catalog()
    except requests.RequestException as exc:
        console.print(f"[red]Failed to load catalog:[/red] {exc}")
        raise typer.Exit(1)

    books = _filter(catalog, query) if query else catalog
    table = Table(title=f"{len(books)} book(s)")
    table.add_column("Title", style="bold")
    table.add_column("Author", style="green")
    table.add_column("Meta", style="dim")
    for b in books:
        table.add_row(b.title, b.author, b.meta)
    console.print(table)


@app.command()
def get(
    book: Optional[str] = typer.Argument(None, help="Book URL, slug, or title substring. Omit to browse."),
    download: bool = typer.Option(False, "--download", "-d", help="Download the audio files."),
    manifest: bool = typer.Option(False, "--manifest", "-m", help="Write manifest.csv / manifest.json."),
    out: Optional[Path] = typer.Option(None, "--out", "-o", help="Output directory (default: ./<slug>)."),
) -> None:
    """Select a book, extract its #playlist tracks, and display them."""
    selected = _resolve_book(book)
    try:
        with console.status(f"Fetching playlist for {selected.title}…"):
            tracks = fetch_tracks(selected.url)
    except requests.RequestException as exc:
        console.print(f"[red]Failed to fetch book page:[/red] {exc}")
        raise typer.Exit(1)
    except LookupError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    _print_tracks(selected, tracks)

    if not (download or manifest):
        return

    out_dir = out or Path(selected.slug or "ashbalala-book")
    if manifest:
        dl.write_manifest(tracks, out_dir, selected.url)
        console.print(f"[green]Manifest written to[/green] {out_dir}/")
    if download:
        with console.status(f"Downloading {len(tracks)} track(s) to {out_dir}/…"):
            saved = dl.download_tracks(tracks, out_dir)
        console.print(f"[green]Saved {len(saved)}/{len(tracks)} file(s) to[/green] {out_dir}/")


if __name__ == "__main__":
    app()
