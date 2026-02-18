"""Fortschritts-Kommandos."""

from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from abs_cli.client import ABSClient
from abs_cli.models import LibationBook, ProgressItem


@dataclass
class FinishedBook:
    """Ein als gehoert markiertes Buch aus einer externen Quelle."""

    asin: str
    title: str
    source: str


def _format_time(seconds: float) -> str:
    """Formatiert Sekunden als HH:MM:SS."""
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _format_timestamp(ts: int) -> str:
    """Formatiert einen Unix-Timestamp als lesbares Datum."""
    if not ts:
        return "-"
    dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M")


@click.group()
def progress() -> None:
    """Hoerfortschritt verwalten."""


def _build_title_index(client: ABSClient) -> dict[str, str]:
    """Baut einen Index libraryItemId -> Titel aus allen Bibliotheken.

    Args:
        client: ABSClient-Instanz

    Returns:
        Dict mit libraryItemId als Key und Titel als Value
    """
    index: dict[str, str] = {}

    libs_resp = client.get("/libraries")
    libs_resp.raise_for_status()
    libraries = libs_resp.json().get("libraries", [])

    for lib in libraries:
        lib_id = lib["id"]
        page = 0
        while True:
            resp = client.get(
                f"/libraries/{lib_id}/items", params={"limit": 100, "page": page},
            )
            resp.raise_for_status()
            result = resp.json()
            lib_items = result.get("results", [])
            if not lib_items:
                break

            for item in lib_items:
                title = (
                    item.get("media", {}).get("metadata", {}).get("title", "")
                )
                index[item["id"]] = title

            total = result.get("total", 0)
            if (page + 1) * 100 >= total:
                break
            page += 1

    return index


@progress.command("list")
@click.option("--finished", is_flag=True, default=False, help="Nur abgeschlossene Items.")
@click.option("--in-progress", "in_progress", is_flag=True, default=False, help="Nur laufende Items.")
@click.pass_context
def progress_list(ctx: click.Context, finished: bool, in_progress: bool) -> None:
    """Hoerfortschritt auflisten."""
    client: ABSClient = ctx.obj["client"]
    console = Console()

    # Fetch all media progress from /me endpoint
    me_resp = client.get("/me")
    me_resp.raise_for_status()
    all_progress = me_resp.json().get("mediaProgress", [])

    if not all_progress:
        console.print("Keine Items gefunden.")
        return

    # Filter before loading titles (saves API calls if empty after filter)
    if finished:
        all_progress = [
            p for p in all_progress if p.get("isFinished") or p.get("progress", 0) >= 1.0
        ]
    elif in_progress:
        all_progress = [
            p for p in all_progress
            if not p.get("isFinished") and p.get("progress", 0) < 1.0
        ]

    if not all_progress:
        console.print("Keine Items gefunden.")
        return

    # Build title index to resolve libraryItemId -> title
    title_index = _build_title_index(client)

    items: list[ProgressItem] = []
    for entry in all_progress:
        item_id = entry.get("libraryItemId", "")
        title = title_index.get(item_id, item_id)
        items.append(ProgressItem.from_media_progress(entry, title=title))

    # Sort: in-progress first (by progress desc), then finished (by last update desc)
    items.sort(key=lambda i: (i.is_finished, -i.last_update))

    table = Table(title="Hoerfortschritt")
    table.add_column("Titel", style="bold")
    table.add_column("Fortschritt", justify="right")
    table.add_column("Position", justify="right")
    table.add_column("Dauer", justify="right")
    table.add_column("Letztes Update")

    for item in items:
        pct = f"{item.progress * 100:.1f}%"
        style = "green" if item.is_finished or item.progress >= 1.0 else ""
        table.add_row(
            item.title,
            pct,
            _format_time(item.current_time),
            _format_time(item.duration),
            _format_timestamp(item.last_update),
            style=style,
        )

    console.print(table)


def _read_libation_finished(db_path: Path) -> list[FinishedBook]:
    """Liest abgeschlossene Buecher aus der Libation-Datenbank."""
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute(
            "SELECT b.AudibleProductId, b.Title "
            "FROM Books b "
            "JOIN UserDefinedItem udi ON b.AudibleProductId = udi.BookId "
            "WHERE udi.IsFinished = 1"
        )
        return [FinishedBook(asin=row[0], title=row[1], source="Libation") for row in cursor.fetchall()]
    finally:
        conn.close()


def _read_audible_export_finished(export_path: Path) -> list[FinishedBook]:
    """Liest abgeschlossene Buecher aus einem audible-cli Export (JSON/TSV/CSV)."""
    suffix = export_path.suffix.lower()

    if suffix == ".json":
        data = json.loads(export_path.read_text())
        return [
            FinishedBook(asin=item["asin"], title=item.get("title", ""), source="Audible")
            for item in data
            if item.get("is_finished") is True
        ]

    # TSV oder CSV
    delimiter = "\t" if suffix == ".tsv" else ","
    books: list[FinishedBook] = []
    with export_path.open(newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            is_finished = row.get("is_finished", "").strip().lower()
            if is_finished in ("true", "1", "yes"):
                books.append(FinishedBook(
                    asin=row.get("asin", ""),
                    title=row.get("title", ""),
                    source="Audible",
                ))
    return books


def _build_asin_index(client: ABSClient) -> dict[str, dict[str, Any]]:
    """Baut einen Index ASIN -> {item_id, title, is_finished} aus allen ABS-Bibliotheken.

    Args:
        client: ABSClient-Instanz

    Returns:
        Dict mit ASIN als Key und Item-Info als Value
    """
    # Fetch user progress from /me (library items don't include mediaProgress)
    me_resp = client.get("/me")
    me_resp.raise_for_status()
    progress_by_item: dict[str, dict] = {}
    for p in me_resp.json().get("mediaProgress", []):
        progress_by_item[p.get("libraryItemId", "")] = p

    index: dict[str, dict[str, Any]] = {}

    libs_resp = client.get("/libraries")
    libs_resp.raise_for_status()
    libraries = libs_resp.json().get("libraries", [])

    for lib in libraries:
        lib_id = lib["id"]
        page = 0
        while True:
            resp = client.get(f"/libraries/{lib_id}/items", params={"limit": 100, "page": page})
            resp.raise_for_status()
            result = resp.json()
            lib_items = result.get("results", [])
            if not lib_items:
                break

            for item in lib_items:
                media = item.get("media", {})
                metadata = media.get("metadata", {})
                asin = metadata.get("asin")
                if asin:
                    progress_data = progress_by_item.get(item["id"], {})
                    index[asin] = {
                        "item_id": item["id"],
                        "title": metadata.get("title", ""),
                        "is_finished": progress_data.get("isFinished", False),
                    }

            total = result.get("total", 0)
            if (page + 1) * 100 >= total:
                break
            page += 1

    return index


@progress.command("sync")
@click.option("--from-libation", "libation_db", type=click.Path(exists=True, path_type=Path), default=None, help="Pfad zur Libation SQLite-Datenbank.")
@click.option("--from-audible-export", "audible_export", type=click.Path(exists=True, path_type=Path), default=None, help="Pfad zum audible-cli Export (JSON/TSV/CSV).")
@click.option("--apply", is_flag=True, default=False, help="Aenderungen tatsaechlich anwenden (Standard: Dry-Run).")
@click.pass_context
def progress_sync(
    ctx: click.Context, libation_db: Path | None, audible_export: Path | None, apply: bool,
) -> None:
    """Fortschritt aus externer Quelle synchronisieren.

    Unterstuetzte Quellen:
      --from-libation       Libation SQLite-Datenbank
      --from-audible-export audible-cli Export (JSON/TSV/CSV)
    """
    if not libation_db and not audible_export:
        raise click.UsageError("Mindestens eine Quelle angeben: --from-libation oder --from-audible-export")

    client: ABSClient = ctx.obj["client"]
    console = Console()

    if not apply:
        console.print("[yellow]DRY-RUN Modus - keine Aenderungen werden vorgenommen. Nutze --apply zum Anwenden.[/yellow]\n")

    finished_books: list[FinishedBook] = []

    if libation_db:
        console.print("Lese Libation-Datenbank...")
        libation_books = _read_libation_finished(libation_db)
        console.print(f"{len(libation_books)} abgeschlossene Buecher in Libation gefunden.")
        finished_books.extend(libation_books)

    if audible_export:
        console.print("Lese Audible-Export...")
        audible_books = _read_audible_export_finished(audible_export)
        console.print(f"{len(audible_books)} abgeschlossene Buecher im Audible-Export gefunden.")
        finished_books.extend(audible_books)

    if not finished_books:
        console.print("\nKeine abgeschlossenen Buecher gefunden.")
        return

    console.print(f"\n[bold]{len(finished_books)} Buecher insgesamt aus {len({b.source for b in finished_books})} Quelle(n).[/bold]\n")

    console.print("Lade ABS-Bibliothek...")
    asin_index = _build_asin_index(client)
    console.print(f"{len(asin_index)} Items mit ASIN in ABS gefunden.\n")

    table = Table(title="Sync-Ergebnis")
    table.add_column("Titel", style="bold")
    table.add_column("Quelle")
    table.add_column("ASIN")
    table.add_column("ABS Match", justify="center")
    table.add_column("ABS Titel")
    table.add_column("Aktion")

    synced = 0
    skipped = 0
    not_found = 0

    for book in finished_books:
        abs_item = asin_index.get(book.asin)

        if not abs_item:
            table.add_row(book.title, book.source, book.asin, "[red]Nein[/red]", "-", "-")
            not_found += 1
            continue

        if abs_item["is_finished"]:
            table.add_row(
                book.title, book.source, book.asin, "[green]Ja[/green]",
                abs_item["title"], "[dim]Bereits abgeschlossen[/dim]",
            )
            skipped += 1
            continue

        if apply:
            resp = client.patch(
                f"/me/progress/{abs_item['item_id']}",
                json={"isFinished": True, "progress": 1},
            )
            resp.raise_for_status()
            table.add_row(
                book.title, book.source, book.asin, "[green]Ja[/green]",
                abs_item["title"], "[green]Synchronisiert[/green]",
            )
        else:
            table.add_row(
                book.title, book.source, book.asin, "[green]Ja[/green]",
                abs_item["title"], "[yellow]Wuerde synchronisieren[/yellow]",
            )
        synced += 1

    console.print(table)
    console.print(f"\nErgebnis: {synced} zu synchronisieren, {skipped} bereits abgeschlossen, {not_found} nicht in ABS gefunden.")
