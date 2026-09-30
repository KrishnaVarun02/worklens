# Connector administrator guide

WorkLens has separate Jira, Bitbucket, and Confluence Cloud/Data Center adapters. They have been tested against synthetic protocol fixtures, including pagination and failure responses. **No adapter has been verified against a live customer system.** The fixture source runs without credentials or a network connection.

## Configuration and credentials

Create a source as an integration administrator, select its exact scopes and fields, then use **Test connection** before synchronization. Create read-only credentials in the source system using a dedicated service account. WorkLens sends only GET requests, but cannot downgrade a token's source permissions: the source administrator must restrict that account and token. Do not paste production credentials into an assistant, issue, or repository. Configure them locally in the application; they are encrypted separately from source configuration.

```json
{
  "name": "Engineering Jira",
  "kind": "jira",
  "deployment": "cloud",
  "base_url": "https://company.atlassian.net",
  "scopes": ["ENG"],
  "fields": ["title", "status", "assignee", "due_date", "priority", "work_type", "changelog", "dependencies", "sprints"],
  "config": {
    "allowed_endpoints": ["https://company.atlassian.net"],
    "page_size": 50,
    "field_map": {"sprints": "customfield_10020"},
    "workflow": {"active": ["In Progress"], "blocked": ["Blocked"], "done": ["Done"]}
  }
}
```

The custom sprint field ID above is an example. Select the actual authorized field ID from your Jira installation. Explicit outcomes can similarly use `field_map.outcomes`, containing an approved structured custom field of outcome references. These are observations; verification of business impact remains a separate review.

For Jira and Confluence Data Center, set `config.source_timezone` to the source service account's IANA timezone (for example `Asia/Kolkata`), or configure that account to UTC, the default assumed by WorkLens. JQL/CQL date literals are converted into that timezone before incremental searches.

The factory accepts a separate credential dictionary, or a `credentials` key inside its configuration:

```python
get_adapter(source_config, secret={"auth_type": "basic", "email": "service@company.example", "token": "configured-locally"})
get_adapter(source_config, secret={"auth_type": "bearer", "token": "configured-locally"})
```

`basic` uses email or username plus token. `bearer` uses a pre-provisioned access token/PAT. Interactive OAuth authorization and token refresh are **not implemented**. Use a supported authentication method for the selected product and token type. Cloud API tokens and OAuth tokens have different scopes and endpoint requirements; check the [Jira authentication reference](https://developer.atlassian.com/cloud/jira/platform/rest/v3/), [Bitbucket authentication/scopes reference](https://developer.atlassian.com/cloud/bitbucket/rest/), and [Data Center PAT guide](https://confluence.atlassian.com/enterprise/using-personal-access-tokens-1026032365.html).

The deployment owner must also set `WORKLENS_ALLOWED_ENDPOINTS` to comma-separated exact HTTPS base URLs. An empty value denies every real integration. Source `config.allowed_endpoints` must independently contain its exact `base_url`. Neither allowlist accepts host wildcards. For restricted networks, use the Compose integration overlay and separately approve exact destination hostnames in the egress gateway. See [Deployment](DEPLOYMENT.md).

| Adapter | Base URL example | Scope format |
| --- | --- | --- |
| Jira Cloud | `https://company.atlassian.net` | exact project keys, such as `ENG` |
| Jira Data Center | `https://jira.company.example/jira` | exact project keys |
| Bitbucket Cloud | `https://api.bitbucket.org` | `workspace/repository-slug` |
| Bitbucket Data Center | `https://code.company.example/bitbucket` | `PROJECT/repository-slug` |
| Confluence Cloud | `https://company.atlassian.net/wiki` | numeric space IDs, such as `12345` |
| Confluence Data Center | `https://docs.company.example/confluence` | exact space keys, such as `ENG` |

HTTPS context paths are preserved. Do not include `/2.0`, `/rest/api`, or `/api/v2` in the base unless they are part of a documented API gateway prefix. Private destination addresses require both the deployment URL allowlist and explicit `config.allow_private_hosts: true`; the gateway also requires approved internal destination ranges. Loopback, link-local, multicast, unspecified, and reserved addresses remain forbidden. Use `WORKLENS_CA_BUNDLE` for an internally managed CA bundle; certificate validation cannot be disabled through source configuration.

## Fields, identities, and evidence

Allowlisted canonical fields are `title`, `status`, `assignee`, `due_date`, `priority`, `sprints`, `dependencies`, `outcomes`, `changelog`, `reviewers`, `approvals`, `merge`, `builds`, `version`, `ownership`, `revisions`, `reviews`, `email`, `labels`, `work_type`, and `authorship`. Unknown names fail validation. Select only fields required for the stated purpose. Live sources with no selected fields retain only necessary record identifiers, source scope, timestamps, and evidence links.

Page bodies, ticket descriptions, comments, attachments, diffs, email inboxes, profile photos, and free-text edit messages are excluded. Some source endpoints return additional attributes; these are discarded during normalization and never logged or persisted. Jira requests narrow source fields. Other APIs may return their standard metadata response before local minimization. A response over 2 MiB fails with a safe diagnostic; reduce page size. Fields without a provider equivalent remain absent/unknown or have a coverage marker, never an invented value.

Identity observations use source account IDs/UUIDs/keys and optional email only when `email` is allowlisted. Confluence Data Center falls back to the returned username when no stable user key is provided; review mappings after username changes. No directory-wide profile lookup occurs. Current assignees, PR authors, page authors, reviewers, and explicit collaborators have different meanings. They do not imply sole credit, verified usefulness, proficiency, or actual hours worked. Email is a matching clue, never permission to access an account; ambiguous and even uniquely suggested matches require administrator confirmation in WorkLens. Map service accounts explicitly instead of attributing them to a person.

Jira changelog normalization preserves selected status, assignment, due-date, priority, sprint, and resolution changes. It retains event IDs and transition times, plus separate `transitions` and `assignments` arrays. It excludes body/text edits. Workflow active/blocked/done mappings must be configured before deriving flow observations. Original commitments and approved changes are managed in WorkLens, rather than guessed from the latest ticket due date.

Documentation reviews require either WorkLens assessments or an explicitly configured content property (`config.review_property_key`, for example `worklens.reviews`). The optional property schema is:

```json
{"reviews": [{"reviewer_account_id": "source-account-id", "reviewed_at": "2026-08-21T12:00:00Z", "verdict": "accepted", "evidence_url": "https://docs.company.example/page"}]}
```

Only `accepted` and `changes_requested` verdicts are imported. Free-text property fields are discarded. A property is source-provided evidence, not an independently verified WorkLens assessment. Likes and page-view counts never substitute for reviews.

## Documented API coverage

All paths below are GET requests, relative to the configured base. Cloud and Data Center are not interchangeable.

| Adapter | Implemented endpoints and pagination | Coverage limits |
| --- | --- | --- |
| Jira Cloud | `/rest/api/3/search/jql`, `nextPageToken`; `/rest/api/3/issue/{id}/changelog`, `startAt`/`total` | Uses enhanced search, not the deprecated search API. JQL is constructed from exact projects and parsed updated-since timestamps. |
| Jira Data Center | `/rest/api/2/search`, `startAt`/`total`, optional `expand=changelog` | Search expansions can truncate history. `changelog_complete=false` prevents treating a partial history as complete. |
| Bitbucket Cloud | `/2.0/repositories/{workspace}/{repo}/pullrequests`, next-page token; `/{id}/statuses`, next-page token | Includes open, merged, declined and superseded PRs. Reviewer/approval snapshots and merge metadata are observations. Build statuses are available source results, not full CI history. |
| Bitbucket Data Center | `/rest/api/1.0/projects/{project}/repos/{repo}/pull-requests`, `nextPageStart`/`isLastPage`; `/rest/build-status/1.0/commits/stats/{commit}` | Scans repository PR metadata and filters updates locally. Build totals are commit-level observations. |
| Confluence Cloud | `/api/v2/pages`, space filter and cursor; `/api/v2/pages/{id}/versions`, cursor; optional `/{id}/properties?key=…` | Scans metadata and filters updated timestamps locally because this page listing has no updated-since query. Owner and revision authors are separate. |
| Confluence Data Center | `/rest/api/content/search`, CQL and start; `/rest/api/content/{id}?status=historical&version=N&expand=version`; optional `/{id}/property/{key}` | Reads bounded historical revision metadata individually. Missing/deleted historical versions are marked incomplete. Standard metadata does not establish a distinct page owner. |

Primary references: [Jira Cloud enhanced search](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issue-search/), [Jira Cloud issues/changelog](https://developer.atlassian.com/cloud/jira/platform/rest/v3/api-group-issues/), [Jira Data Center search](https://developer.atlassian.com/server/jira/platform/rest/v10004/api-group-search/), [Bitbucket Cloud PRs/statuses](https://developer.atlassian.com/cloud/bitbucket/rest/api-group-pullrequests/), [Bitbucket Data Center PRs](https://developer.atlassian.com/server/bitbucket/rest/v819/api-group-pull-requests/), [Bitbucket Data Center builds](https://developer.atlassian.com/server/bitbucket/rest/v810/api-group-builds-and-deployments/), [Confluence Cloud pages](https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-page/), [Confluence Cloud versions](https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-version/), [Confluence Data Center content/history/properties](https://docs.atlassian.com/ConfluenceServer/rest/8.9.0/).

The optional Cloud review-property request follows the [Confluence Cloud content properties API](https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-content-properties/).

The Data Center adapter targets the documented REST contract, not every Data Center release or installed extension. Verify against your exact maintained product version. Cloud endpoints and permission scopes can evolve. No unimplemented endpoint or mailbox connector is silently substituted.

## Synchronization and access changes

`adapter.iter_pages(cursor=None)` yields `{records, cursor, complete}`. Each record has `external_id`, `kind`, `scope`, `title`, `url`, `occurred_at`, `updated_at`, `account_id`, `email`, `data`, and `deleted`. Record kinds are `work_item`, `pull_request`, and `document`. A stable source plus external ID is the idempotency key. Nested event IDs preserve duplicate detection. Save each page and its cursor in the same database transaction, then resume from the last committed cursor after interruption.

The cursor records scope position, provider page token, synchronization boundary, and a configuration fingerprint. A completed cursor starts a new incremental scan with a five-minute overlap. Existing IDs update idempotently. Changing scopes, endpoint, fields, or custom field mappings invalidates the cursor; restart a full synchronization/reconciliation. Source-side eventual consistency and offset paging can still cause temporary omissions during concurrent edits; schedule full reconciliation as well as incremental scans.

GET requests have bounded timeouts, page sizes (1–100), retries (0–5), and a nested-page budget (default 100). HTTP 429 and 5xx use exponential backoff/jitter and bounded `Retry-After`. The default minimum request interval is 0.1 seconds; set `config.min_interval` to meet source quotas. An exhausted budget fails rather than calling partial collection complete. DC Confluence revision depth is bounded and reports its earliest requested revision and missing version numbers. Credential values and upstream bodies never appear in diagnostics.

HTTP 401/403 disables the source and makes retained observations unavailable. HTTP 404 means missing **or** hidden, so it cannot prove deletion. A full reconciliation marks previously retained but unseen records unavailable only after every page completes successfully. Incremental absence never deletes data. A fixture tombstone demonstrates an explicit confirmed deletion. Use source purge to remove retained records and mappings; apply backup retention separately. Disable a source before removing upstream access. Individual source ACL changes may be invisible until reconciliation; choose an appropriate reconciliation interval and restrict WorkLens audiences independently of the service account.

All redirects are refused. Pagination extracts documented cursor values and reconstructs requests locally; it cannot switch host or repository/page-listing path. Direct HTTPS pins a DNS address after checking every returned address and preserves the original certificate hostname/SNI. In proxy mode, only the deployment's `WORKLENS_EGRESS_PROXY` is honored; ambient `HTTP_PROXY`/`HTTPS_PROXY` are ignored. The approved proxy performs CONNECT and must independently enforce destination IP restrictions against DNS rebinding. Source metadata URLs are never fetched.

## Verification before operational use

Run `python -m unittest tests.test_connectors` from `backend` for fixture protocol/security tests. They cover all six adapters, cursor resume, stable IDs, duplicate replay, incremental filtering, field minimization, authorization failure, unknown deletion, pagination escape, read-only transport, retry limits, DNS checks, redirects, body limits, and explicit proxy configuration. They do not prove that a real endpoint or container network is correctly configured.

For each real source: confirm its exact maintained version and token scopes; check connection diagnostics for every selected scope; compare imported records and multi-page totals against an administrator-authorized source view; interrupt and resume a sync; change a record and verify the update; revoke access and test quarantine; run reconciliation after hiding/deleting a test record; verify no write permission is granted; inspect egress gateway/firewall logs and run the deployment egress probe. Use synthetic records in an isolated source project for these checks. Record the date, deployment version and results in local operational documentation before describing that installation as live-verified.
