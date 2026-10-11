"""Helpers shared by the vendor backends (Jev, Claude). Owner: LAB-B.

Provenance rule (types.py, LL5): anything that talked to the local stub is MOCK, whatever the
config claims. LIVE is only possible when the effective base URL is a non-loopback host AND the
response did not carry the stub watermark header.
"""
from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlparse

from jevlab.stub_server import DUMMY_KEY, MOCK_HEADER

__all__ = ["DUMMY_KEY", "MOCK_HEADER", "is_loopback_url", "provenance", "resolve_api_key"]


def is_loopback_url(url: str | None) -> bool:
    if not url:
        return False
    host = (urlparse(url).hostname or "").strip("[]")
    if host in ("localhost", ""):
        return host == "localhost"
    try:
        return ipaddress.ip_address(host).is_loopback or ipaddress.ip_address(host).is_unspecified
    except ValueError:
        return False


def provenance(backend: str, model: str, *, mode: str, base_url: str | None, mock_header_seen: bool) -> str:
    """'MOCK:<backend>' for the stub; 'LIVE:<backend>:<model>' only for a real remote API."""
    if mode == "stub" or mock_header_seen or is_loopback_url(base_url):
        return f"MOCK:{backend}"
    return f"LIVE:{backend}:{model}"


def resolve_api_key(mode: str, env_var: str, base_url: str | None, backend: str, signup_hint: str) -> str:
    """Stub mode: always the dummy key (never forward a real key from the environment to the stub).
    Live mode: the user's key from env_var; fail loudly if absent."""
    if mode == "stub":
        if not is_loopback_url(base_url):
            raise RuntimeError(
                f"{backend}: stub mode requires a loopback base_url (got {base_url!r}); refusing to send the "
                "dummy key to a remote host")
        return DUMMY_KEY
    if mode != "live":
        raise ValueError(f"{backend}: mode must be 'stub' or 'live', got {mode!r}")
    key = (os.environ.get(env_var) or "").strip()
    if not key:
        raise RuntimeError(f"{backend}: live mode needs ${env_var}. {signup_hint}")
    if is_loopback_url(base_url):
        raise RuntimeError(f"{backend}: live mode with a loopback base_url ({base_url}) would send your real key "
                           "to the stub; use mode: stub instead")
    return key
