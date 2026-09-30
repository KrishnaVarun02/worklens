"""Jira Cloud enhanced search and Jira Data Center v2 are separate adapters."""

from .base import Adapter, account, identifier, instant, text
from .transport import ConnectorError


class JiraBase(Adapter):
    kind = "jira"
    api = ""

    def request_fields(self):
        mapping = {
            "title": "summary",
            "status": "status,resolutiondate",
            "assignee": "assignee",
            "due_date": "duedate",
            "priority": "priority",
            "dependencies": "issuelinks",
            "work_type": "issuetype",
            "labels": "labels",
        }
        fields = {"updated", "created", "project"}
        for key in self.fields:
            fields.update(mapping.get(key, "").split(","))
        for key in ("sprints", "outcomes"):
            configured = self.options.get("field_map", {}).get(key)
            if key in self.fields and configured:
                if (
                    not str(configured).startswith("customfield_")
                    or not str(configured)[12:].isdigit()
                ):
                    raise ConnectorError(
                        "Jira custom field mappings require an exact customfield_N identifier."
                    )
                fields.add(configured)
        return ",".join(sorted(fields - {""}))

    def query(self, scope, since):
        query = f'project = "{scope}"'
        if since:
            # Only a parsed timestamp is interpolated; arbitrary JQL is not accepted.
            query += ' AND updated >= "' + self.query_minute(since) + '"'
        return query + " ORDER BY updated ASC, key ASC"

    def normalize(self, raw, scope):
        fields = raw.get("fields", {})
        if fields.get("project", {}).get("key", scope) != scope:
            raise ConnectorError("Jira returned an issue outside the configured project.")
        key = identifier(raw.get("key") or raw["id"])
        data = self.selected(
            {
                "status": fields.get("status", {}).get("name"),
                "due_date": fields.get("duedate"),
                "priority": (fields.get("priority") or {}).get("name"),
                "work_type": (fields.get("issuetype") or {}).get("name"),
                "labels": [text(v, 100) for v in fields.get("labels", [])[:100]],
            }
        )
        if "status" in self.fields:
            data["completed_at"] = instant(fields.get("resolutiondate"))
        if "assignee" in self.fields:
            data["assignee"] = account(fields.get("assignee"), "email" in self.fields)
        if "dependencies" in self.fields:
            data["dependencies"] = [
                {
                    "relationship": text(link.get("type", {}).get("name")),
                    "inward": text(link.get("inwardIssue", {}).get("key")),
                    "outward": text(link.get("outwardIssue", {}).get("key")),
                }
                for link in fields.get("issuelinks", [])[:500]
            ]
        for key_name in ("sprints", "outcomes"):
            field = self.options.get("field_map", {}).get(key_name)
            if key_name in self.fields:
                value = fields.get(field) if field else None
                values = (
                    value if isinstance(value, list) else ([value] if value is not None else [])
                )
                if key_name == "sprints":
                    data[key_name] = [
                        {k: v.get(k) for k in ("id", "name", "state", "startDate", "endDate")}
                        if isinstance(v, dict)
                        else {"source_label": text(v)}
                        for v in values[:100]
                    ]
                else:
                    data[key_name] = [
                        text(v, 1000) for v in values[:100] if isinstance(v, (str, int, float))
                    ]
                if not field:
                    data[key_name + "_coverage"] = "not_configured"
        if "changelog" in self.fields:
            histories, complete = self.changelog(raw)
            changes = []
            permitted_changes = {
                "status",
                "assignee",
                "duedate",
                "priority",
                "Sprint",
                "resolution",
            }
            # Provider pagination may replay boundary events. Stable event IDs prevent duplicate durations.
            unique = {
                str(event.get("id")): event for event in histories if event.get("id") is not None
            }
            complete = complete and len(unique) == len(histories)
            for event in unique.values():
                items = []
                for item in event.get("items", []):
                    field = item.get("field")
                    if field not in permitted_changes:
                        continue
                    # Changelog is explicitly selected, but never import free-text body edits.
                    items.append(
                        {
                            "field": field,
                            "from": text(item.get("from")),
                            "to": text(item.get("to")),
                            "from_label": text(item.get("fromString"))
                            if field != "assignee"
                            else "",
                            "to_label": text(item.get("toString")) if field != "assignee" else "",
                        }
                    )
                if items:
                    changes.append(
                        {
                            "id": text(event.get("id")),
                            "at": instant(event.get("created")),
                            "author": account(event.get("author")),
                            "items": items,
                        }
                    )
            data["changelog"] = changes
            data["changelog_complete"] = complete
            data["transitions"] = [
                {
                    "at": event["at"],
                    "from": item["from_label"],
                    "to": item["to_label"],
                    "event_id": event["id"],
                }
                for event in changes
                for item in event["items"]
                if item["field"] == "status"
            ]
            data["assignments"] = [
                {
                    "at": event["at"],
                    "from_account_id": item["from"],
                    "to_account_id": item["to"],
                    "event_id": event["id"],
                }
                for event in changes
                for item in event["items"]
                if item["field"] == "assignee"
            ]
        return self.record(
            raw.get("id") or key,
            scope,
            raw,
            title=fields.get("summary"),
            url=self.base_url + "/browse/" + key,
            created=fields.get("created"),
            updated=fields.get("updated"),
            user=fields.get("assignee"),
            data=data,
            kind="work_item",
        )


class JiraCloudAdapter(JiraBase):
    deployment = "cloud"
    api = "rest/api/3"

    def fetch_page(self, scope, token, since):
        params = {
            "jql": self.query(scope, since),
            "maxResults": self.page_size,
            "fields": self.request_fields(),
        }
        if token:
            params["nextPageToken"] = token
        result = self.transport.get(self.api + "/search/jql", params)
        if "issues" not in result:
            raise ConnectorError("Jira Cloud enhanced search did not return an issues collection.")
        next_token = result.get("nextPageToken")
        if result.get("isLast") is False and not next_token:
            raise ConnectorError("Jira Cloud omitted a required nextPageToken.")
        return [self.normalize(raw, scope) for raw in result["issues"]], next_token

    def changelog(self, raw):
        values, start = [], 0
        for _ in range(self.max_nested_pages):
            result = self.transport.get(
                self.api + "/issue/" + identifier(raw["id"]) + "/changelog",
                {"startAt": start, "maxResults": self.page_size},
            )
            if "values" not in result or (result.get("isLast") is False and "total" not in result):
                raise ConnectorError("Jira Cloud returned an incomplete changelog page shape.")
            page = result.get("values", [])
            values.extend(page)
            if result.get("isLast", False) or start + len(page) >= result.get(
                "total", start + len(page)
            ):
                return values, True
            if not page:
                raise ConnectorError("Jira changelog pagination made no progress.")
            start += len(page)
        raise ConnectorError(
            "Jira changelog exceeded page budget; reduce source scope or raise bounded page budget."
        )


class JiraDataCenterAdapter(JiraBase):
    deployment = "data_center"
    api = "rest/api/2"

    def fetch_page(self, scope, token, since):
        start = int(token or 0)
        params = {
            "jql": self.query(scope, since),
            "startAt": start,
            "maxResults": self.page_size,
            "fields": self.request_fields(),
        }
        if "changelog" in self.fields:
            params["expand"] = "changelog"
        result = self.transport.get(self.api + "/search", params)
        if "issues" not in result or "total" not in result:
            raise ConnectorError("Jira Data Center search returned an unexpected page shape.")
        values = result["issues"]
        next_start = start + len(values)
        if not values and next_start < result["total"]:
            raise ConnectorError("Jira Data Center pagination made no progress.")
        return [self.normalize(raw, scope) for raw in values], next_start if next_start < result[
            "total"
        ] else None

    def changelog(self, raw):
        change = raw.get("changelog", {})
        histories = change.get("histories", [])
        # Data Center's search expansion can be truncated. Never infer complete flow history.
        complete = (
            "total" in change
            and change.get("startAt", 0) == 0
            and len(histories) >= change["total"]
        )
        return histories, complete
