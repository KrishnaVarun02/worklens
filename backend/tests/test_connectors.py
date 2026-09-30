"""Protocol fixtures and failure/security cases. No real account or network is used."""

import copy
import json
import os
import socket
import unittest
from unittest.mock import MagicMock, patch

from connectors import ADAPTERS, AccessRevoked, ConnectorError, RecordUnavailable, get_adapter
from connectors.base import FIELDS
from connectors.transport import HttpTransport


def config(kind="jira", deployment="cloud", fields=None, scopes=None, **options):
    base = "https://source.example.test"
    return {
        "kind": kind,
        "deployment": deployment,
        "base_url": base,
        "scopes": scopes
        or (
            ["DEMO/repository"]
            if kind == "bitbucket"
            else ["17"]
            if kind == "confluence" and deployment == "cloud"
            else ["DEMO"]
        ),
        "fields": list(
            fields if fields is not None else ["title", "status", "authorship", "assignee", "email"]
        ),
        "config": {"allowed_endpoints": [base], "min_interval": 0, **options},
    }


class FakeTransport:
    def __init__(self, pages, base="https://source.example.test"):
        self.pages = list(pages)
        self.calls = []
        self.base = base

    def get(self, path, params=None):
        self.calls.append((path, params))
        if not self.pages:
            raise AssertionError("Unexpected extra request: " + path)
        value = self.pages.pop(0)
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)

    def url(self, path):
        return path if "://" in path else self.base + "/" + path.lstrip("/")

    def validate_url(self, url):
        if not url.startswith(self.base + "/"):
            raise ConnectorError("Outside endpoint")


def jira_issue(id="1001", deployment="cloud"):
    user = (
        {"accountId": "acct-alex", "emailAddress": "alex@example.test"}
        if deployment == "cloud"
        else {"key": "user-alex", "emailAddress": "alex@example.test"}
    )
    return {
        "id": id,
        "key": "DEMO-1",
        "fields": {
            "project": {"key": "DEMO"},
            "summary": "Ship accessible recovery",
            "updated": "2026-09-01T13:00:00Z",
            "created": "2026-08-01T13:00:00Z",
            "assignee": user,
            "status": {"name": "Done"},
            "resolutiondate": "2026-09-01T13:00:00Z",
            "duedate": "2026-09-02",
            "issuetype": {"name": "Story"},
            "description": "PRIVATE BODY MUST NOT PERSIST",
            "customfield_10020": [
                {"id": 5, "name": "September", "state": "active", "goal": "UNSELECTED"}
            ],
            "issuelinks": [
                {
                    "type": {"name": "Blocks"},
                    "inwardIssue": {"key": "DEMO-2", "fields": {"summary": "UNSELECTED"}},
                }
            ],
        },
    }


def cloud_pr(id=42):
    return {
        "id": id,
        "title": "Accessible recovery",
        "state": "MERGED",
        "created_on": "2026-08-01T09:00:00Z",
        "updated_on": "2026-09-01T09:00:00Z",
        "author": {"uuid": "{alex}", "email": "alex@example.test"},
        "reviewers": [{"uuid": "{sam}", "display_name": "Sam"}],
        "participants": [
            {
                "user": {"uuid": "{sam}"},
                "approved": True,
                "state": "approved",
                "participated_on": "2026-08-31T09:00:00Z",
            }
        ],
        "links": {
            "html": {"href": "https://bitbucket.example.test/DEMO/repository/pull-requests/42"}
        },
        "merge_commit": {"hash": "abc123"},
        "description": "PRIVATE BODY",
    }


def dc_pr(id=42):
    return {
        "id": id,
        "title": "Retry policy",
        "state": "MERGED",
        "createdDate": 1785574800000,
        "updatedDate": 1788253200000,
        "closedDate": 1788253200000,
        "author": {"user": {"id": 11, "emailAddress": "alex@example.test"}},
        "reviewers": [{"user": {"id": 12}, "approved": True, "status": "APPROVED"}],
        "fromRef": {"latestCommit": "abc123"},
        "links": {"self": [{"href": "https://source.example.test/pr/42"}]},
    }


def cloud_page(id="21"):
    return {
        "id": id,
        "spaceId": "17",
        "status": "current",
        "title": "Recovery guide",
        "authorId": "acct-alex",
        "ownerId": "acct-sam",
        "createdAt": "2026-08-01T09:00:00Z",
        "version": {"number": 2, "createdAt": "2026-09-01T09:00:00Z", "authorId": "acct-sam"},
        "_links": {"webui": "/spaces/DEMO/pages/21"},
        "body": {"storage": {"value": "PRIVATE BODY"}},
    }


def dc_page(id="21"):
    return {
        "id": id,
        "space": {"key": "DEMO"},
        "status": "current",
        "title": "Recovery guide",
        "history": {"createdDate": "2026-08-01T09:00:00Z", "createdBy": {"userKey": "alex"}},
        "version": {"number": 2, "when": "2026-09-01T09:00:00Z", "by": {"userKey": "sam"}},
        "_links": {"webui": "/display/DEMO/Recovery+guide"},
        "body": {"storage": {"value": "PRIVATE BODY"}},
    }


class AdapterProtocolTests(unittest.TestCase):
    def test_all_six_live_adapters_explicitly_registered(self):
        self.assertEqual(len([k for k in ADAPTERS if k[0] != "fixture"]), 6)
        with self.assertRaises(ConnectorError):
            get_adapter(config("mailbox"))

    def test_jira_cloud_pagination_resume_and_changelog(self):
        fields = ["title", "assignee", "email", "changelog", "sprints", "dependencies", "due_date"]
        history = {
            "id": "event-1",
            "created": "2026-09-01T12:00:00Z",
            "author": {"accountId": "acct-sam"},
            "items": [
                {
                    "field": "status",
                    "from": "1",
                    "to": "3",
                    "fromString": "Doing",
                    "toString": "Done",
                },
                {"field": "description", "fromString": "PRIVATE", "toString": "PRIVATE"},
            ],
        }
        transport = FakeTransport(
            [
                {"issues": [jira_issue()], "nextPageToken": "p2", "isLast": False},
                {"values": [history], "total": 2, "isLast": False},
                {"values": [{**history, "id": "event-2"}], "total": 2, "isLast": True},
            ]
        )
        cfg = config(fields=fields, field_map={"sprints": "customfield_10020"})
        adapter = get_adapter(cfg, transport=transport)
        first = next(adapter.iter_pages())
        self.assertFalse(first["complete"])
        self.assertEqual(first["cursor"]["page"], "p2")
        row = first["records"][0]
        self.assertEqual(row["account_id"], "acct-alex")
        self.assertEqual(len(row["data"]["changelog"]), 2)
        self.assertTrue(row["data"]["changelog_complete"])
        self.assertEqual(row["data"]["transitions"][0]["to"], "Done")
        self.assertNotIn("PRIVATE", json.dumps(row))
        self.assertNotIn("goal", json.dumps(row))
        self.assertEqual(transport.calls[0][0], "rest/api/3/search/jql")
        self.assertEqual(transport.calls[2][1]["startAt"], 1)
        resumed_transport = FakeTransport([{"issues": [], "isLast": True}])
        resumed = list(get_adapter(cfg, transport=resumed_transport).iter_pages(first["cursor"]))
        self.assertEqual(resumed_transport.calls[0][1]["nextPageToken"], "p2")
        self.assertTrue(resumed[-1]["complete"])

    def test_jira_dc_uses_offset_and_labels_truncated_history(self):
        raw = jira_issue(deployment="data_center")
        raw["changelog"] = {"total": 20, "histories": [], "startAt": 10}
        transport = FakeTransport([{"issues": [raw], "total": 2}, {"issues": [raw], "total": 2}])
        pages = list(
            get_adapter(
                config(deployment="data_center", fields=["assignee", "changelog"]),
                transport=transport,
            ).iter_pages()
        )
        self.assertEqual(transport.calls[0][0], "rest/api/2/search")
        self.assertEqual(transport.calls[1][1]["startAt"], 1)
        self.assertEqual(pages[0]["records"][0]["account_id"], "user-alex")
        self.assertFalse(pages[0]["records"][0]["data"]["changelog_complete"])

    def test_duplicate_changelog_events_are_not_counted_twice(self):
        raw = jira_issue(deployment="data_center")
        event = {
            "id": "100",
            "created": "2026-09-01T12:00:00Z",
            "items": [
                {
                    "field": "status",
                    "from": "1",
                    "to": "2",
                    "fromString": "Doing",
                    "toString": "Done",
                }
            ],
        }
        raw["changelog"] = {"histories": [event, event], "total": 2}
        adapter = get_adapter(
            config(deployment="data_center", fields=["changelog"]),
            transport=FakeTransport([{"issues": [raw], "total": 1}]),
        )
        row = next(adapter.iter_pages())["records"][0]
        self.assertEqual(len(row["data"]["transitions"]), 1)

    def test_bitbucket_cloud_pagination_all_states_and_builds(self):
        path = "https://source.example.test/2.0/repositories/DEMO/repository/pullrequests"
        transport = FakeTransport(
            [
                {"values": [cloud_pr()], "next": path + "?page=2"},
                {
                    "values": [
                        {"key": "unit", "state": "SUCCESSFUL", "updated_on": "2026-09-01T09:00:00Z"}
                    ]
                },
                {"values": []},
            ]
        )
        cfg = config(
            "bitbucket", fields=["title", "authorship", "reviewers", "approvals", "merge", "builds"]
        )
        pages = list(get_adapter(cfg, transport=transport).iter_pages())
        self.assertEqual(
            transport.calls[0][1]["state"], ["OPEN", "MERGED", "DECLINED", "SUPERSEDED"]
        )
        self.assertEqual(transport.calls[2][1]["page"], "2")
        row = pages[0]["records"][0]
        self.assertEqual(row["account_id"], "{alex}")
        self.assertEqual(row["email"], "")
        self.assertTrue(row["data"]["approvals"][0]["approved"])
        self.assertEqual(row["data"]["builds"][0]["state"], "SUCCESSFUL")
        self.assertNotIn("PRIVATE", json.dumps(row))

    def test_bitbucket_dc_uses_next_page_start_not_page_size(self):
        transport = FakeTransport(
            [
                {"values": [dc_pr()], "isLastPage": False, "nextPageStart": 7},
                {"successful": 5, "failed": 1},
                {"values": [], "isLastPage": True},
            ]
        )
        pages = list(
            get_adapter(
                config("bitbucket", "data_center", fields=["authorship", "approvals", "builds"]),
                transport=transport,
            ).iter_pages()
        )
        self.assertEqual(transport.calls[2][1]["start"], 7)
        self.assertEqual(transport.calls[1][0], "rest/build-status/1.0/commits/stats/abc123")
        self.assertEqual(pages[0]["records"][0]["account_id"], "11")
        self.assertEqual(pages[0]["records"][0]["data"]["builds"]["failed"], 1)

    def test_confluence_cloud_page_cursor_revisions_and_explicit_reviews(self):
        transport = FakeTransport(
            [
                {
                    "results": [cloud_page()],
                    "_links": {"next": "/api/v2/pages?cursor=next&space-id=17"},
                },
                {
                    "results": [
                        {"number": 1, "authorId": "acct-alex", "createdAt": "2026-08-01T09:00:00Z"}
                    ],
                    "_links": {"next": "/api/v2/pages/21/versions?cursor=v2"},
                },
                {
                    "results": [
                        {"number": 2, "authorId": "acct-sam", "createdAt": "2026-09-01T09:00:00Z"}
                    ]
                },
                {
                    "results": [
                        {
                            "key": "worklens.reviews",
                            "value": {
                                "reviews": [
                                    {
                                        "reviewer_account_id": "acct-sam",
                                        "verdict": "accepted",
                                        "reviewed_at": "2026-09-01T12:00:00Z",
                                        "notes": "PRIVATE",
                                    }
                                ]
                            },
                        }
                    ]
                },
                {"results": []},
            ]
        )
        cfg = config(
            "confluence",
            fields=["title", "authorship", "ownership", "revisions", "reviews"],
            review_property_key="worklens.reviews",
        )
        pages = list(get_adapter(cfg, transport=transport).iter_pages())
        self.assertEqual(transport.calls[4][1]["cursor"], "next")
        row = pages[0]["records"][0]
        self.assertEqual(row["data"]["ownership"]["account_id"], "acct-sam")
        self.assertTrue(row["data"]["revisions_complete"])
        self.assertEqual(len(row["data"]["revisions"]), 2)
        self.assertEqual(row["data"]["reviews"][0]["verdict"], "accepted")
        self.assertNotIn("PRIVATE", json.dumps(row))

    def test_confluence_dc_cql_pagination_and_revision_coverage(self):
        transport = FakeTransport(
            [
                {"results": [dc_page()], "_links": {"next": "/rest/api/content/search?start=2"}},
                RecordUnavailable("historical version was deleted or permission restricted"),
                {"results": []},
            ]
        )
        cfg = config(
            "confluence",
            "data_center",
            fields=["authorship", "revisions", "ownership"],
            since="2026-08-01T00:00:00Z",
        )
        pages = list(get_adapter(cfg, transport=transport).iter_pages())
        self.assertIn("lastmodified >=", transport.calls[0][1]["cql"])
        self.assertEqual(transport.calls[2][1]["start"], 2)
        row = pages[0]["records"][0]
        self.assertFalse(row["data"]["revisions_complete"])
        self.assertIsNone(row["data"]["ownership"]["account_id"])
        self.assertEqual(row["account_id"], "alex")

    def test_confluence_dc_reads_official_historical_version_metadata(self):
        transport = FakeTransport(
            [
                {"results": [dc_page()]},
                {
                    "id": "21",
                    "version": {
                        "number": 1,
                        "when": "2026-08-01T09:00:00Z",
                        "by": {"userKey": "alex"},
                    },
                    "body": {"storage": {"value": "PRIVATE"}},
                },
            ]
        )
        cfg = config("confluence", "data_center", fields=["revisions"])
        row = next(get_adapter(cfg, transport=transport).iter_pages())["records"][0]
        self.assertEqual(
            transport.calls[1],
            ("rest/api/content/21", {"status": "historical", "version": 1, "expand": "version"}),
        )
        self.assertTrue(row["data"]["revisions_complete"])
        self.assertEqual([r["number"] for r in row["data"]["revisions"]], [1, 2])
        self.assertNotIn("PRIVATE", json.dumps(row))

    def test_every_adapter_minimizes_unselected_fields(self):
        inputs = [
            ("jira", "cloud", {"issues": [jira_issue()], "isLast": True}),
            ("jira", "data_center", {"issues": [jira_issue()], "total": 1}),
            ("bitbucket", "cloud", {"values": [cloud_pr()]}),
            ("bitbucket", "data_center", {"values": [dc_pr()], "isLastPage": True}),
            ("confluence", "cloud", {"results": [cloud_page()]}),
            ("confluence", "data_center", {"results": [dc_page()]}),
        ]
        for kind, deployment, page in inputs:
            with self.subTest(kind=kind, deployment=deployment):
                row = next(
                    get_adapter(
                        config(kind, deployment, fields=[]), transport=FakeTransport([page])
                    ).iter_pages()
                )["records"][0]
                self.assertEqual(row["data"], {})
                self.assertEqual(row["title"], "")
                self.assertEqual(row["email"], "")
                self.assertEqual(row["account_id"], "")

    def test_scope_allowlist_blocks_source_scope_mismatch(self):
        raw = jira_issue()
        raw["fields"]["project"]["key"] = "SECRET"
        with self.assertRaises(ConnectorError):
            list(get_adapter(config(), transport=FakeTransport([{"issues": [raw]}])).iter_pages())

    def test_pagination_cannot_switch_repo_or_host(self):
        for url in (
            "https://evil.example/2.0/repositories/DEMO/repository/pullrequests?page=2",
            "https://source.example.test/2.0/repositories/SECRET/hidden/pullrequests?page=2",
        ):
            with self.subTest(url=url), self.assertRaises(ConnectorError):
                list(
                    get_adapter(
                        config("bitbucket"), transport=FakeTransport([{"values": [], "next": url}])
                    ).iter_pages()
                )

    def test_scope_and_field_changes_invalidate_cursor(self):
        cfg = config()
        page = next(
            get_adapter(
                cfg, transport=FakeTransport([{"issues": [], "nextPageToken": "p2"}])
            ).iter_pages()
        )
        cfg["scopes"] = ["OTHER"]
        with self.assertRaises(ConnectorError):
            list(get_adapter(cfg, transport=FakeTransport([])).iter_pages(page["cursor"]))

    def test_repeated_cursor_is_detected(self):
        pages = [{"issues": [], "nextPageToken": "repeated"}] * 3
        with self.assertRaisesRegex(ConnectorError, "repeated"):
            list(get_adapter(config(), transport=FakeTransport(pages)).iter_pages())

    def test_no_progress_page_is_not_silently_complete(self):
        with self.assertRaisesRegex(ConnectorError, "no progress"):
            list(
                get_adapter(
                    config(deployment="data_center"),
                    transport=FakeTransport([{"issues": [], "total": 7}]),
                ).iter_pages()
            )

    def test_incremental_filter_preserves_unknown_dates_and_replays_overlap(self):
        older, current, unknown = cloud_page("1"), cloud_page("2"), cloud_page("3")
        older["version"]["createdAt"] = "2026-01-01T00:00:00Z"
        unknown["createdAt"] = None
        unknown["version"]["createdAt"] = None
        cfg = config("confluence", since="2026-09-01T00:00:00Z")
        page = next(
            get_adapter(
                cfg, transport=FakeTransport([{"results": [older, current, unknown]}])
            ).iter_pages()
        )
        self.assertEqual([r["external_id"] for r in page["records"]], ["2", "3"])

    def test_incremental_jql_uses_source_timezone(self):
        cfg = config(source_timezone="Asia/Kolkata", since="2026-09-01T00:00:00Z")
        fake = FakeTransport([{"issues": [], "isLast": True}])
        list(get_adapter(cfg, transport=fake).iter_pages())
        self.assertIn('updated >= "2026-09-01 05:25"', fake.calls[0][1]["jql"])

    def test_fixture_pages_resume_and_duplicate_events_use_stable_ids(self):
        cfg = {"kind": "fixture", "deployment": "fixture", "config": {"page_size": 2}}
        adapter = get_adapter(cfg)
        first = next(adapter.iter_pages())
        remaining = list(get_adapter(cfg).iter_pages(first["cursor"]))
        all_rows = first["records"] + [r for p in remaining for r in p["records"]]
        self.assertEqual(len(all_rows), 5)
        self.assertEqual(len({r["external_id"] for r in all_rows}), 5)
        replay = next(get_adapter(cfg).iter_pages())["records"]
        self.assertEqual(first["records"], replay)
        self.assertIn("shared_with", all_rows[0]["data"])
        self.assertFalse(adapter.test_connection()["coverage"]["live_verification"])

    def test_fixture_tombstones_are_explicit(self):
        cfg = {"kind": "fixture", "deployment": "fixture", "config": {"fixture": "deleted"}}
        self.assertTrue(next(get_adapter(cfg).iter_pages())["records"][0]["deleted"])

    def test_fixture_cannot_read_arbitrary_files(self):
        cfg = {"kind": "fixture", "config": {"fixture": "../../secrets"}}
        with self.assertRaises(ConnectorError):
            next(get_adapter(cfg).iter_pages())

    def test_configuration_rejects_unbounded_scopes_fields_and_jql(self):
        for cfg in (
            config(scopes=['DEMO" OR project = SECRET']),
            config(fields=["description"]),
            config(scopes=["../private"]),
        ):
            with self.subTest(cfg=cfg), self.assertRaises(ConnectorError):
                get_adapter(cfg, transport=FakeTransport([]))

    def test_permission_diagnostic_checks_every_scope(self):
        cfg = config(scopes=["DEMO", "OTHER"])
        fake = FakeTransport([{"issues": []}, AccessRevoked("denied")])
        with self.assertRaises(AccessRevoked):
            get_adapter(cfg, transport=fake).test_connection()
        self.assertEqual(len(fake.calls), 2)

    def test_missing_optional_confluence_property_is_unknown(self):
        fake = FakeTransport([{"results": [dc_page()]}, RecordUnavailable("property not visible")])
        cfg = config(
            "confluence", "data_center", fields=["reviews"], review_property_key="worklens.reviews"
        )
        row = next(get_adapter(cfg, transport=fake).iter_pages())["records"][0]
        self.assertEqual(row["data"]["reviews_coverage"], "property_missing_or_unavailable")


@patch.dict(os.environ, {"WORKLENS_ALLOWED_ENDPOINTS": "https://source.example.test"}, clear=True)
class HttpTransportTests(unittest.TestCase):
    def transport(self, **options):
        return HttpTransport(config(**options), {"token": "SYNTHETIC_SECRET"})

    def test_endpoint_allowlist_required_and_deployment_boundary(self):
        cfg = config()
        cfg["config"]["allowed_endpoints"] = []
        with self.assertRaises(ConnectorError):
            HttpTransport(cfg)
        with patch.dict(
            os.environ, {"WORKLENS_ALLOWED_ENDPOINTS": "https://different.example.test"}
        ):
            with self.assertRaises(ConnectorError):
                self.transport()
        with patch.dict(os.environ, {"WORKLENS_ALLOWED_ENDPOINTS": ""}):
            with self.assertRaisesRegex(ConnectorError, "denied until"):
                self.transport()

    def test_urls_cannot_escape_host_context_or_https(self):
        transport = self.transport()
        urls = [
            "http://source.example.test/rest/api/3/search",
            "https://source.example.test.evil/rest/api/3/search",
            "https://user:secret@source.example.test/rest/api/3/search",
            "https://source.example.test/../secret",
            "https://source.example.test/%2e%2e/secret",
            "https://source.example.test/rest#token",
            "https://source.example.test:444/rest",
        ]
        for url in urls:
            with self.subTest(url=url), self.assertRaises(ConnectorError):
                transport.validate_url(url)

    def test_internal_context_is_respected(self):
        cfg = config()
        cfg["base_url"] += "/jira"
        cfg["config"]["allowed_endpoints"] = [cfg["base_url"]]
        with patch.dict(os.environ, {"WORKLENS_ALLOWED_ENDPOINTS": cfg["base_url"]}):
            transport = HttpTransport(cfg)
        transport.validate_url(cfg["base_url"] + "/rest/api/2/search")
        with self.assertRaises(ConnectorError):
            transport.validate_url("https://source.example.test/jira-admin")

    def test_dns_blocks_metadata_loopback_and_unapproved_private(self):
        for address in (
            "169.254.169.254",
            "127.0.0.1",
            "::1",
            "0.0.0.0",
            "10.0.0.1",
            "::ffff:127.0.0.1",
        ):
            with (
                self.subTest(address=address),
                patch(
                    "socket.getaddrinfo",
                    return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))],
                ),
            ):
                with self.assertRaises(ConnectorError):
                    self.transport()._resolve("source.example.test", 443)

    def test_approved_private_still_forbids_metadata(self):
        transport = self.transport(allow_private_hosts=True)
        with patch(
            "socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.20.30.40", 443))],
        ):
            self.assertEqual(transport._resolve("internal.example.test", 443), "10.20.30.40")
        with patch(
            "socket.getaddrinfo",
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443))],
        ):
            with self.assertRaises(ConnectorError):
                transport._resolve("internal.example.test", 443)

    def test_mixed_public_and_private_dns_is_rejected(self):
        addresses = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (v, 443)) for v in ("8.8.8.8", "127.0.0.1")
        ]
        with patch("socket.getaddrinfo", return_value=addresses), self.assertRaises(ConnectorError):
            self.transport()._resolve("source.example.test", 443)

    def test_retries_rate_limit_then_success_without_payload_logging(self):
        transport = self.transport(retries=2)
        with (
            patch.object(
                transport,
                "_perform",
                side_effect=[
                    (429, {"retry-after": "1"}, b"PRIVATE"),
                    (503, {}, b"PRIVATE"),
                    (200, {}, b'{"issues":[]}'),
                ],
            ) as perform,
            patch("time.sleep") as sleep,
        ):
            self.assertEqual(transport.get("rest/api/3/search/jql"), {"issues": []})
            self.assertEqual(perform.call_count, 3)
            self.assertEqual(sleep.call_args_list[0].args[0], 1)

    def test_retries_stop_and_redact_sensitive_bodies(self):
        transport = self.transport(retries=1)
        with (
            patch.object(transport, "_perform", return_value=(503, {}, b"PRIVATE SECRET")),
            patch("time.sleep"),
        ):
            with self.assertRaises(ConnectorError) as error:
                transport.get("rest/api/3/search")
            self.assertNotIn("PRIVATE", str(error.exception))
            self.assertNotIn("SYNTHETIC_SECRET", str(error.exception))

    def test_redirects_are_never_followed(self):
        transport = self.transport()
        with patch.object(
            transport, "_perform", return_value=(302, {"location": "https://evil.test"}, b"")
        ) as perform:
            with self.assertRaisesRegex(ConnectorError, "redirect"):
                transport.get("rest/api/3/search")
            self.assertEqual(perform.call_count, 1)

    def test_revocation_and_ambiguous_missing_are_distinct(self):
        transport = self.transport()
        for status, error in ((401, AccessRevoked), (403, AccessRevoked), (404, RecordUnavailable)):
            with (
                self.subTest(status=status),
                patch.object(transport, "_perform", return_value=(status, {}, b"PRIVATE")),
            ):
                with self.assertRaises(error):
                    transport.get("rest/api/3/search")

    def test_invalid_json_and_array_shapes_fail(self):
        transport = self.transport()
        for payload in (b"<html>login</html>", b"[]", b"null"):
            with (
                patch.object(transport, "_perform", return_value=(200, {}, payload)),
                self.assertRaises(ConnectorError),
            ):
                transport.get("rest/api/3/search")

    def test_read_only_direct_https_pins_checked_address(self):
        transport = self.transport()
        conn = MagicMock()
        response = conn.getresponse.return_value
        response.status = 200
        response.getheaders.return_value = [("Content-Type", "application/json")]
        response.read.return_value = b"{}"
        with (
            patch.object(transport, "_resolve", return_value="8.8.8.8"),
            patch("http.client.HTTPSConnection", return_value=conn),
            patch("socket.create_connection") as create,
        ):
            transport.get("rest/api/3/search")
            conn._create_connection(("unexpected-dns-name", 443), 10)
            self.assertEqual(create.call_args.args[0], ("8.8.8.8", 443))
            self.assertEqual(conn.request.call_args.args[0], "GET")
            self.assertTrue(conn.close.called)

    def test_payload_limit_and_encoding_are_bounded(self):
        transport = self.transport()
        conn = MagicMock()
        response = conn.getresponse.return_value
        response.status = 200
        response.getheaders.return_value = []
        response.read.return_value = b"a" * (transport.MAX_BYTES + 1)
        with (
            patch.object(transport, "_resolve", return_value="8.8.8.8"),
            patch("http.client.HTTPSConnection", return_value=conn),
        ):
            with self.assertRaisesRegex(ConnectorError, "2 MiB"):
                transport.get("rest/api/3/search")
            response.getheaders.return_value = [("Content-Encoding", "gzip")]
            with self.assertRaisesRegex(ConnectorError, "Compressed"):
                transport.get("rest/api/3/search")

    def test_proxy_is_explicit_server_configuration_only(self):
        transport = self.transport()
        conn = MagicMock()
        response = conn.getresponse.return_value
        response.status, response.read.return_value, response.getheaders.return_value = (
            200,
            b"{}",
            [],
        )
        with (
            patch.dict(
                os.environ,
                {
                    "WORKLENS_EGRESS_PROXY": "http://egress-proxy:3128",
                    "HTTPS_PROXY": "http://evil:9999",
                },
            ),
            patch.object(transport, "_resolve", return_value="8.8.8.8"),
            patch("http.client.HTTPSConnection", return_value=conn) as connection,
        ):
            transport.get("rest/api/3/search")
            self.assertEqual(connection.call_args.args, ("egress-proxy", 3128))
            conn.set_tunnel.assert_called_once_with("source.example.test", 443)

    def test_basic_auth_and_bearer_are_local_credentials_only(self):
        cfg = config()
        headers = HttpTransport(
            cfg, {"auth_type": "basic", "email": "service@example.test", "token": "synthetic"}
        )._headers()
        self.assertTrue(headers["Authorization"].startswith("Basic "))
        self.assertEqual(self.transport()._headers()["Authorization"], "Bearer SYNTHETIC_SECRET")


if __name__ == "__main__":
    unittest.main()
