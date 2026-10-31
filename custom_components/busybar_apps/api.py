"""
A small client for the BUSY Bar local HTTP API, for what this integration
needs: the apps (VeryBUSY firmware only: /api/apps/*), the timer snapshot
and key presses.

Found on a real bar (VeryBUSY r12, API 27.7):
- `GET /api/apps/running` -> {name, runtime, app_id, js_id}. Built-in apps
  come with runtime "" and only their name ("Clock"); a .fap with runtime
  "fap" and its path as app_id; a JS app with runtime "js" and its id.
- `POST /api/apps/launch?runtime=..&id=..` opens an app, even from the
  off state; the app opens on its Start screen, so OK starts it.
- Power off: `key=off` alone does nothing when the mode was already Off
  (an app launched from off), so it is `key=apps` then `key=off`.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import RUNTIMES, TIMER_APPID

APPS_DIR = "/ext/apps"  # installed apps, /ext/apps/<category>/<name>.fap
SCRIPTS_DIR = "/ext/user_assets"  # script apps, <id>/appmeta/manifest.json and <id>/scripts/
TIMEOUT = aiohttp.ClientTimeout(total=10)


class BusyBarError(Exception):
    """The bar answered with an error."""


class BusyBarConnectionError(BusyBarError):
    """The bar couldn't be reached."""


class BusyBarAuthError(BusyBarError):
    """The bar refused the password."""


@dataclass(frozen=True)
class BarApp:
    """An app the bar can open."""

    runtime: str
    app_id: str
    name: str

    @property
    def value(self) -> str:
        return f"{self.runtime}:{self.app_id}"


def parse_value(value: str) -> tuple[str, str]:
    """(runtime, app_id) of a "runtime:id" value; ValueError when it isn't one."""
    runtime, sep, app_id = value.partition(":")
    if not sep or runtime not in RUNTIMES or not app_id:
        raise ValueError(f"not an app: {value!r} (expected runtime:id, e.g. system:clock)")
    return runtime, app_id


class BusyBarApi:
    """Talks to one bar."""

    def __init__(self, session: aiohttp.ClientSession, host: str, password: str | None) -> None:
        host = host.strip().rstrip("/")
        if not host.startswith(("http://", "https://")):
            host = f"http://{host}"
        self._base = host
        self._session = session
        self._headers = {"X-API-Token": password} if password else {}

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, str] | None = None,
        raw: bool = False,
    ) -> Any:
        try:
            async with self._session.request(
                method,
                f"{self._base}{path}",
                params=params,
                data=b"" if method == "POST" else None,
                headers=self._headers,
                timeout=TIMEOUT,
            ) as resp:
                body = await resp.read()
                if resp.status in (401, 403):
                    raise BusyBarAuthError(f"{path}: HTTP {resp.status} (wrong password, or HTTP API off)")
                if resp.status >= 400:
                    raise BusyBarError(f"{path}: HTTP {resp.status} {body[:200]!r}")
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise BusyBarConnectionError(f"{path}: {err!r}") from err
        if raw:
            return body
        try:
            return json.loads(body) if body else {}
        except ValueError as err:
            raise BusyBarError(f"{path}: not JSON") from err

    # Reads

    async def status(self) -> dict:
        return await self._request("GET", "/api/status")

    async def name(self) -> str:
        return (await self._request("GET", "/api/name")).get("name", "")

    async def running(self) -> dict:
        """{name, runtime, app_id, js_id} of what is on the bar."""
        return await self._request("GET", "/api/apps/running")

    async def snapshot(self) -> dict:
        return await self._request("GET", "/api/busy/snapshot")

    async def system_apps(self) -> list[dict]:
        return (await self._request("GET", "/api/apps/system")).get("list", [])

    async def _list(self, path: str) -> list[dict]:
        return (await self._request("GET", "/api/storage/list", params={"path": path})).get("list", [])

    async def apps(self, system: list[dict] | None = None) -> list[BarApp]:
        """
        The apps this bar can open: the built-in ones (the timer left out),
        then the installed .fap and script apps, by name.
        """
        if system is None:
            system = await self.system_apps()
        builtin = [
            BarApp("system", a["appid"], a.get("name") or a["appid"])
            for a in system
            if a.get("group") == "apps" and not a.get("blocked") and a.get("appid") not in ("", TIMER_APPID)
        ]
        installed = [*await self._faps(), *await self._script_apps()]
        return builtin + sorted(installed, key=lambda a: a.name.casefold())

    async def _faps(self) -> list[BarApp]:
        found: list[BarApp] = []
        try:
            folders = [e["name"] for e in await self._list(APPS_DIR) if e.get("type") == "dir"]
        except BusyBarError:
            return found
        for folder in folders:
            for entry in await self._list(f"{APPS_DIR}/{folder}"):
                name = entry.get("name", "")
                if entry.get("type") == "file" and name.endswith(".fap"):
                    found.append(BarApp("fap", f"{APPS_DIR}/{folder}/{name}", name.removesuffix(".fap")))
        return found

    async def _script_apps(self) -> list[BarApp]:
        """JavaScript and MicroPython apps: a folder with appmeta/ and scripts/ (others are app data)."""
        try:
            folders = [e["name"] for e in await self._list(SCRIPTS_DIR) if e.get("type") == "dir"]
        except BusyBarError:
            return []
        found: list[BarApp] = []
        for folder in folders:
            base = f"{SCRIPTS_DIR}/{folder}"
            try:
                if {"appmeta", "scripts"} - {e.get("name") for e in await self._list(base)}:
                    continue
                scripts = [e.get("name", "") for e in await self._list(f"{base}/scripts")]
                raw = await self._request("GET", "/api/storage/read", params={"path": f"{base}/appmeta/manifest.json"}, raw=True)
                manifest = json.loads(raw)
            except (BusyBarConnectionError, BusyBarAuthError):
                raise
            except (BusyBarError, ValueError):
                continue
            if manifest.get("debug"):
                continue
            runtime = "js" if any(n.endswith(".js") for n in scripts) else "python"
            app_id = str(manifest.get("id") or folder)
            found.append(BarApp(runtime, app_id, str(manifest.get("name") or app_id)))
        return found

    # Actions

    async def launch(self, runtime: str, app_id: str) -> None:
        """Open an app (on its Start screen); press("ok") then starts it."""
        await self._request("POST", "/api/apps/launch", params={"runtime": runtime, "id": app_id})

    async def press(self, key: str) -> None:
        """A key press, or a move of the mode switch (busy, custom, off, apps, settings)."""
        await self._request("POST", "/api/input", params={"key": key})


def running_value(running: dict, system: list[dict]) -> str:
    """The "runtime:id" of what runs, "" when it can't be told (built-ins come by name only)."""
    runtime = running.get("runtime") or ""
    if runtime:
        return f"{runtime}:{running.get('app_id') or running.get('js_id') or ''}"
    name = running.get("name") or ""
    for app in system:
        if app.get("name") == name and app.get("appid"):
            return f"system:{app['appid']}"
    return ""
