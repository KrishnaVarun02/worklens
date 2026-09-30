# Verification record

## Executed checks — 30 September 2026

All checks used synthetic data. The local host was macOS with Python 3.13 and Node 22; production-style checks ran in Linux containers with PostgreSQL 17.11, Gunicorn and nginx over HTTPS. The localhost certificate was self-signed and accepted only by the test clients. This is execution evidence for this build, not a third-party audit or live vendor certification.

| Check | Observed result |
| --- | --- |
| Django test suite | **99 passed** against SQLite and the same **99 passed** against container PostgreSQL; includes six connector protocols, metrics, imports, permissions, source access changes, report jobs and SSO adapter regressions |
| Database schema | All seven core migrations applied; migration drift check passed |
| Backup envelope tests | **3 passed**: multi-megabyte round trip, wrong key/tampering, truncation and refusal to overwrite outputs |
| Real database recovery | Dumped the final PostgreSQL schema, encrypted and authenticated/decrypted the archive, compared bytes, restored into a separate empty database; verified six employees, 21 frozen snapshots, password login, latest migration and decryption of a synthetic connector credential |
| Frontend | TypeScript and production build passed; formatting check passed; npm audit reported zero vulnerabilities at check time |
| Real browser workflows | **4 passed** in Chromium/Chrome, covering all five roles, source setup/synchronization, identity review, metric explanations, CSV download, queued worker reports, correction approval and forbidden access |
| Responsive/runtime checks | Desktop screens and seven mobile screens inspected; tested views had no horizontal overflow or JavaScript runtime errors; main workflow observed no external browser requests |
| Final HTTPS acceptance | Actual sessions and CSRF, fixture configuration/sync, confirmed identity, repeat-sync idempotence, seven metrics, employee correction, manager approval, CSV/PDF export, cross-employee denial and source purge passed through nginx/Gunicorn/PostgreSQL |
| Production report worker | Queued PDF completed in the running worker and downloaded through the authorized HTTPS endpoint |
| Report layout | Both pages of the generated A4 PDF rendered and visually inspected; sections, units and page footers were readable without clipping or orphaned section headings |
| Container build/start | Pinned backend and frontend image builds succeeded; database health, API, worker and HTTPS frontend verified |
| Runtime egress | API and worker probes to representative IPv4/IPv6 external destinations were blocked; optional Squid gateway rejected an unapproved hostname; web container outbound probe was blocked and nginx's capability set excluded network administration/raw sockets |
| Publication review | Source/docs/assets checked for accidental credentials, employee data and private filesystem paths; local secrets, databases, certificates, archives, dependencies and scratch output excluded from Git |

These are bounded checks of the supplied topology. They do not prove that every destination, DNS path, browser extension, host configuration or future dependency is safe.

Normal Django system checks passed. `check --deploy` reports three deliberate defaults: W005 (HSTS does not include every subdomain), W008 (Django does not redirect HTTP), and W021 (HSTS preload is off). The supplied external nginx listener accepts TLS only. Review the organization's domain ownership and proxy topology before enabling subdomain-wide HSTS, preload or application redirects.

Repeat the API acceptance check against an isolated seeded installation with a running worker:

```sh
.venv/bin/python scripts/smoke_api.py --queued
# Local self-signed container deployment only:
.venv/bin/python scripts/smoke_api.py --base-url https://localhost:8443 --insecure-local --queued
```

Repository CI repeats database, frontend and browser checks on synthetic data. The repository's Actions page records those separate remote results.

## Remaining limitations

This repository contains a working application and tested workflows. The following boundaries remain; they are not claims of full production readiness or complete fulfillment of every possible enterprise deployment.

- **Live integrations remain unverified.** No real Jira, Bitbucket or Confluence credentials were available. The six separate adapters are tested against synthetic responses and documented API contracts. Each actual Cloud tenant and maintained Data Center version needs the live checklist in [CONNECTORS.md](CONNECTORS.md). There is no certified Data Center version range. Interactive OAuth setup and token refresh are not implemented; provision and rotate an appropriate read-only token locally.

- **Source coverage has explicit gaps.** Jira Data Center search can truncate expanded changelogs; incomplete history suppresses flow conclusions. Confluence historical revision reads have a bounded budget and expose missing versions; standard Data Center metadata does not establish a distinct document owner. Bitbucket supplies available PR/build observations rather than a full CI, incident, or service-reliability history. Repository language inventories and training-system records are not imported by the bundled adapters. Skill rules for those fields need an additional authorized source extension; labels and work categories work with the existing evidence.

- **Source access changes are discovered during checks or reconciliation.** A successful incremental scan does not establish that every retained record is still visible upstream. Individual deletions or changed ACLs can remain unknown until full reconciliation. Missing records become unavailable, rather than being asserted deleted. Source outages preserve permitted cached evidence with freshness indicators. Set an operational reconciliation interval and apply the WorkLens audience rules independently of source-account permissions.

- **Recurring schedules are an operator responsibility.** The worker processes queued work; the application does not include an in-product recurring synchronization, reconciliation, retention or backup scheduler. Trigger approved API/management operations using a company-controlled scheduler. Backup expiration and the deletion ledger applied after restoring old backups remain documented operator procedures.

- **Capacity and work context are descriptive.** The employee capacity percentage, context, role/team history, dependencies, complexity and recorded workflow intervals accompany evidence. There is no time-based capacity calendar, structured absence/onboarding adjustment, cross-role calibration, or automatic complexity normalization. Reviewers must interpret those factors; the formulas do not manufacture adjusted productivity.

- **Shared contribution is represented without inferred effort allocation.** Source authors, current assignees, reviewers, explicit shared accounts and reassignment history remain observations. Historical assignee participation, pairing, mentoring, usefulness and credit shares are not reconstructed automatically from activity. Add and review the relevant evidence. Cross-team changes to shared commitments require a reviewer/system administrator with the necessary scope.

- **Quality uses a common maturity policy.** Acceptance, reopening, rework and supported defect attribution are structured reviewed observations. The completion-age cutoff is a deployment setting, not a category-specific defect-discovery model. There is no integrated incident-attribution or team/service reliability pipeline. Recently completed work is excluded until the configured observation window matures.

- **Goal progress is the current recorded state.** The business view averages currently stored goal percentages and separately lists verified outcomes in the selected period. It does not maintain a time series of goal progress, infer financial value, or allocate revenue to employees. A historical calculation is not a reconstruction of every goal's past progress.

- **Historical reproducibility is snapshot-based.** Saved calculations contain their formula/configuration versions and copied inputs. Recalculating an old date window uses currently retained source/commitment data and the selected configuration; it is not a general event-sourced “as of that date” reconstruction. Current access restrictions and deletion policies can hide or remove historical snapshots containing affected source material.

- **Corrections are dated context addenda.** Approval preserves the original observation and adds the requested context with the review decision. It does not automatically rewrite source facts or substitute numerical metric inputs. Correct an erroneous upstream fact at its source, or record a supported commitment/quality/assessment change through its explicit workflow, then calculate a new snapshot.

- **Metric customization is bounded.** Formula implementations are fixed deterministic code; administrators configure permitted data and policies rather than arbitrary formulas. Global evidence/maturity defaults are deployment settings. Skill proficiency uses levels 1–5 with configurable rubric descriptions. Roadmap alignment currently requires every required skill to have a fresh verified assessment, even when a lower completeness preference is stored; partial coverage is shown without an overall result.

- **Scale has not been certified.** The initial resource list APIs and client collections are unpaginated. Some source adapters must scan authorized metadata before applying incremental filtering locally. This edition has no documented large-workforce performance envelope, high-availability failover result, or large-volume recovery-time guarantee. Run representative load and recovery rehearsals before choosing operational capacity targets.

- **Identity-provider integration is a deployment adapter.** Local sessions work independently. Optional SSO accepts a trusted WSGI `REMOTE_USER` from an organization-operated authentication server; it has fixture/regression coverage, not a live company-provider test. The default nginx/Gunicorn stack does not supply that identity by itself. There is no bundled OIDC/SAML client flow, automatic directory provisioning, or local self-service password-recovery service. See [IDENTITY_PROVIDER.md](IDENTITY_PROVIDER.md).

- **Infrastructure security still needs installation-specific verification.** Connector secrets and backups use application encryption; full database/disk encryption depends on company-controlled storage configuration. TLS certificates, secrets injection, browser behavior, DNS, host firewalls, restricted dependency mirrors and egress gateway rules must be validated in the target environment. Local checks do not establish zero leakage, zero data loss, an air gap, or production certification.

## Support matrix

“Implemented” describes code present in this repository. “Fixture/regression coverage” describes automated synthetic checks, not live vendor certification. Exact final execution results and deployment evidence are recorded separately in this document.

| Area | Implemented support | Verification boundary / remaining scope |
| --- | --- | --- |
| Application and persistence | React/TypeScript client; Django REST API; database models and migrations; synthetic seed; PostgreSQL deployment and SQLite development | Final build/database/browser execution results must identify the actual environment; no production load certification |
| Local authentication | Django passwords, sessions, CSRF, initial setup, explicit account provisioning and offboarding | Automated authorization/authentication cases; local recovery is an administrator process |
| Optional company identity | Pre-provisioned accounts through trusted WSGI `REMOTE_USER`; spoofed client headers rejected | Fixture/regression coverage; company authentication server and provider not live-tested |
| Authorization | Employee, manager, reviewer, integration administrator and system administrator roles; reporting scope; optional source/team bindings | Regression coverage includes record IDs, imported-evidence immutability, shared commitment edits, revoked records, historical snapshots and exports; reviewer is an expressly assigned cross-team role |
| Jira Cloud | Enhanced issue search, selected structured fields, paginated changelog, incremental checkpoints | Synthetic protocol tests; live tenant/authentication/permissions and source-timezone configuration need verification |
| Jira Data Center | Separate v2 search adapter, project/field selection, offset pagination and expanded history | Synthetic protocol tests; no certified product-version range; truncated history marked incomplete |
| Bitbucket Cloud | Repository-scoped PR authors/reviewers/approvals/merge metadata and available statuses | Synthetic protocol tests; no live workspace verification or full CI-history import |
| Bitbucket Data Center | Separate repository PR API, documented continuation offsets and commit build statistics | Synthetic protocol tests; no certified product-version range or live installation verification |
| Confluence Cloud | Space-scoped page metadata, authorship/ownership, revision pages and optional explicit review property | Synthetic protocol tests; body/comment content excluded; metadata scanning and revision gaps remain visible |
| Confluence Data Center | CQL content metadata, bounded historical version reads and optional review property | Synthetic protocol tests; owner unknown where not supplied; missing historical versions marked incomplete |
| Fixture and CSV | Offline source fixtures; directory, teams, roles, skills, goals, assessments, historical evidence and membership CSVs | Synthetic/idempotency validation; CSV is a structured import workflow, not a generic connector or arbitrary schema loader |
| Evidence and reviews | Imported observations, manual claims, source identity resolution, shared evidence, independent verification, context corrections and audit records | Human usefulness/proficiency/impact review remains required; context correction does not rewrite source facts |
| Deterministic metrics | Delivery reliability, categorized flow, reviewed quality, goals/outcomes, collaboration evidence, verified skills and selected-roadmap alignment | Formula/regression coverage; descriptive context, global default thresholds and snapshot-based history as described above |
| Reports | Authorized CSV/PDF employee reports; CSV includes detailed snapshot provenance and PDF provides a readable summary | Access and source-audience checks apply to exports; files downloaded by authorized users are governed by company storage/sharing policy |
| Background work | Company-controlled database-backed worker and durable synchronization checkpoints | Recurrence requires a company scheduler; exact queued-report/worker verification is recorded with the final execution results |
| Lifecycle and recovery | Source disabling/quarantine/purge, retention preview/deletion, employee offboarding, encrypted backups and restore tooling | Active deletion does not rewrite old backups; backup expiration, deletion replay and target-volume recovery rehearsals remain operational duties |
| Network and deployment | HTTPS reverse proxy; local frontend assets; runtime isolation; optional explicit HTTPS egress gateway; endpoint/DNS/redirect safeguards | Final container checks apply only to the tested topology; browser, DNS, host privileges and installation-specific controls still need validation |

No AI, hosted analytics, mailbox ingestion, individual company-wide leaderboard, employee-worth score, or automatic employment/compensation decision is part of this application. Those exclusions are intentional product boundaries.
