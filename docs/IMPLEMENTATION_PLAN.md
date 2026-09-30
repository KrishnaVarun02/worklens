# WorkLens implementation plan

The repository was empty at inspection. WorkLens is a new modular monolith with a React/TypeScript client, Django REST API, PostgreSQL production database, and database-backed worker. Local development and automated tests can use SQLite. All example people and records are synthetic.

## Assumptions

- No production source credentials or identity-provider configuration are available. Connector verification will use realistic fixtures, with live verification explicitly outstanding.
- The deployment target is a company-controlled Linux Docker host. No external AI, analytics, storage, fonts, or CDNs are used.
- Employee, manager, reviewer, integration administrator, and system administrator are separate application roles. A local superuser bootstraps an installation.
- Source access does not confer employee-record access. Scope and employee relationships are checked by the API.
- Cloud-connected and entirely internal deployments are documented separately; neither is labeled air-gapped without verifying the full environment.
- Publishing the source as a public GitHub repository is explicitly authorized. Only source, synthetic fixtures, and example configuration belong in Git.

## Working increments

1. Authentication, organization/evidence models, migrations, and synthetic seed.
2. Read-only Jira, Bitbucket, Confluence Cloud/Data Center adapters; guarded HTTP, durable synchronization and identity resolution.
3. Versioned deterministic delivery, flow, quality, contribution, collaboration, skills, and roadmap calculations.
4. Responsive dashboards, evidence, goals, assessments, corrections, integration and administration workflows.
5. Authorization regression tests, reports, retention, encrypted backup/restore tooling, deployment and operator guides.
6. Run backend and browser workflows, inspect publication contents, create and push the public repository.

## Shared implementation contract

- Root: `outputs/worklens`; backend Django project `config`, app `core`.
- JSON API prefix `/api/`; session and CSRF authentication. `GET /api/auth/session/` gives `{user: null | {id, username, role, employee_id}, csrfToken}`; POST `/api/auth/login/` takes `{username,password}`; POST `/api/auth/logout/`.
- Resource collections return arrays (no pagination for the initial UI), detail URLs use numeric IDs. Access is always enforced before serialization.
- Resources: `employees`, `teams`, `roles`, `memberships`, `sources`, `source-records`, `sync-runs`, `identities`, `work-items`, `contributions`, `goals`, `outcomes`, `skills`, `assessments`, `roadmaps`, `requirements`, `corrections`, `audit-events`, `metric-definitions`, `snapshots`.
- `/api/dashboard/` returns aggregate information for the authenticated user's scope. `/api/employees/{id}/metrics/` returns dimension snapshots; `/api/employees/{id}/calculate/` calculates and stores them. `/api/reports/export/?employee={id}&format=csv|pdf` exports authorized data.
- Source actions: `POST /api/sources/{id}/test/`, `/sync/`, `/purge/`. Identity action: `POST /api/identities/{id}/resolve/` with employee ID. Correction action: `POST /api/corrections/{id}/review/` with `{decision: approved|rejected, review_note}`. Assessment action: `/api/assessments/{id}/verify/`.
- Connector package lives in `backend/connectors`. Its independent adapter interface receives a config dictionary and yields normalized record pages. Backend owns models and persistence bridge.
- Source config: `{kind: jira|bitbucket|confluence|fixture, deployment: cloud|data_center|fixture, base_url, scopes: [...], fields: [...], config: {...}}`. Secrets are separate encrypted fields and never serialized.
- Normalized records: `{external_id, kind, scope, title, url, occurred_at, updated_at, account_id, email, data, deleted}`. Adapter `iter_pages(cursor)` yields `{records, cursor, complete}`. Credential-free fixtures are local and bundled.
