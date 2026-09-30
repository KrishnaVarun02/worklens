"""Normalized, resumable adapter contract shared by explicitly separate APIs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from urllib.parse import urljoin, urlsplit, parse_qs
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .transport import ConnectorError, HttpTransport

FIELDS = frozenset(
    {
        "title",
        "status",
        "assignee",
        "due_date",
        "priority",
        "sprints",
        "dependencies",
        "outcomes",
        "changelog",
        "reviewers",
        "approvals",
        "merge",
        "builds",
        "version",
        "ownership",
        "revisions",
        "reviews",
        "email",
        "labels",
        "work_type",
        "authorship",
    }
)


def text(value, limit=500):
    return str(value or "")[:limit]


def instant(value):
    if not value:
        return None
    if isinstance(value, (float, int)):
        return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat()
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).isoformat()
    except (ValueError, TypeError):
        return None


def after_since(value, since):
    if not since or not instant(value):
        return True  # Missing timestamps remain unknown, not silently discarded.
    return datetime.fromisoformat(instant(value)) >= datetime.fromisoformat(instant(since))


def account(value, include_email=False):
    value = value or {}
    if not isinstance(value, dict):
        return {"account_id": text(value), "email": ""}
    return {
        "account_id": text(
            value.get("accountId")
            or value.get("uuid")
            or value.get("userKey")
            or value.get("key")
            or value.get("id")
            or value.get("name")
            or value.get("username")
        ),
        "email": text(value.get("emailAddress") or value.get("email"), 254).lower()
        if include_email
        else "",
    }


def identifier(value):
    value = str(value)
    if not re.fullmatch(r"[A-Za-z0-9_{}~.:-]{1,180}", value) or value in (".", ".."):
        raise ConnectorError("Source returned an invalid record identifier.")
    return value


class Adapter:
    kind = ""
    deployment = ""

    def __init__(self, config, credentials=None, transport=None):
        self.config = config
        self.options = config.get("config", {})
        self.scopes = list(dict.fromkeys(str(v) for v in config.get("scopes", [])))
        if not self.scopes or len(self.scopes) > 100:
            raise ConnectorError("Select between 1 and 100 explicit source scopes.")
        for scope in self.scopes:
            if (
                not re.fullmatch(r"[A-Za-z0-9_{}~.:-]+(?:/[A-Za-z0-9_{}~.:-]+)?", scope)
                or ".." in scope
            ):
                raise ConnectorError(
                    "Invalid source scope; use an exact project, repository, or space identifier."
                )
        raw_fields = config.get("fields", [])
        self.fields = set(raw_fields)
        if self.fields - FIELDS:
            raise ConnectorError("Unsupported field allowlist; see docs/CONNECTORS.md.")
        self.page_size = min(max(int(self.options.get("page_size", 50)), 1), 100)
        self.max_nested_pages = min(max(int(self.options.get("max_nested_pages", 100)), 1), 1000)
        self.transport = transport or HttpTransport(config, credentials)
        self.base_url = config.get("base_url", "").rstrip("/")
        stable = {
            "kind": self.kind,
            "deployment": self.deployment,
            "base_url": self.base_url,
            "scopes": self.scopes,
            "fields": sorted(self.fields),
            "field_map": self.options.get("field_map", {}),
            "source_timezone": self.options.get("source_timezone", "UTC"),
            "review_property_key": self.options.get("review_property_key"),
        }
        self.fingerprint = hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()[
            :24
        ]

    def record(
        self,
        external_id,
        scope,
        raw,
        title="",
        url="",
        created=None,
        updated=None,
        user=None,
        data=None,
        kind=None,
        deleted=False,
    ):
        identity = (
            account(user, "email" in self.fields)
            if ({"assignee", "authorship"} & self.fields)
            else {"account_id": "", "email": ""}
        )
        return {
            "external_id": str(external_id),
            "kind": kind or self.kind,
            "scope": scope,
            "title": text(title) if "title" in self.fields else "",
            "url": self.evidence_url(url),
            "occurred_at": instant(created),
            "updated_at": instant(updated),
            **identity,
            "data": data or {},
            "deleted": bool(deleted),
        }

    def evidence_url(self, url):
        # Evidence URLs are stored, never fetched; nevertheless exclude active schemes and credentials.
        if not url:
            return ""
        value = urljoin(self.base_url + "/", str(url))
        p = urlsplit(value)
        return (
            value[:2000]
            if p.scheme == "https" and p.hostname and not p.username and not p.password
            else ""
        )

    def next_cursor(self, link, path, key):
        if not link:
            return None
        # Confluence emits API-relative links beginning /rest/ or /api/v2/ even
        # when the server lives under /confluence or /wiki.
        full = (
            self.transport.url(link)
            if link.startswith(("/rest/", "/api/v2/"))
            else urljoin(self.base_url + "/", link)
        )
        self.transport.validate_url(full)
        expected = urlsplit(self.transport.url(path))
        actual = urlsplit(full)
        if actual.path.rstrip("/") != expected.path.rstrip("/"):
            raise ConnectorError("Source pagination changed the authorized resource path.")
        values = parse_qs(actual.query).get(key)
        if not values:
            raise ConnectorError("Source pagination omitted its documented cursor.")
        return values[0]

    def iter_pages(self, cursor=None):
        state = dict(cursor or {})
        if state.get("fingerprint") not in (None, self.fingerprint):
            raise ConnectorError("Source configuration changed; reset the synchronization cursor.")
        if state.get("complete"):
            state = {"since": state.get("since")}
        since = state.get("since") or self.options.get("since")
        if since:
            parsed = instant(since)
            if not parsed:
                raise ConnectorError("Incremental since must be an ISO 8601 date or timestamp.")
            # Server-side minute precision and concurrent edits require a replay overlap.
            since = (
                (datetime.fromisoformat(parsed) - timedelta(minutes=5)).isoformat()
                if not state.get("started_at")
                else parsed
            )
        started = state.get("started_at") or datetime.now(timezone.utc).isoformat()
        scope_index = int(state.get("scope_index", 0))
        token = state.get("page")
        if not 0 <= scope_index <= len(self.scopes):
            raise ConnectorError("Invalid synchronization scope cursor.")
        seen = set()
        pages = 0
        while scope_index < len(self.scopes):
            signature = (scope_index, str(token))
            if signature in seen:
                raise ConnectorError(
                    "Source repeated a pagination cursor; sync stopped without advancing it."
                )
            seen.add(signature)
            records, next_token = self.fetch_page(self.scopes[scope_index], token, since)
            records = [r for r in records if after_since(r.get("updated_at"), since)]
            if next_token is None:
                scope_index += 1
                token = None
            else:
                token = next_token
            complete = scope_index == len(self.scopes)
            checkpoint = {
                "fingerprint": self.fingerprint,
                "scope_index": scope_index,
                "page": token,
                "since": started if complete else since,
                "started_at": started,
                "complete": complete,
            }
            yield {"records": records, "cursor": checkpoint, "complete": complete}
            pages += 1
            if pages >= 10000:
                raise ConnectorError(
                    "Synchronization page budget exhausted; resume from persisted cursor."
                )
        if pages == 0:
            yield {
                "records": [],
                "cursor": {"fingerprint": self.fingerprint, "since": started, "complete": True},
                "complete": True,
            }

    def test_connection(self):
        # Check every authorized scope, using actual read endpoints rather than unrelated identity endpoints.
        for scope in self.scopes:
            self.fetch_page(scope, None, None)
        return {
            "ok": True,
            "diagnostics": [
                "Read access checked for every configured scope.",
                "No write operation was attempted; grant only read permissions at the source.",
            ],
            "coverage": {
                "scopes": self.scopes,
                "fields": sorted(self.fields),
                "deployment": self.deployment,
                "live_verification": "Connection tested against configured endpoint",
            },
        }

    def selected(self, data):
        return {k: v for k, v in data.items() if k in self.fields}

    def query_minute(self, since):
        # JQL/CQL date literals are interpreted in the source account's timezone.
        try:
            source_zone = ZoneInfo(self.options.get("source_timezone", "UTC"))
        except (ZoneInfoNotFoundError, ValueError, TypeError):
            raise ConnectorError(
                "source_timezone must name the source service account's IANA timezone."
            ) from None
        return (
            datetime.fromisoformat(instant(since))
            .astimezone(source_zone)
            .strftime("%Y-%m-%d %H:%M")
        )

    def fetch_page(self, scope, token, since):
        raise NotImplementedError
