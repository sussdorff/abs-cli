"""Item-Kommandos."""

from __future__ import annotations

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from abs_cli.client import ABSClient
from abs_cli.models import ItemDetail, LibraryItem

console = Console()


def _format_duration(seconds: float) -> str:
    """Formatiert Sekunden als h:mm:ss.

    Args:
        seconds: Dauer in Sekunden

    Returns:
        Formatierte Dauer
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def _format_size(size_bytes: int) -> str:
    """Formatiert Bytes als menschenlesbare Groesse.

    Args:
        size_bytes: Groesse in Bytes

    Returns:
        Formatierte Groesse
    """
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


@click.group()
def items() -> None:
    """Hoerbuecher und Podcasts verwalten."""


@items.command("list")
@click.option("--library", "library_id", required=True, help="Bibliotheks-ID.")
@click.option("--missing", is_flag=True, default=False, help="Nur fehlende Items anzeigen.")
@click.option("--unmatched", is_flag=True, default=False, help="Nur Items ohne ASIN anzeigen.")
@click.option("--listened", is_flag=True, default=False, help="Nur gehoerte Items anzeigen.")
@click.option("--not-listened", is_flag=True, default=False, help="Nur ungehoerte Items anzeigen.")
@click.pass_context
def list_items(
    ctx: click.Context,
    library_id: str,
    missing: bool,
    unmatched: bool,
    listened: bool,
    not_listened: bool,
) -> None:
    """Items einer Bibliothek auflisten."""
    client: ABSClient = ctx.obj["client"]

    resp = client.get(f"/libraries/{library_id}/items", params={"limit": 0})
    resp.raise_for_status()
    data = resp.json()

    results = data.get("results", [])
    items_list = [LibraryItem.from_api(r) for r in results]

    # Hoerstatus vom /me Endpunkt laden und joinen
    me_resp = client.get("/me")
    me_resp.raise_for_status()
    progress_by_item: dict[str, dict] = {}
    for p in me_resp.json().get("mediaProgress", []):
        progress_by_item[p.get("libraryItemId", "")] = p

    for item in items_list:
        p = progress_by_item.get(item.id)
        if p:
            item.progress = p.get("progress", 0.0)
            item.is_finished = p.get("isFinished", False)

    if missing:
        items_list = [i for i in items_list if i.is_missing]
    if unmatched:
        items_list = [i for i in items_list if not i.asin]
    if listened:
        items_list = [i for i in items_list if i.is_finished]
    if not_listened:
        items_list = [i for i in items_list if not i.is_finished]

    if not items_list:
        console.print("[yellow]Keine Items gefunden.[/yellow]")
        return

    table = Table(title=f"Items ({len(items_list)})")
    table.add_column("ID", style="dim", no_wrap=True)
    table.add_column("Titel", style="bold")
    table.add_column("Autor")
    table.add_column("Dauer", justify="right")
    table.add_column("Status", justify="center")
    table.add_column("ASIN", justify="center")
    table.add_column("Fehlend", justify="center")

    for item in items_list:
        has_asin = "[green]Ja[/green]" if item.asin else "[red]Nein[/red]"
        is_missing_txt = "[red]Ja[/red]" if item.is_missing else "[green]Nein[/green]"
        if item.is_finished:
            status = "[green]Gehoert[/green]"
        elif item.progress > 0:
            status = f"[yellow]{item.progress * 100:.0f}%[/yellow]"
        else:
            status = "[dim]—[/dim]"
        table.add_row(
            item.id,
            item.title,
            item.author or "-",
            _format_duration(item.duration),
            status,
            has_asin,
            is_missing_txt,
        )

    console.print(table)


@items.command()
@click.argument("item_id")
@click.pass_context
def show(ctx: click.Context, item_id: str) -> None:
    """Detailansicht eines Items."""
    client: ABSClient = ctx.obj["client"]

    resp = client.get(f"/items/{item_id}")
    resp.raise_for_status()
    detail = ItemDetail.from_api(resp.json())

    lines: list[str] = []
    lines.append(f"[bold]Titel:[/bold]      {detail.title}")
    if detail.author:
        lines.append(f"[bold]Autor:[/bold]      {detail.author}")
    if detail.narrator:
        lines.append(f"[bold]Sprecher:[/bold]   {detail.narrator}")
    if detail.series_name:
        seq = f" #{detail.series_sequence}" if detail.series_sequence else ""
        lines.append(f"[bold]Serie:[/bold]      {detail.series_name}{seq}")
    lines.append(f"[bold]Dauer:[/bold]      {_format_duration(detail.duration)}")
    if detail.asin:
        lines.append(f"[bold]ASIN:[/bold]       {detail.asin}")
    if detail.isbn:
        lines.append(f"[bold]ISBN:[/bold]       {detail.isbn}")
    if detail.publisher:
        lines.append(f"[bold]Verlag:[/bold]     {detail.publisher}")
    if detail.publish_year:
        lines.append(f"[bold]Jahr:[/bold]       {detail.publish_year}")
    if detail.language:
        lines.append(f"[bold]Sprache:[/bold]    {detail.language}")
    if detail.genres:
        lines.append(f"[bold]Genres:[/bold]     {', '.join(detail.genres)}")
    lines.append(f"[bold]Tracks:[/bold]     {detail.num_tracks}")
    lines.append(f"[bold]Groesse:[/bold]    {_format_size(detail.size)}")
    is_missing = "[red]Ja[/red]" if detail.is_missing else "[green]Nein[/green]"
    lines.append(f"[bold]Fehlend:[/bold]    {is_missing}")

    content = "\n".join(lines)
    if detail.description:
        content += f"\n\n[bold]Beschreibung:[/bold]\n{detail.description}"

    console.print(Panel(content, title=detail.title, border_style="blue"))


@items.command()
@click.argument("item_id", required=False)
@click.option("--all", "match_all", is_flag=True, default=False, help="Alle Items der Bibliothek matchen.")
@click.option("--library", "library_id", default=None, help="Bibliotheks-ID (erforderlich mit --all).")
@click.option("--provider", default="audible", help="Metadaten-Provider.")
@click.pass_context
def match(
    ctx: click.Context,
    item_id: str | None,
    match_all: bool,
    library_id: str | None,
    provider: str,
) -> None:
    """Metadaten fuer ein Item matchen."""
    client: ABSClient = ctx.obj["client"]

    if match_all:
        if not library_id:
            raise click.UsageError("--library ist erforderlich wenn --all verwendet wird.")

        resp = client.get(f"/libraries/{library_id}/items", params={"limit": 0})
        resp.raise_for_status()
        results = resp.json().get("results", [])

        console.print(f"Matche {len(results)} Items mit Provider [bold]{provider}[/bold]...")

        success = 0
        errors = 0
        for item_data in results:
            iid = item_data["id"]
            title = item_data.get("media", {}).get("metadata", {}).get("title", iid)
            try:
                match_resp = client.post(f"/items/{iid}/match", json={"provider": provider})
                match_resp.raise_for_status()
                result = match_resp.json()
                updated = result.get("updated", False)
                status = "[green]aktualisiert[/green]" if updated else "[dim]keine Aenderung[/dim]"
                console.print(f"  {title}: {status}")
                success += 1
            except Exception as exc:
                console.print(f"  [red]{title}: Fehler - {exc}[/red]")
                errors += 1

        console.print(f"\nFertig: {success} erfolgreich, {errors} Fehler")
    else:
        if not item_id:
            raise click.UsageError("ITEM_ID ist erforderlich (oder verwende --all --library=ID).")

        resp = client.post(f"/items/{item_id}/match", json={"provider": provider})
        resp.raise_for_status()
        result = resp.json()

        updated = result.get("updated", False)
        if updated:
            console.print("[green]Item wurde aktualisiert.[/green]")
        else:
            console.print("[yellow]Keine Aenderungen gefunden.[/yellow]")


@items.command()
@click.argument("item_id")
@click.option("--dry-run/--no-dry-run", default=True, help="Nur anzeigen was geloescht wird (Standard: an).")
@click.option("--hard-delete", is_flag=True, default=False, help="Dateien auch vom Dateisystem loeschen.")
@click.pass_context
def delete(ctx: click.Context, item_id: str, dry_run: bool, hard_delete: bool) -> None:
    """Ein Item loeschen.

    Standardmaessig wird nur angezeigt, was geloescht wuerde (--dry-run).
    Verwende --no-dry-run um tatsaechlich zu loeschen.
    """
    client: ABSClient = ctx.obj["client"]

    resp = client.get(f"/items/{item_id}")
    resp.raise_for_status()
    detail = ItemDetail.from_api(resp.json())

    console.print(Panel(
        f"[bold]Titel:[/bold]   {detail.title}\n"
        f"[bold]Autor:[/bold]   {detail.author or '-'}\n"
        f"[bold]Tracks:[/bold]  {detail.num_tracks}\n"
        f"[bold]Groesse:[/bold] {_format_size(detail.size)}",
        title="Zu loeschendes Item",
        border_style="red",
    ))

    if dry_run:
        console.print("[yellow]Dry-Run: Es wurde nichts geloescht. Verwende --no-dry-run zum Loeschen.[/yellow]")
        return

    if not click.confirm("Wirklich loeschen?"):
        console.print("[yellow]Abgebrochen.[/yellow]")
        return

    params = {}
    if hard_delete:
        params["hard"] = 1

    del_resp = client.delete(f"/items/{item_id}", params=params)
    del_resp.raise_for_status()
    console.print(f"[green]Item '{detail.title}' wurde geloescht.[/green]")


@items.command()
@click.argument("query")
@click.option("--library", "library_id", required=True, help="Bibliotheks-ID.")
@click.pass_context
def search(ctx: click.Context, query: str, library_id: str) -> None:
    """Freitextsuche in einer Bibliothek."""
    client: ABSClient = ctx.obj["client"]

    resp = client.get(f"/libraries/{library_id}/search", params={"q": query})
    resp.raise_for_status()
    data = resp.json()

    book_results = data.get("book", data.get("podcast", []))
    author_results = data.get("authors", [])
    series_results = data.get("series", [])
    narrator_results = data.get("narrators", [])

    has_results = book_results or author_results or series_results or narrator_results

    if not has_results:
        console.print("[yellow]Keine Ergebnisse gefunden.[/yellow]")
        return

    if book_results:
        table = Table(title=f"Buecher ({len(book_results)})")
        table.add_column("ID", style="dim", no_wrap=True)
        table.add_column("Titel", style="bold")
        table.add_column("Autor")
        table.add_column("Dauer", justify="right")

        for result in book_results:
            lib_item = result.get("libraryItem", {})
            item = LibraryItem.from_api(lib_item)
            table.add_row(
                item.id,
                item.title,
                item.author or "-",
                _format_duration(item.duration),
            )
        console.print(table)

    if author_results:
        table = Table(title=f"Autoren ({len(author_results)})")
        table.add_column("Name", style="bold")
        table.add_column("Buecher", justify="right")
        for author in author_results:
            table.add_row(
                author.get("name", "-"),
                str(author.get("numBooks", 0)),
            )
        console.print(table)

    if series_results:
        table = Table(title=f"Serien ({len(series_results)})")
        table.add_column("Name", style="bold")
        table.add_column("Buecher", justify="right")
        for series in series_results:
            s = series.get("series", {})
            table.add_row(
                s.get("name", "-"),
                str(len(series.get("books", []))),
            )
        console.print(table)

    if narrator_results:
        table = Table(title=f"Sprecher ({len(narrator_results)})")
        table.add_column("Name", style="bold")
        for narrator in narrator_results:
            table.add_row(narrator.get("name", "-"))
        console.print(table)
