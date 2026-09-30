# API reference

The JSON API is rooted at `/api/`. Collection endpoints return arrays. Numeric
database IDs identify records; `Employee.stable_id` is the durable organization
identifier. Missing values are `null`, not inferred zero. All protected endpoints
require an authenticated, active application account.

## Sessions and setup

| Method | Path | Contract |
| --- | --- | --- |
| GET | `/auth/session/` | `{user, csrfToken}`; user includes ID, username, access role and employee ID |
| POST | `/auth/login/` | `{username,password}`; returns user and rotated CSRF token |
| POST | `/auth/logout/` | Ends the local session |
| GET | `/setup/` | Whether initial administrator setup is required |
| POST | `/setup/` | Initial `{username,password,email}`; refuses after bootstrap |
| GET | `/health/` | Minimal database health; no employee/configuration disclosure |

Use the returned CSRF token as `X-CSRFToken` for unsafe methods, retain the
HttpOnly session cookie, and send the correct same-origin Referer/Origin under
HTTPS. All login/setup writes require CSRF, including anonymous requests. Secure
cookies are enabled outside development. Protect a new unbootstrapped installation
on loopback or a restricted network until an administrator is provisioned.

## Resource collections

`GET /{collection}/`, `GET /{collection}/{id}/`, `POST /{collection}/`,
`PATCH /{collection}/{id}/`, `DELETE /{collection}/{id}/` are available only where
the role and lifecycle permit. Read-only or immutable resources reject mutation.

| Collections | Typical access |
| --- | --- |
| `employees`, `teams`, `roles`, `memberships` | Scoped reads; organization changes by system admin |
| `sources`, `sync-runs`, `identities`, `access-scopes` | Integration/system admin; sync history and identities use actions |
| `source-records` | Minimized imported observations; source and employee scope checks |
| `work-items`, `contributions` | Authorized employee evidence; reviewed changes via explicit actions |
| `goals`, `outcomes`, `reviews` | Employee/reporting scope; verification by an authorized different reviewer |
| `skills`, `assessments`, `roadmaps`, `requirements` | Shared taxonomy and roadmap; scoped assessments |
| `corrections`, `approvals` | Employee/request scope; append-only review history |
| `metric-definitions`, `snapshots` | Read-only definitions/results; calculations create snapshots |
| `audit-events` | System-admin read; no API edit/delete |

Employee-owned collections support `?employee={id}` without expanding the caller's
authorization scope. Integration admins see only the directory attributes needed
for mapping; source administration does not grant workforce-review access.

## Workflow actions

| Method / path | Input or result |
| --- | --- |
| `GET /dashboard/` | Authorized summary, recent evidence and personal metrics |
| `GET /employees/{id}/metrics/` | Latest snapshot for each dimension |
| `POST /employees/{id}/calculate/` | Optional `window_start`, `window_end`, `roadmap`, `category` |
| `POST /employees/{id}/offboard/` | System admin disables login and closes active membership |
| `POST /employees/{id}/account/` | System-admin local account provisioning/reset; validated password |
| `POST /sources/{id}/test/` | Safe diagnostics and coverage; never serializes credentials |
| `POST /sources/{id}/sync/` | Queues live sync; small bundled fixtures finish inline |
| `POST /sources/{id}/reconcile/` | Full visible-record reconciliation, preserving revocation distinction |
| `POST /sources/{id}/purge/` | Disabled source only; removes retained observations/derived copies |
| `POST /identities/{id}/resolve/` | `{employee: id}` or `{service: true}` |
| `POST /work-items/{id}/commit/` | Explicit reviewed commitment with due date and note |
| `POST /work-items/{id}/quality/` | Reviewed quality observations with evidence and attribution |
| `POST /contributions/{id}/verify/` | Requires evidence and a different authorized reviewer |
| `POST /outcomes/{id}/verify/` | Human-verifies evidenced business impact |
| `POST /assessments/{id}/verify/` | Appends a verified assessment linked to its predecessor |
| `POST /corrections/{id}/review/` | `{decision: approved|rejected, review_note}` |
| `POST /report-jobs/` | `{employee: id, format: csv|pdf}` queues a bounded background report |
| `GET /report-jobs/` | The caller's authorized job history and generation status |
| `GET /report-jobs/{id}/download/` | Completed, unexpired artifact after renewed authorization checks |
| `GET /reports/export/?employee={id}&format=csv|pdf` | Authorized file; export is audited |
| `GET /retention/` | Preview expired retained observations |
| `POST /retention/` | `{confirm: true}` applies reviewed deletion policy |

Example synthetic fixture source:

```json
{
  "name": "Local synthetic fixture",
  "kind": "fixture",
  "deployment": "fixture",
  "scopes": ["DEMO"],
  "fields": [],
  "config": {"fixture": "demo"}
}
```

Real sources require a separately configured `base_url`, nonempty source and field
allowlists, and locally entered write-only `credentials`. Credentials are encrypted
at rest and omitted from responses. `has_credentials` only reports their presence.
See [CONNECTORS.md](CONNECTORS.md) for source-specific scope syntax and endpoints.

Queued report artifacts expire after 24 hours and are capped at 2 MiB. Limits also
bound pending and retained jobs per user and installation. Run the local worker to
generate them. Employee, requester and current source/snapshot authorization are
rechecked when generating and downloading; a previously authorized file does not
remain downloadable after its source evidence becomes inaccessible.

## CSV import

`POST /csv-import/` accepts `{kind, content}` where `content` is CSV text up to
1 MiB and 5,000 rows. System admin only. Supported kinds: `employees`, `teams`,
`roles`, `skills`, `goals`, `assessments`, `historical_records`, `memberships`.
Unknown/protected fields fail validation. Imports run atomically and report
created/updated row counts. Assessments imported from CSV are evidence-supported,
never automatically verified. Employee references accept stable employee IDs.

```json
{
  "kind": "employees",
  "content": "stable_id,name,email,capacity\nDEMO-010,Taylor Demo,taylor@example.test,80\n"
}
```

## Errors and audit

Validation generally returns 400, unauthenticated/forbidden access 403, inaccessible
records 404, and throttled requests 429. Source failure text uses safe categories,
not vendor response bodies or credentials. Check sync history for progress,
checkpoints and last successful synchronization. Public APIs do not expose raw
source-page bodies, mailbox content or hidden performance scores.
