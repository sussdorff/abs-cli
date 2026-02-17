"""Audiobookshelf API Client."""

from __future__ import annotations

from typing import Any

import httpx


class ABSClient:
    """HTTP-Client fuer die Audiobookshelf API."""

    def __init__(self, server_url: str, api_token: str | None = None) -> None:
        headers = {}
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"

        self._client = httpx.Client(
            base_url=server_url.rstrip("/"),
            headers=headers,
        )

    def __enter__(self) -> ABSClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self._client.close()

    def get(self, path: str, **kwargs: Any) -> httpx.Response:
        """GET-Request an die API."""
        return self._client.get(f"/api{path}", **kwargs)

    def post(self, path: str, **kwargs: Any) -> httpx.Response:
        """POST-Request an die API."""
        return self._client.post(f"/api{path}", **kwargs)

    def patch(self, path: str, **kwargs: Any) -> httpx.Response:
        """PATCH-Request an die API."""
        return self._client.patch(f"/api{path}", **kwargs)

    def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        """DELETE-Request an die API."""
        return self._client.delete(f"/api{path}", **kwargs)
