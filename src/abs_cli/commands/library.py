"""Bibliotheks-Kommandos."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from abs_cli.client import ABSClient
from abs_cli.models import Library, LibraryStats

console = Console()


@click.group()
def library() -> None:
    """Bibliotheken verwalten."""


@library.command("list")
@click.pass_context
def list_libraries(ctx: click.Context) -> None:
    """Alle Bibliotheken auflisten."""
    client: ABSClient = ctx.obj["client"]

    resp = client.get("/libraries")
    resp.raise_for_status()

    libraries_data = resp.json().get("libraries", [])
    libraries = [Library.from_api(lib) for lib in libraries_data]

    if not libraries:
        console.print("Keine Bibliotheken gefunden.")
        return

    table = Table(title="Bibliotheken")
    table.add_column("ID", style="dim")
    table.add_column("Name", style="bold")
    table.add_column("Typ")
    table.add_column("Ordner", justify="right")

    for lib in libraries:
        table.add_row(
            lib.id,
            lib.name,
            lib.media_type,
            str(len(lib.folders)),
        )

    console.print(table)


@library.command()
@click.argument("library_id", required=False)
@click.option("--force", is_flag=True, help="Erzwingt einen vollstaendigen Rescan.")
@click.pass_context
def scan(ctx: click.Context, library_id: str | None, *, force: bool) -> None:
    """Bibliothek neu scannen.

    Ohne LIBRARY_ID werden alle Bibliotheken gescannt.
    """
    client: ABSClient = ctx.obj["client"]

    if library_id:
        library_ids = [library_id]
    else:
        resp = client.get("/libraries")
        resp.raise_for_status()
        library_ids = [lib["id"] for lib in resp.json().get("libraries", [])]

    params = {"force": "1"} if force else {}

    for lib_id in library_ids:
        resp = client.post(f"/libraries/{lib_id}/scan", params=params)
        resp.raise_for_status()
        console.print(f"Scan gestartet fuer Bibliothek [bold]{lib_id}[/bold]")

    console.print(f"[green]{len(library_ids)} Bibliothek(en) werden gescannt.[/green]")


@library.command()
@click.argument("library_id", required=False)
@click.pass_context
def stats(ctx: click.Context, library_id: str | None) -> None:
    """Statistiken einer Bibliothek anzeigen.

    Ohne LIBRARY_ID werden Statistiken aller Bibliotheken angezeigt.
    """
    client: ABSClient = ctx.obj["client"]

    if library_id:
        libraries_info = [{"id": library_id, "name": library_id}]
    else:
        resp = client.get("/libraries")
        resp.raise_for_status()
        libraries_data = resp.json().get("libraries", [])
        libraries_info = [{"id": lib["id"], "name": lib["name"]} for lib in libraries_data]

    if not libraries_info:
        console.print("Keine Bibliotheken gefunden.")
        return

    table = Table(title="Bibliotheks-Statistiken")
    table.add_column("Bibliothek", style="bold")
    table.add_column("Items", justify="right")
    table.add_column("Groesse", justify="right")
    table.add_column("Dauer (h)", justify="right")
    table.add_column("Autoren", justify="right")
    table.add_column("Genres", justify="right")

    for lib_info in libraries_info:
        resp = client.get(f"/libraries/{lib_info['id']}/stats")
        resp.raise_for_status()
        lib_stats = LibraryStats.from_api(resp.json())

        size_gb = lib_stats.total_size / (1024**3)
        duration_h = lib_stats.total_duration / 3600

        table.add_row(
            lib_info["name"],
            str(lib_stats.total_items),
            f"{size_gb:.1f} GB",
            f"{duration_h:.1f}",
            str(lib_stats.num_authors),
            str(lib_stats.num_genres),
        )

    console.print(table)
