"""The region guard: send nothing to Claude or Codex while this machine's connection comes out in a
region the traveller has ruled out (``blocked_regions``, by default mainland China, Hong Kong, Macau
and Taiwan).

Before every agent run, and every ``region_check_s`` seconds during one, the runner asks public
geolocation services for the country of this machine's public IP, over the same route the agent's
own CLI takes: Claude Code follows ``HTTPS_PROXY`` / ``HTTP_PROXY`` (it does not use SOCKS, so an
``ALL_PROXY`` alone means it connects directly), Codex also follows ``ALL_PROXY``. A system-wide VPN
(TUN mode) covers every route. In a blocked region the agent does not start, or its whole
process group (the CLI, its MCP servers, its browser) is frozen with SIGSTOP; once the connection is
back outside, it continues (SIGCONT). Until a first lookup succeeds, and after two failed lookups in a
row, the region counts as blocked.

It is a guard, not a guarantee: it checks on a timer, so whatever the agent sent in the seconds before
a check has already gone out. A VPN's own kill switch closes that gap.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable

from econoclast.log import get_logger

log = get_logger("region")

REGION_NAMES = {"CN": "mainland China", "HK": "Hong Kong", "MO": "Macau", "TW": "Taiwan"}
_LOOKUPS: tuple[tuple[str, str], ...] = (
    ("https://api.country.is/", "country"),
    ("https://ipinfo.io/json", "country"),
)


_API_HOSTS = {"claude": "api.anthropic.com", "codex": "chatgpt.com"}
_PROXY_ENV = {
    "claude": ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"),
    "codex": ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"),
}


def proxy_from_env(backend: str = "claude") -> str | None:
    """The proxy that agent's CLI would take, from the environment (not macOS's system proxy setting)."""
    from urllib.request import proxy_bypass_environment

    if proxy_bypass_environment(_API_HOSTS.get(backend, "chatgpt.com")):  # NO_PROXY sends it direct
        return None
    for key in _PROXY_ENV.get(backend, _PROXY_ENV["codex"]):
        if os.environ.get(key):
            return os.environ[key]
    return None


def lookup_country(timeout: float = 6.0, *, backend: str = "claude") -> str | None:
    """ISO country code of this machine's public IP as seen over that agent's route, or None when no
    service answered."""
    import httpx

    try:
        client = httpx.Client(proxy=proxy_from_env(backend), trust_env=False, timeout=timeout,
                              headers={"User-Agent": "econoclast-region-guard"})
    except Exception as exc:  # noqa: BLE001 - e.g. a socks proxy without socksio installed
        log.warning("region lookup unavailable: %s", exc)
        return None
    with client:
        for url, field in _LOOKUPS:
            try:
                r = client.get(url)
                r.raise_for_status()
                code = str(r.json().get(field) or "").strip().upper()
                if re.fullmatch(r"[A-Z]{2}", code):
                    return code
            except Exception as exc:  # noqa: BLE001 - try the next service
                log.info("region lookup via %s failed: %s", url, exc)
    return None


class RegionGuard:
    """Remembers the last answer, so a single failed lookup does not flip a running hunt into a pause."""

    def __init__(self, blocked: list[str], *, lookup: Callable[[], str | None] = lookup_country,
                 strikes: int = 2) -> None:
        self.blocked = {c.strip().upper() for c in blocked if c and c.strip()}
        self.lookup = lookup
        self.strikes = strikes
        self.failures = 0
        self.last: str | None = None

    def check(self) -> tuple[bool, str | None]:
        """(safe, country code or None)."""
        code = self.lookup()
        if code:
            self.failures, self.last = 0, code
            return code not in self.blocked, code
        self.failures += 1
        if self.failures >= self.strikes or self.last is None:
            return False, None
        return self.last not in self.blocked, self.last


def region_name(code: str | None) -> str:
    return REGION_NAMES.get(code or "", code or "an unverified region")
