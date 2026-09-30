# Deployment and operations

## Local development

Requires Python 3.13, Node 22.12+, and npm. From the repository root:

```sh
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
DEBUG=1 .venv/bin/python backend/manage.py migrate
DEBUG=1 .venv/bin/python backend/manage.py seed_demo --password 'WorkLens-demo-2026!'
DEBUG=1 .venv/bin/python backend/manage.py runserver 127.0.0.1:8000
# Another terminal:
cd frontend
npm ci
npm run dev
```

Use the displayed local Vite URL. Development SQLite and synthetic accounts are for evaluation. Never reuse the documented demo password on an accessible company installation. Run `DEBUG=1 .venv/bin/python backend/manage.py run_worker` in another terminal to process queued synchronization work. Development processes do not have the container network isolation described below.

## Company-controlled Linux deployment

Docker Engine and the Compose plugin are prerequisites. Verify host patching, disk encryption (for example an organization-managed LUKS volume), backup storage access and certificate issuance using company procedures. Mount database, container logs, temporary files and backup staging on encrypted company-controlled storage. Application field encryption protects connector credentials; it does not encrypt the entire employee database.

```sh
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/init_local.py
mkdir -p certs
# Provision company-issued fullchain.pem and privkey.pem in certs/.
# Edit .env locally: hostnames, CSRF origins, database credentials and policies.
docker compose build
docker compose up -d db
docker compose run --rm api python manage.py migrate
docker compose run --rm api python manage.py createsuperuser
docker compose up -d
```

`init_local.py` creates random keys and a database password with file mode 0600 and refuses to overwrite `.env`. Back up the application encryption key in a separate company-controlled secret store. Container environment variables are visible to Docker administrators; use your organization's secrets injection mechanism where required. Do not paste production keys into prompts, tickets, or Git.

HTTPS listens at port 8443, bound to loopback by default. To expose it on an approved host interface, set `WORKLENS_BIND` to that interface's IP in `.env`. Set `ALLOWED_HOSTS` to the expected hostnames, and `CSRF_TRUSTED_ORIGINS` to the exact HTTPS origins including nonstandard ports. Install a valid company-issued certificate; no automatic public ACME request is made. The API and database have no published ports. nginx replaces forwarded headers. Do not expose the API directly or trust client-supplied proxy headers.

The initial superuser has system-administrator access. Create employee records and assign their existing local user accounts through the administration interface. Keep employee, manager, reviewer and integration-administrator responsibilities distinct. Database administrators necessarily have privileged access to stored data.

## Network modes

The API, worker and database share a Compose network with `internal: true` and have no ordinary outside route. The HTTPS frontend also joins an ingress network so Docker can publish its port. Before nginx starts, its entrypoint installs default-deny IPv4/IPv6 OUTPUT firewall rules, allowing only replies to established requests and a new connection to the resolved internal API address on port 8000. It then drops NET_ADMIN/NET_RAW from nginx's capability bounding set. Startup fails if the firewall cannot be installed. This requires a Docker host that supports container network-namespace iptables and the initial NET_ADMIN capability. The browser loads local compiled assets only. No telemetry, remote fonts, analytics, AI, mailboxes or external storage are configured.

To enable approved sources, configure exact HTTPS origins in the application server policy and exact hostnames in `deploy/allowed-hosts.txt`. For internal source services, additionally permit their narrow destination CIDRs in `deploy/allowed-internal-cidrs.txt` and configure the connector transport's internal-host policy (see [CONNECTORS.md](CONNECTORS.md)). Never allow metadata, loopback, link-local or broad arbitrary destinations.

```sh
docker compose -f compose.yml -f compose.integrations.yml up -d
docker compose exec api python scripts/check_egress.py
docker compose exec worker python scripts/check_egress.py
```

Only the Squid gateway can initiate approved external source connections. It permits HTTPS CONNECT on 443 to explicitly allowed hosts; blocks other requests; rejects sensitive destination IPs and denies unapproved private IPs. The application validates origin/context, DNS and redirects as a separate layer. Gateway policy changes are configuration changes: review them, record an operator audit entry and restart the gateway. The frontend pins its internal API address at startup: restart `web` after recreating `api` so its upstream and firewall rule use the new address. Docker administrators remain trusted infrastructure operators.

Cloud Jira/Bitbucket/Confluence connections constitute **cloud-connected operation**, even though application data stays self-hosted. Entirely internal source endpoints avoid that dependency. Neither arrangement alone proves an air gap. Enforce organization DNS/firewall rules too: Docker network isolation does not constitute a complete policy for every DNS, host, browser or administrator channel. `check_egress.py` tests representative IPv4/IPv6 connections, not every possible exfiltration technique. Repeat checks after networking changes, inspect gateway deny behavior, and inspect browser requests during main workflows.

When a source is unavailable, retained synchronized data remains usable with visible last-success/freshness indicators. A confirmed revoked source scope is excluded by the persistence layer. Availability and authorization revocation are different conditions.

## Restricted-network installation

Build and scan images on an approved build machine or internal CI with internally mirrored base images, PyPI wheels and npm packages. All Python runtime dependencies are pinned in `requirements.txt`, npm dependencies in `frontend/package-lock.json`, and base images by digest. Container build arguments allow replacing base images with approved internal registry references. Standard Dockerfiles expect access to configured package indexes during the build; no dependency installation occurs at runtime.

For a disconnected runtime, transfer approved prebuilt `worklens-api:1.0.0`, `worklens-web:1.0.0`, the pinned PostgreSQL image, and optional gateway image via `docker save`/`docker load` and your controlled media process. Use `docker compose up --no-build --pull never`. Transfer source/configuration separately, provision secrets and TLS locally, then run migrations. Match image platform to the Linux server. No external authentication provider is required for local login.

## Upgrade and rollback

1. Read release limitations, dependency changes and migrations in a staging environment.
2. Stop or drain the synchronization worker. Create an encrypted database backup and verify restoration to a separate database.
3. Record the deployed commit and image digests; retain the prior application images.
4. Build/import the new images, run `python manage.py migrate`, restart API/worker/web and exercise authorization and report workflows.
5. If rollback requires reversing an incompatible migration, restore the backup into an isolated replacement database and deploy the matching old images. Do not blindly reverse data migrations or delete the active database.

Replace the static volume when frontend/admin assets change if using a pre-existing volume. Build verification alone is not a security audit or capacity certification. Patch dependency pins and image digests on a reviewed schedule.

## Troubleshooting

- Database not ready: `docker compose ps` and `docker compose logs db`; verify local configuration and disk capacity without printing passwords.
- CSRF/403 login: check browser HTTPS origin, proxy Host header, `ALLOWED_HOSTS`, secure cookies and `CSRF_TRUSTED_ORIGINS`.
- Empty employee profile: check identity resolution, source/team scopes, shared-contribution records and selected metric period.
- Insufficient evidence: inspect denominator, minimum sample, assessment coverage and freshness before changing policy.
- Queued source: check worker health and sync history. Investigate a failed scope before retrying.
- Source denied: verify endpoint allowlists, DNS policy, certificate trust and minimum read permissions; do not disable SSL verification.
- Never publish logs containing secrets or source payloads. The application stores compact safe failure categories; retrieve vendor diagnostics locally when necessary.
