"""Repository-scoped pull request observations; no commits/LOC productivity scores."""

from .base import Adapter, account, identifier, instant, text
from .transport import ConnectorError


class BitbucketBase(Adapter):
    kind = "bitbucket"

    def repo(self, scope):
        if len(scope.split("/")) != 2:
            raise ConnectorError(
                "Bitbucket scope must be workspace/repository or PROJECT/repository."
            )
        return scope.split("/")

    def approvals(self, participants):
        return [
            {
                **account(p.get("user"), "email" in self.fields),
                "approved": bool(p.get("approved")),
                "status": text(p.get("state") or p.get("status")),
                "at": instant(p.get("participated_on")),
            }
            for p in participants[:500]
        ]


class BitbucketCloudAdapter(BitbucketBase):
    deployment = "cloud"

    def path(self, scope):
        workspace, repo = self.repo(scope)
        return f"2.0/repositories/{workspace}/{repo}/pullrequests"

    def fetch_page(self, scope, token, since):
        path = self.path(scope)
        params = {
            "state": ["OPEN", "MERGED", "DECLINED", "SUPERSEDED"],
            "sort": "updated_on",
            "pagelen": self.page_size,
        }
        if token:
            params["page"] = token
        if since:
            params["q"] = f"updated_on >= {instant(since)}"
        result = self.transport.get(path, params)
        if "values" not in result:
            raise ConnectorError("Bitbucket Cloud did not return a values collection.")
        return [self.normalize(raw, scope) for raw in result["values"]], self.next_cursor(
            result.get("next"), path, "page"
        )

    def normalize(self, raw, scope):
        pr_id = identifier(raw["id"])
        data = self.selected(
            {
                "status": raw.get("state"),
                "reviewers": [
                    account(v, "email" in self.fields) for v in raw.get("reviewers", [])[:500]
                ],
                "approvals": self.approvals(raw.get("participants", [])),
                "merge": {
                    "commit": text((raw.get("merge_commit") or {}).get("hash")),
                    "merged": raw.get("state") == "MERGED",
                    "closed_by": account(raw.get("closed_by")),
                },
            }
        )
        if "builds" in self.fields:
            path, token, builds = self.path(scope) + "/" + pr_id + "/statuses", None, []
            for _ in range(self.max_nested_pages):
                result = self.transport.get(
                    path, {"pagelen": self.page_size, **({"page": token} if token else {})}
                )
                if "values" not in result:
                    raise ConnectorError("Bitbucket did not return a build-status collection.")
                builds.extend(
                    {
                        "key": text(v.get("key")),
                        "state": text(v.get("state")),
                        "updated_at": instant(v.get("updated_on")),
                        "url": self.evidence_url(v.get("url")),
                    }
                    for v in result.get("values", [])
                )
                token = self.next_cursor(result.get("next"), path, "page")
                if token is None:
                    break
            else:
                raise ConnectorError("Bitbucket build-status pagination exceeded its budget.")
            data["builds"] = builds
        return self.record(
            scope + ":" + pr_id,
            scope,
            raw,
            title=raw.get("title"),
            url=raw.get("links", {}).get("html", {}).get("href"),
            created=raw.get("created_on"),
            updated=raw.get("updated_on"),
            user=raw.get("author"),
            data=data,
            kind="pull_request",
        )


class BitbucketDataCenterAdapter(BitbucketBase):
    deployment = "data_center"

    def path(self, scope):
        project, repo = self.repo(scope)
        return f"rest/api/1.0/projects/{project}/repos/{repo}/pull-requests"

    def fetch_page(self, scope, token, since):
        path = self.path(scope)
        result = self.transport.get(
            path,
            {"state": "ALL", "order": "NEWEST", "start": int(token or 0), "limit": self.page_size},
        )
        if "values" not in result or "isLastPage" not in result:
            raise ConnectorError("Bitbucket Data Center returned an unexpected page shape.")
        next_start = None if result["isLastPage"] else result.get("nextPageStart")
        if not result["isLastPage"] and next_start is None:
            raise ConnectorError("Bitbucket Data Center omitted nextPageStart.")
        return [self.normalize(raw, scope) for raw in result["values"]], next_start

    def normalize(self, raw, scope):
        pr_id = identifier(raw["id"])
        data = self.selected(
            {
                "status": raw.get("state"),
                "reviewers": [
                    account(v.get("user"), "email" in self.fields)
                    for v in raw.get("reviewers", [])[:500]
                ],
                "approvals": self.approvals(raw.get("reviewers", [])),
                "merge": {
                    "merged": raw.get("state") == "MERGED",
                    "closed_at": instant(raw.get("closedDate")),
                },
            }
        )
        if "builds" in self.fields:
            commit = raw.get("fromRef", {}).get("latestCommit")
            if commit:
                # Official aggregate endpoint: these are commit-level observations, never individual quality attribution.
                stats = self.transport.get(
                    "rest/build-status/1.0/commits/stats/" + identifier(commit)
                )
                data["builds"] = {
                    k: stats.get(k)
                    for k in ("successful", "failed", "inProgress", "cancelled", "unknown")
                }
                data["builds"]["commit"] = text(commit)
            else:
                data["builds"] = None
        links = raw.get("links", {}).get("self", [])
        return self.record(
            scope + ":" + pr_id,
            scope,
            raw,
            title=raw.get("title"),
            url=links[0].get("href", "") if links else "",
            created=raw.get("createdDate"),
            updated=raw.get("updatedDate"),
            user=raw.get("author", {}).get("user"),
            data=data,
            kind="pull_request",
        )
