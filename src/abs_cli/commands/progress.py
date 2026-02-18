"""Fortschritts-Kommandos."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from abs_cli.client import ABSClient
from abs_cli.models import LibationBook, ProgressItem


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


def _read_libation_finished(db_path: Path) -> list[LibationBook]:
    """Liest abgeschlossene Buecher aus der Libation-Datenbank.

    Args:
        db_path: Pfad zur Libation SQLite-Datenbank

    Returns:
        Liste der abgeschlossenen Buecher
    """
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.execute(
            "SELECT b.AudibleProductId, b.Title "
            "FROM Books b "
            "JOIN UserDefinedItem udi ON b.AudibleProductId = udi.BookId "
            "WHERE udi.IsFinished = 1"
        )
        return [LibationBook(asin=row[0], title=row[1]) for row in cursor.fetchall()]
    finally:
        conn.close()


def _build_asin_index(client: ABSClient) -> dict[str, dict[str, Any]]:
    """Baut einen Index ASIN -> {item_id, title, is_finished} aus allen ABS-Bibliotheken.

    Args:
        client: ABSClient-Instanz

    Returns:
        Dict mit ASIN als Key und Item-Info als Value
    """
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
                    progress_data = item.get("mediaProgress") or {}
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
@click.option("--from-libation", "libation_db", required=True, type=click.Path(exists=True, path_type=Path), help="Pfad zur Libation SQLite-Datenbank.")
@click.option("--apply", is_flag=True, default=False, help="Aenderungen tatsaechlich anwenden (Standard: Dry-Run).")
@click.pass_context
def progress_sync(ctx: click.Context, libation_db: Path, apply: bool) -> None:
    """Fortschritt aus Libation synchronisieren."""
    client: ABSClient = ctx.obj["client"]
    console = Console()

    if not apply:
        console.print("[yellow]DRY-RUN Modus - keine Aenderungen werden vorgenommen. Nutze --apply zum Anwenden.[/yellow]\n")

    console.print("Lese Libation-Datenbank...")
    finished_books = _read_libation_finished(libation_db)
    console.print(f"{len(finished_books)} abgeschlossene Buecher in Libation gefunden.\n")

    if not finished_books:
        return

    console.print("Lade ABS-Bibliothek...")
    asin_index = _build_asin_index(client)
    console.print(f"{len(asin_index)} Items mit ASIN in ABS gefunden.\n")

    table = Table(title="Libation-Sync")
    table.add_column("Libation Titel", style="bold")
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
            table.add_row(book.title, book.asin, "[red]Nein[/red]", "-", "-")
            not_found += 1
            continue

        if abs_item["is_finished"]:
            table.add_row(
                book.title, book.asin, "[green]Ja[/green]",
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
                book.title, book.asin, "[green]Ja[/green]",
                abs_item["title"], "[green]Synchronisiert[/green]",
            )
        else:
            table.add_row(
                book.title, book.asin, "[green]Ja[/green]",
                abs_item["title"], "[yellow]Wuerde synchronisieren[/yellow]",
            )
        synced += 1

    console.print(table)
    console.print(f"\nErgebnis: {synced} zu synchronisieren, {skipped} bereits abgeschlossen, {not_found} nicht in ABS gefunden.")
