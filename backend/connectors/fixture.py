"""Bundled synthetic records, without filesystem paths or network access from config."""

import copy
import json
from pathlib import Path

from .base import Adapter, FIELDS
from .transport import ConnectorError


class FixtureAdapter(Adapter):
    kind = "fixture"
    deployment = "fixture"

    def __init__(self, config, credentials=None, transport=None):
        config = copy.deepcopy(config)
        config["scopes"] = config.get("scopes") or ["DEMO"]
        config["fields"] = config.get("fields") or sorted(FIELDS)
        super().__init__(config, credentials, transport=object())

    def fetch_page(self, scope, token, since):
        fixture_name = self.options.get("fixture", "demo")
        if fixture_name not in ("demo", "deleted"):
            raise ConnectorError(
                "Fixture name must be demo or deleted; arbitrary files are not supported."
            )
        rows = json.loads(
            (Path(__file__).parent / "fixtures" / (fixture_name + ".json")).read_text()
        )
        rows = [r for r in rows if r["scope"] == scope]
        start = int(token or 0)
        values = rows[start : start + self.page_size]
        for record in values:
            record["data"] = {
                k: v
                for k, v in record.get("data", {}).items()
                if k in self.fields
                or k in ("completed_at", "started_at", "contribution_kind", "shared_with")
            }
            if "email" not in self.fields:
                record["email"] = ""

                def strip_email(value):
                    if isinstance(value, dict):
                        return {
                            key: strip_email(item)
                            for key, item in value.items()
                            if key not in ("email", "emailAddress")
                        }
                    if isinstance(value, list):
                        return [strip_email(item) for item in value]
                    return value

                record["data"] = strip_email(record["data"])
            if "title" not in self.fields:
                record["title"] = ""
            if not ({"assignee", "authorship"} & self.fields):
                record["account_id"] = ""
        next_start = start + len(values)
        return values, next_start if next_start < len(rows) else None

    def test_connection(self):
        rows = sum(len(self.fetch_page(scope, None, None)[0]) for scope in self.scopes)
        return {
            "ok": True,
            "diagnostics": [
                "Bundled synthetic fixture loaded. No network connection was attempted."
            ],
            "coverage": {
                "scopes": self.scopes,
                "fields": sorted(self.fields),
                "first_page_records": rows,
                "live_verification": False,
            },
        }
