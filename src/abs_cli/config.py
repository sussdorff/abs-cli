"""Konfiguration fuer abs-cli."""

import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "abs-cli" / "config.toml"


@dataclass
class Config:
    """Audiobookshelf-Verbindungskonfiguration."""

    server_url: str
    api_token: str | None = None


def _read_token_from_1password() -> str | None:
    """Versucht den API-Token aus 1Password zu lesen."""
    try:
        result = subprocess.run(
            ["op", "read", "op://Private/Audiobookshelf/API Token"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    """Laedt die Konfiguration aus der TOML-Datei.

    Falls kein api_token in der Konfiguration vorhanden ist,
    wird versucht, diesen aus 1Password zu lesen.

    Args:
        path: Pfad zur Konfigurationsdatei

    Returns:
        Geladene Konfiguration

    Raises:
        FileNotFoundError: Konfigurationsdatei existiert nicht
        KeyError: server_url fehlt in der Konfiguration
    """
    data = tomllib.loads(path.read_text())

    server_url = data["server_url"]
    api_token = data.get("api_token")

    if not api_token:
        api_token = _read_token_from_1password()

    return Config(server_url=server_url, api_token=api_token)
