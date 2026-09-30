"""Small read-only HTTPS transport. No browser cookies or ambient proxy settings."""

from __future__ import annotations

import base64
import http.client
import ipaddress
import json
import os
import random
import socket
import ssl
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urlsplit, urlunsplit, unquote


class ConnectorError(Exception):
    """Safe diagnostic: never include upstream response bodies or credentials."""


class AccessRevoked(ConnectorError):
    """Authorization was denied; persistence must quarantine retained observations."""


class RecordUnavailable(ConnectorError):
    """404 is ambiguous: deleted, hidden, or missing. It is not proof of deletion."""


def endpoint_parts(url):
    try:
        parts = urlsplit(url)
        port = parts.port or 443
    except (TypeError, ValueError):
        raise ConnectorError("Invalid integration endpoint.") from None
    path = unquote(parts.path)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.fragment
        or "\\" in url
        or any(ord(c) < 32 for c in url)
        or any(s in (".", "..") for s in path.split("/"))
    ):
        raise ConnectorError(
            "Integration endpoints require HTTPS and a canonical URL without credentials."
        )
    return parts, (parts.hostname.lower(), port), path.rstrip("/")


class HttpTransport:
    MAX_BYTES = 2 * 1024 * 1024

    def __init__(self, config, credentials=None):
        self.base_url = str(config.get("base_url", "")).rstrip("/")
        self.options = config.get("config", {})
        parts, self.origin, self.base_path = endpoint_parts(self.base_url)
        if parts.query:
            raise ConnectorError("Base endpoints cannot contain query parameters.")
        allowed = self.options.get("allowed_endpoints", [])
        if not isinstance(allowed, list) or self.base_url not in [
            str(v).rstrip("/") for v in allowed
        ]:
            raise ConnectorError("Base URL must be explicitly listed in config.allowed_endpoints.")
        # Deployment owner must approve egress independently from source admins.
        server_allowed = os.environ.get("WORKLENS_ALLOWED_ENDPOINTS", "")
        if not server_allowed:
            raise ConnectorError(
                "Live integrations are denied until WORKLENS_ALLOWED_ENDPOINTS is configured by the deployment owner."
            )
        if self.base_url not in [v.strip().rstrip("/") for v in server_allowed.split(",")]:
            raise ConnectorError("Endpoint is outside the deployment egress allowlist.")
        self.allow_private = self.options.get("allow_private_hosts") is True
        self.credentials = credentials or config.get("credentials") or {}
        if isinstance(self.credentials, str):
            self.credentials = {"token": self.credentials}
        if not isinstance(self.credentials, dict):
            raise ConnectorError("Credentials must be configured locally as an object.")
        self.retries = min(max(int(self.options.get("retries", 3)), 0), 5)
        self.timeout = min(max(float(self.options.get("timeout", 15)), 1), 60)
        self.min_interval = min(max(float(self.options.get("min_interval", 0.1)), 0), 10)
        self._last_request = 0.0
        self._ssl = ssl.create_default_context(cafile=os.environ.get("WORKLENS_CA_BUNDLE") or None)

    def url(self, path):
        return path if "://" in path else self.base_url + "/" + path.lstrip("/")

    def validate_url(self, url):
        parts, origin, path = endpoint_parts(url)
        if origin != self.origin or not (
            path == self.base_path or path.startswith(self.base_path + "/")
        ):
            raise ConnectorError("Request destination is outside the configured endpoint.")
        return parts

    def _resolve(self, host, port):
        try:
            addresses = list(
                dict.fromkeys(
                    i[4][0] for i in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
                )
            )
        except OSError:
            raise ConnectorError("Integration DNS lookup failed.") from None
        if not addresses:
            raise ConnectorError("Integration DNS lookup returned no addresses.")
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
                ip = ip.ipv4_mapped
            if (
                ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_unspecified
                or ip.is_reserved
            ):
                raise ConnectorError("Integration resolves to a prohibited network address.")
            if not ip.is_global and not (self.allow_private and ip.is_private):
                raise ConnectorError(
                    "Private integration addresses require explicit administrator approval."
                )
        return addresses[0]

    def _headers(self):
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": "WorkLens/1.0",
        }
        token = str(self.credentials.get("token", ""))
        if token:
            if any(ord(c) < 32 for c in token):
                raise ConnectorError("Invalid credential format.")
            if self.credentials.get("auth_type", "bearer") == "basic":
                user = self.credentials.get("email") or self.credentials.get("username", "")
                encoded = base64.b64encode(f"{user}:{token}".encode()).decode()
                headers["Authorization"] = "Basic " + encoded
            else:
                headers["Authorization"] = "Bearer " + token
        return headers

    def _perform(self, url, headers):
        parts = self.validate_url(url)
        port = parts.port or 443
        address = self._resolve(parts.hostname, port)
        proxy = os.environ.get("WORKLENS_EGRESS_PROXY", "")
        if proxy:
            proxy_parts = urlsplit(proxy)
            if (
                proxy_parts.scheme != "http"
                or not proxy_parts.hostname
                or proxy_parts.username
                or proxy_parts.password
                or proxy_parts.query
                or proxy_parts.fragment
                or proxy_parts.path not in ("", "/")
            ):
                raise ConnectorError(
                    "Deployment egress proxy must be a plain HTTP CONNECT endpoint."
                )
            connection = http.client.HTTPSConnection(
                proxy_parts.hostname,
                proxy_parts.port or 3128,
                timeout=self.timeout,
                context=self._ssl,
            )
            connection.set_tunnel(parts.hostname, port)
        else:
            connection = http.client.HTTPSConnection(
                parts.hostname, port, timeout=self.timeout, context=self._ssl
            )
            # Pin the checked address, keeping original Host/SNI and certificate verification.
            connection._create_connection = lambda addr, timeout=None, source_address=None: (
                socket.create_connection((address, port), timeout, source_address)
            )
        try:
            connection.request(
                "GET", urlunsplit(("", "", parts.path or "/", parts.query, "")), headers=headers
            )
            response = connection.getresponse()
            response_headers = {k.lower(): v for k, v in response.getheaders()}
            if response_headers.get("content-encoding", "identity") not in ("", "identity"):
                raise ConnectorError("Compressed integration responses are not accepted.")
            payload = response.read(self.MAX_BYTES + 1)
            if len(payload) > self.MAX_BYTES:
                raise ConnectorError(
                    "Integration response exceeds the 2 MiB limit; reduce page size."
                )
            return response.status, response_headers, payload
        finally:
            connection.close()

    @staticmethod
    def _retry_delay(headers, attempt):
        raw = headers.get("retry-after", "")
        try:
            delay = float(raw)
        except ValueError:
            try:
                delay = (parsedate_to_datetime(raw) - datetime.now(timezone.utc)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                delay = 2**attempt + random.random()
        return max(0, min(delay, 30))

    def get(self, path, params=None):
        url = self.url(path)
        if params:
            url += ("&" if "?" in url else "?") + urlencode(params, doseq=True)
        self.validate_url(url)
        headers = self._headers()
        for attempt in range(self.retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()
            try:
                status, response_headers, payload = self._perform(url, headers)
            except (OSError, http.client.HTTPException):
                if attempt < self.retries:
                    time.sleep(self._retry_delay({}, attempt))
                    continue
                raise ConnectorError("Integration network or TLS request failed.") from None
            if status in (401, 403):
                raise AccessRevoked(
                    "Source credentials or read permissions were denied; retained data must be restricted."
                )
            if status == 404:
                raise RecordUnavailable(
                    "Source resource is missing or no longer visible; deletion is unconfirmed."
                )
            if 300 <= status < 400:
                raise ConnectorError(
                    "Integration redirect refused; configure the final approved HTTPS endpoint."
                )
            if status == 429 or 500 <= status <= 599:
                if attempt < self.retries:
                    time.sleep(self._retry_delay(response_headers, attempt))
                    continue
                raise ConnectorError(f"Source returned HTTP {status}; retry budget exhausted.")
            if status != 200:
                raise ConnectorError(
                    f"Source returned HTTP {status}; verify API version, scopes, and selected fields."
                )
            try:
                value = json.loads(payload)
            except (ValueError, UnicodeError):
                raise ConnectorError("Source returned invalid JSON.") from None
            if not isinstance(value, dict):
                raise ConnectorError("Source returned an unexpected JSON shape.")
            return value
        raise ConnectorError("Integration retry budget exhausted.")
