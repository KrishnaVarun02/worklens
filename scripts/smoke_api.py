#!/usr/bin/env python3
"""Exercise an already seeded SYNTHETIC WorkLens instance through HTTP, including CSRF."""

import argparse
import os
from pathlib import Path
import time
from urllib.parse import urlsplit
from uuid import uuid4
import requests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--insecure-local",
        action="store_true",
        help="Only allow a self-signed loopback certificate.",
    )
    parser.add_argument("--report-dir")
    parser.add_argument(
        "--queued", action="store_true", help="Also require a running report worker."
    )
    args = parser.parse_args()
    if args.insecure_local and urlsplit(args.base_url).hostname not in (
        "localhost",
        "127.0.0.1",
        "::1",
    ):
        parser.error("--insecure-local is restricted to loopback")
    if args.insecure_local:
        import urllib3

        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    password = os.environ.get("WORKLENS_DEMO_PASSWORD", "WorkLens-demo-2026!")

    def session(username):
        client = requests.Session()
        client.trust_env = False
        client.verify = not args.insecure_local
        response = client.get(args.base_url + "/api/auth/session/", timeout=15)
        response.raise_for_status()
        client.headers.update(
            {"X-CSRFToken": response.json()["csrfToken"], "Referer": args.base_url + "/"}
        )
        response = client.post(
            args.base_url + "/api/auth/login/",
            json={"username": username, "password": password},
            timeout=15,
        )
        response.raise_for_status()
        client.headers["X-CSRFToken"] = response.json()["csrfToken"]
        return client

    def api(client, method, path, data=None, expected=(200, 201, 202, 204)):
        response = client.request(method, args.base_url + "/api/" + path, json=data, timeout=30)
        assert response.status_code in expected, f"{method} {path}: HTTP {response.status_code}"
        return response

    admin = session("admin")
    directory = api(admin, "GET", "employees/").json()
    alex = next(row for row in directory if row["stable_id"] == "EMP-002")
    jordan = next(row for row in directory if row["stable_id"] == "EMP-004")
    assert alex["email"] == "alex@example.test" and jordan["email"] == "jordan@example.test", (
        "Synthetic dataset required"
    )
    source = api(
        admin,
        "POST",
        "sources/",
        {
            "name": "HTTP smoke " + uuid4().hex[:8],
            "kind": "fixture",
            "deployment": "fixture",
            "scopes": ["DEMO"],
            "fields": [],
            "config": {},
        },
    ).json()
    sid = source["id"]
    assert api(admin, "POST", f"sources/{sid}/test/", {}).json()["ok"]
    run = api(admin, "POST", f"sources/{sid}/sync/", {}).json()
    assert run["status"] == "succeeded", run["status"]
    mapping = next(
        row
        for row in api(admin, "GET", "identities/").json()
        if row["source"] == sid and row["account_id"] == "demo-alex"
    )
    assert mapping["status"] in ("unresolved", "ambiguous")
    api(admin, "POST", f"identities/{mapping['id']}/resolve/", {"employee": alex["id"]})
    records = [row for row in api(admin, "GET", "source-records/").json() if row["source"] == sid]
    api(admin, "POST", f"sources/{sid}/sync/", {})
    repeated = [row for row in api(admin, "GET", "source-records/").json() if row["source"] == sid]
    assert len(records) == len(repeated) and len(records) > 0
    metrics = api(admin, "POST", f"employees/{alex['id']}/calculate/", {}).json()
    assert len(metrics) == 7 and all(row["details"]["formula"] for row in metrics)
    employee = session("alex")
    evidence = api(employee, "GET", "contributions/").json()
    assert evidence and all(row["employee"] == alex["id"] for row in evidence)
    correction = api(
        employee,
        "POST",
        "corrections/",
        {
            "employee": alex["id"],
            "contribution": evidence[0]["id"],
            "reason": "Synthetic HTTP acceptance test",
            "requested_context": "Pairing context recorded through the employee workflow.",
        },
    ).json()
    manager = session("manager")
    reviewed = api(
        manager,
        "POST",
        f"corrections/{correction['id']}/review/",
        {
            "decision": "approved",
            "review_note": "Verified against synthetic shared delivery evidence.",
        },
    ).json()
    assert reviewed["status"] == "approved"
    for kind, mime in [("csv", "text/csv"), ("pdf", "application/pdf")]:
        report = api(employee, "GET", f"reports/export/?employee={alex['id']}&format={kind}")
        assert mime in report.headers["Content-Type"] and len(report.content) > 100
        if args.report_dir:
            destination = Path(args.report_dir)
            destination.mkdir(parents=True, exist_ok=True)
            (destination / ("synthetic-report." + kind)).write_bytes(report.content)
    if args.queued:
        job = api(
            employee, "POST", "report-jobs/", {"employee": alex["id"], "format": "pdf"}
        ).json()
        deadline = time.monotonic() + 30
        while job["status"] in ("queued", "running") and time.monotonic() < deadline:
            time.sleep(1)
            job = api(employee, "GET", f"report-jobs/{job['id']}/").json()
        assert job["status"] == "succeeded", f"Queued report: {job['status']}"
        report = api(employee, "GET", f"report-jobs/{job['id']}/download/")
        assert report.content.startswith(b"%PDF-")
    api(employee, "GET", f"reports/export/?employee={jordan['id']}&format=csv", expected=(403,))
    api(
        employee,
        "POST",
        "sources/",
        {
            "name": "Forbidden fixture",
            "kind": "fixture",
            "deployment": "fixture",
            "scopes": ["DEMO"],
        },
        expected=(403,),
    )
    api(admin, "PATCH", f"sources/{sid}/", {"enabled": False})
    api(admin, "POST", f"sources/{sid}/purge/", {})
    assert not [row for row in api(admin, "GET", "source-records/").json() if row["source"] == sid]
    api(admin, "DELETE", f"sources/{sid}/")
    api(admin, "POST", f"employees/{alex['id']}/calculate/", {})
    print(
        "PASS: session/CSRF, fixture configuration, sync, identity resolution, idempotence, seven metrics, "
        "employee correction, manager review, CSV/PDF exports, unauthorized access denial, source purge."
    )
    if args.queued:
        print("PASS: queued PDF processed by worker and downloaded by its authorized requester.")


if __name__ == "__main__":
    main()
