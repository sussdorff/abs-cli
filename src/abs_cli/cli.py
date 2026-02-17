"""CLI-Einstiegspunkt fuer abs-cli."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from abs_cli.client import ABSClient
from abs_cli.commands.items import items
from abs_cli.commands.library import library
from abs_cli.commands.progress import progress
from abs_cli.config import load_config


class _LazyContext(dict[str, Any]):
    """Dict-Subklasse die den API-Client lazy initialisiert."""

    def __init__(self, config_path: Path | None) -> None:
        super().__init__()
        self._config_path = config_path
        self._client: ABSClient | None = None

    def __getitem__(self, key: str) -> Any:
        if key == "client":
            return self._get_client()
        return super().__getitem__(key)

    def _get_client(self) -> ABSClient:
        if self._client is None:
            try:
                config = load_config(self._config_path) if self._config_path else load_config()
            except FileNotFoundError:
                raise click.ClickException(
                    "Konfigurationsdatei nicht gefunden. Erstelle ~/.config/abs-cli/config.toml"
                )
            self._client = ABSClient(config.server_url, config.api_token)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client._client.close()


@click.group()
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Pfad zur Konfigurationsdatei.",
)
@click.pass_context
def cli(ctx: click.Context, config_path: Path | None) -> None:
    """Audiobookshelf CLI."""
    lazy_ctx = _LazyContext(config_path)
    ctx.obj = lazy_ctx
    ctx.call_on_close(lazy_ctx.close)


cli.add_command(library)
cli.add_command(items)
cli.add_command(progress)
