"""Fetch and parse the ashbalala.com catalog and book playlists.

Both the homepage catalog and each book's ``#playlist`` are present in the
static HTML, so plain ``requests`` + BeautifulSoup is enough — no JS rendering.
"""

from __future__ import annotations

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag
from loguru import logger

from ashbala.models import Book, Track

BASE_URL = "https://ashbalala.com/"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}


def _attr(tag: Tag, name: str) -> str | None:
    """Return ``tag``'s ``name`` attribute when it is a single string value.

    BeautifulSoup types multi-valued attributes (such as ``class``) as a list;
    the attributes read here are always single-valued, so any non-string result
    is treated as absent.
    """
    value = tag.get(name)
    return value if isinstance(value, str) else None


def _session() -> requests.Session:
    """Create a :class:`requests.Session` preloaded with the browser-like headers."""
    s = requests.Session()
    s.headers.update(_HEADERS)
    return s


def _soup(session: requests.Session, url: str, *, timeout: int = 30) -> BeautifulSoup:
    """GET ``url`` and parse the response body into a :class:`BeautifulSoup` tree.

    Args:
        session: The session used to issue the request.
        url: The absolute URL to fetch.
        timeout: Per-request timeout in seconds.

    Returns:
        The parsed HTML document.

    Raises:
        requests.HTTPError: If the response status is an error code.
    """
    logger.debug("GET {}", url)
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def fetch_catalog(session: requests.Session | None = None) -> list[Book]:
    """Return every book listed on the homepage.

    Catalog entries are ``<a class="no-pjax" data-link-type="page">`` anchors
    nested inside ``<li>`` items; header/category links share the class but are
    not inside an ``<li>``, so the parent check filters them out.
    """
    session = session or _session()
    soup = _soup(session, BASE_URL)

    books: list[Book] = []
    seen: set[str] = set()
    for anchor in soup.select('a.no-pjax[data-link-type="page"]'):
        li: Tag | None = anchor.find_parent("li")
        if li is None:
            continue
        href: str | None = _attr(anchor, "href")
        if not href or href in seen:
            continue
        seen.add(href)

        title = anchor.get_text(strip=True)
        author, meta = _parse_li_meta(li, anchor)
        books.append(
            Book(title=title, url=urljoin(BASE_URL, href), author=author, meta=meta)
        )

    books.sort(key=lambda b: b.title.lower())
    logger.info("Loaded {} books from catalog", len(books))
    return books


def _parse_li_meta(li: Tag, anchor: Tag) -> tuple[str, str]:
    """Pull "Author | Type | Status" text that follows the title anchor."""
    spans = [s.get_text(strip=True) for s in li.find_all("span")]
    spans = [s for s in spans if s]
    if not spans:
        return "", ""
    author = spans[0]
    meta = " | ".join(spans[1:])
    return author, meta


def fetch_tracks(book_url: str, session: requests.Session | None = None) -> list[Track]:
    """Extract every ``#playlist > .track`` entry from a book page.

    Despite the ``track`` name, these are ``<div class="track">`` nodes (there
    is no HTML ``<track>`` element on the page), each carrying ``data-title``,
    ``data-audio`` and ``data-cover`` attributes.
    """
    session = session or _session()
    soup = _soup(session, book_url)

    playlist = soup.find(id="playlist")
    if playlist is None:
        raise LookupError(
            f"No #playlist element found on {book_url} — check the URL, or the "
            "site's page structure may have changed."
        )

    tracks: list[Track] = []
    for el in playlist.select(".track"):
        audio_url = _attr(el, "data-audio")
        if not audio_url:
            continue
        title = (
            _attr(el, "data-title") or el.get_text(strip=True)
        ).strip() or f"Track {len(tracks) + 1}"
        tracks.append(
            Track(
                index=len(tracks) + 1,
                title=title,
                audio_url=urljoin(book_url, audio_url),
                cover_url=_attr(el, "data-cover") or "",
            )
        )

    if not tracks:
        raise LookupError(
            f"#playlist found on {book_url}, but it has no .track entries with data-audio."
        )

    logger.info("Found {} track(s) on {}", len(tracks), book_url)
    return tracks
