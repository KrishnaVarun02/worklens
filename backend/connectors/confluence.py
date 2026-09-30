"""Confluence metadata only: page bodies, comments, attachments and likes are excluded."""

from .base import Adapter, account, identifier, instant, text
from .transport import ConnectorError, RecordUnavailable


class ConfluenceBase(Adapter):
    kind = "confluence"

    def page_url(self, raw):
        link = raw.get("_links", {}).get("webui", "")
        if not link or "://" in link:
            return link
        return self.base_url + "/" + link.lstrip("/")

    def review_values(self, value):
        if not isinstance(value, dict):
            return []
        reviews = value.get("reviews", [])
        if not isinstance(reviews, list):
            return []
        result = []
        for item in reviews[:100]:
            if not isinstance(item, dict) or item.get("verdict") not in (
                "accepted",
                "changes_requested",
            ):
                continue
            result.append(
                {
                    "reviewer_account_id": text(item.get("reviewer_account_id")),
                    "reviewed_at": instant(item.get("reviewed_at")),
                    "verdict": item["verdict"],
                    "evidence_url": self.evidence_url(item.get("evidence_url")),
                }
            )
        return result


class ConfluenceCloudAdapter(ConfluenceBase):
    deployment = "cloud"

    def fetch_page(self, scope, token, since):
        if not scope.isdigit():
            raise ConnectorError("Confluence Cloud scopes must be numeric space IDs.")
        path = "api/v2/pages"
        params = {"space-id": scope, "limit": self.page_size, "status": "current", "sort": "id"}
        if token:
            params["cursor"] = token
        result = self.transport.get(path, params)
        if "results" not in result:
            raise ConnectorError("Confluence Cloud did not return a results collection.")
        # v2 does not provide an updated-since filter: scan metadata and filter locally.
        return [self.normalize(raw, scope) for raw in result["results"]], self.next_cursor(
            result.get("_links", {}).get("next"), path, "cursor"
        )

    def normalize(self, raw, scope):
        if str(raw.get("spaceId", scope)) != scope:
            raise ConnectorError("Confluence returned a page outside the configured space.")
        page_id = identifier(raw["id"])
        version = raw.get("version", {})
        data = self.selected(
            {
                "status": raw.get("status"),
                "version": {
                    "number": version.get("number"),
                    "at": instant(version.get("createdAt")),
                    "author": account(version.get("authorId")),
                },
                "ownership": {"account_id": text(raw.get("ownerId"))},
            }
        )
        if "revisions" in self.fields:
            revisions, token, path = [], None, "api/v2/pages/" + page_id + "/versions"
            for _ in range(self.max_nested_pages):
                result = self.transport.get(
                    path, {"limit": self.page_size, **({"cursor": token} if token else {})}
                )
                if "results" not in result:
                    raise ConnectorError("Confluence did not return a revision collection.")
                revisions.extend(
                    {
                        "number": v.get("number"),
                        "at": instant(v.get("createdAt")),
                        "author": account(v.get("authorId")),
                    }
                    for v in result.get("results", [])
                )
                token = self.next_cursor(result.get("_links", {}).get("next"), path, "cursor")
                if token is None:
                    break
            else:
                raise ConnectorError("Confluence revision pagination exceeded its budget.")
            revisions = list({v["number"]: v for v in revisions}.values())
            numbers = {
                v["number"] for v in revisions if isinstance(v["number"], int) and v["number"] > 0
            }
            current = version.get("number")
            complete = bool(
                numbers
                and isinstance(current, int)
                and len(numbers) == current
                and min(numbers) == 1
                and max(numbers) == current
            )
            data.update(revisions=revisions, revisions_complete=complete)
        if "reviews" in self.fields:
            key = self.options.get("review_property_key")
            data["reviews"] = []
            data["reviews_coverage"] = "not_configured"
            if key:
                result = self.transport.get(
                    "api/v2/pages/" + page_id + "/properties", {"key": identifier(key), "limit": 10}
                )
                for prop in result.get("results", []):
                    if prop.get("key") == key:
                        data["reviews"].extend(self.review_values(prop.get("value")))
                data["reviews_coverage"] = "explicit_content_property"
        return self.record(
            page_id,
            scope,
            raw,
            title=raw.get("title"),
            url=self.page_url(raw),
            created=raw.get("createdAt"),
            updated=version.get("createdAt") or raw.get("createdAt"),
            user=raw.get("authorId"),
            data=data,
            kind="document",
        )


class ConfluenceDataCenterAdapter(ConfluenceBase):
    deployment = "data_center"

    def fetch_page(self, scope, token, since):
        path = "rest/api/content/search"
        cql = f'type = page AND space = "{scope}"'
        if since:
            cql += ' AND lastmodified >= "' + self.query_minute(since) + '"'
        cql += " ORDER BY lastmodified ASC"
        params = {
            "cql": cql,
            "start": int(token or 0),
            "limit": self.page_size,
            "expand": "space,history,version",
        }
        result = self.transport.get(path, params)
        if "results" not in result:
            raise ConnectorError("Confluence Data Center did not return a results collection.")
        return [self.normalize(raw, scope) for raw in result["results"]], self.next_cursor(
            result.get("_links", {}).get("next"), path, "start"
        )

    def normalize(self, raw, scope):
        if raw.get("space", {}).get("key", scope) != scope:
            raise ConnectorError("Confluence returned a page outside the configured space.")
        page_id = identifier(raw["id"])
        version, history = raw.get("version", {}), raw.get("history", {})
        revision = {
            "number": version.get("number"),
            "at": instant(version.get("when")),
            "author": account(version.get("by"), "email" in self.fields),
        }
        data = self.selected(
            {
                "status": raw.get("status"),
                "version": revision,
                "ownership": {
                    "account_id": None,
                    "basis": "not_available_in_standard_content_metadata",
                },
            }
        )
        if "revisions" in self.fields:
            current = int(version.get("number") or 0)
            revisions, missing = [], []
            start = max(1, current - self.max_nested_pages)
            for number in range(start, current):
                try:
                    historical = self.transport.get(
                        "rest/api/content/" + page_id,
                        {"status": "historical", "version": number, "expand": "version"},
                    )
                except RecordUnavailable:
                    missing.append(
                        number
                    )  # Version deletion and visibility restrictions are indistinguishable.
                    continue
                prior = historical.get("version", {})
                if prior.get("number") != number:
                    raise ConnectorError(
                        "Confluence did not return the requested historical revision."
                    )
                revisions.append(
                    {
                        "number": number,
                        "at": instant(prior.get("when")),
                        "author": account(prior.get("by"), "email" in self.fields),
                    }
                )
            revisions.append(revision)
            data.update(
                revisions=revisions,
                revisions_complete=current >= 1 and start == 1 and not missing,
                revisions_coverage="bounded_historical_metadata",
                revisions_missing=missing,
                revisions_earliest_requested=start,
            )
        if "reviews" in self.fields:
            key = self.options.get("review_property_key")
            data.update(reviews=[], reviews_coverage="not_configured")
            if key:
                try:
                    result = self.transport.get(
                        "rest/api/content/" + page_id + "/property/" + identifier(key)
                    )
                    data["reviews"] = self.review_values(result.get("value"))
                    data["reviews_coverage"] = "explicit_content_property"
                except RecordUnavailable:
                    # The optional property may not exist; the already-visible page is unaffected.
                    data["reviews_coverage"] = "property_missing_or_unavailable"
        return self.record(
            page_id,
            scope,
            raw,
            title=raw.get("title"),
            url=self.page_url(raw),
            created=history.get("createdDate"),
            updated=version.get("when"),
            user=history.get("createdBy"),
            data=data,
            kind="document",
        )
