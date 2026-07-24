"""Data models for the ashbalala.com catalog and book playlists."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class Book:
    """A single title in the ashbalala.com catalog.

    Attributes:
        title: The book's display title.
        url: Absolute URL of the book's page.
        author: The author's name, or ``""`` if not listed.
        meta: Free-form catalog metadata, e.g. ``"Text to Speech | Ongoing"``.
    """

    title: str
    url: str
    author: str = ""
    meta: str = ""  # e.g. "Text to Speech | Ongoing"

    @property
    def slug(self) -> str:
        """The final path segment of :attr:`url`, used as a default directory name."""
        return urlparse(self.url).path.strip("/").split("/")[-1]


@dataclass(frozen=True, slots=True)
class Track:
    """A single audio entry inside a book page's ``#playlist``.

    Attributes:
        index: 1-based position of the track within the playlist.
        title: The track's display title.
        audio_url: Absolute URL of the track's audio file.
        cover_url: Absolute URL of the track's cover image, or ``""`` if none.
    """

    index: int
    title: str
    audio_url: str
    cover_url: str = ""
