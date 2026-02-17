"""Gemeinsame Datenmodelle fuer abs-cli."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Library:
    """Audiobookshelf-Bibliothek."""

    id: str
    name: str
    media_type: str
    folders: list[dict[str, Any]]

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Library:
        """Erstellt eine Library aus API-Antwortdaten."""
        return cls(
            id=data["id"],
            name=data["name"],
            media_type=data.get("mediaType", ""),
            folders=data.get("folders", []),
        )


@dataclass
class LibraryStats:
    """Statistiken einer Bibliothek."""

    total_items: int
    total_size: int
    total_duration: float
    num_authors: int
    num_genres: int

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> LibraryStats:
        """Erstellt LibraryStats aus API-Antwortdaten."""
        return cls(
            total_items=data.get("totalItems", 0),
            total_size=data.get("totalSize", 0),
            total_duration=data.get("totalDuration", 0.0),
            num_authors=data.get("numAuthors", 0),
            num_genres=data.get("numGenres", 0),
        )


@dataclass
class LibraryItem:
    """Ein Item (Hoerbuch/Podcast) in einer Bibliothek."""

    id: str
    title: str
    author: str | None = None
    narrator: str | None = None
    duration: float = 0.0
    asin: str | None = None
    is_missing: bool = False

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> LibraryItem:
        """Erstellt ein LibraryItem aus der API-Antwort.

        Args:
            data: API-Antwortdaten fuer ein Item

        Returns:
            LibraryItem-Instanz
        """
        media = data.get("media", {})
        metadata = media.get("metadata", {})
        return cls(
            id=data["id"],
            title=metadata.get("title", "Unbekannt"),
            author=metadata.get("authorName") or metadata.get("author"),
            narrator=metadata.get("narratorName") or metadata.get("narrator"),
            duration=media.get("duration", 0.0),
            asin=metadata.get("asin"),
            is_missing=data.get("isMissing", False),
        )


@dataclass
class ItemDetail:
    """Detaillierte Informationen zu einem Item."""

    id: str
    title: str
    author: str | None = None
    narrator: str | None = None
    duration: float = 0.0
    asin: str | None = None
    isbn: str | None = None
    description: str | None = None
    publisher: str | None = None
    publish_year: str | None = None
    language: str | None = None
    genres: list[str] = field(default_factory=list)
    series_name: str | None = None
    series_sequence: str | None = None
    is_missing: bool = False
    num_tracks: int = 0
    size: int = 0

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> ItemDetail:
        """Erstellt ein ItemDetail aus der API-Antwort.

        Args:
            data: API-Antwortdaten fuer ein Item

        Returns:
            ItemDetail-Instanz
        """
        media = data.get("media", {})
        metadata = media.get("metadata", {})
        series = metadata.get("series", [])
        series_entry = series[0] if series else {}

        audio_files = media.get("audioFiles", [])
        total_size = sum(f.get("metadata", {}).get("size", 0) for f in audio_files)

        return cls(
            id=data["id"],
            title=metadata.get("title", "Unbekannt"),
            author=metadata.get("authorName") or metadata.get("author"),
            narrator=metadata.get("narratorName") or metadata.get("narrator"),
            duration=media.get("duration", 0.0),
            asin=metadata.get("asin"),
            isbn=metadata.get("isbn"),
            description=metadata.get("description"),
            publisher=metadata.get("publisher"),
            publish_year=metadata.get("publishedYear"),
            language=metadata.get("language"),
            genres=metadata.get("genres", []),
            series_name=series_entry.get("name") if series_entry else None,
            series_sequence=series_entry.get("sequence") if series_entry else None,
            is_missing=data.get("isMissing", False),
            num_tracks=len(audio_files),
            size=total_size,
        )


@dataclass
class ProgressItem:
    """Hoerfortschritt eines Items."""

    item_id: str
    title: str
    progress: float
    current_time: float
    duration: float
    is_finished: bool
    last_update: int

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> ProgressItem:
        """Erstellt ein ProgressItem aus API-Antwortdaten.

        Args:
            data: libraryItemWithEpisode-Objekt aus /me/items-in-progress
        """
        media = data.get("media", {})
        progress_data = data.get("mediaProgress", {}) or {}
        metadata = media.get("metadata", {})

        duration = progress_data.get("duration", 0.0) or media.get("duration", 0.0)

        return cls(
            item_id=data.get("id", ""),
            title=metadata.get("title", data.get("id", "")),
            progress=progress_data.get("progress", 0.0),
            current_time=progress_data.get("currentTime", 0.0),
            duration=duration,
            is_finished=progress_data.get("isFinished", False),
            last_update=progress_data.get("lastUpdate", 0),
        )


@dataclass
class LibationBook:
    """Buch aus der Libation-Datenbank."""

    asin: str
    title: str
