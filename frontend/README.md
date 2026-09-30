# WorkLens frontend

React and TypeScript client for the real WorkLens Django API. All images, icons, code and styling are served locally; the application loads no fonts, analytics, AI services or external assets.

## Development

Use Node.js 22.12 or newer and an approved package registry or offline npm cache:

```sh
npm ci
npm run dev
```

The development server listens on `127.0.0.1:5173` and proxies `/api` and `/admin` to Django on `127.0.0.1:8000`. Start and seed the backend using the root README. The backend must trust the development origin for CSRF; its DEBUG defaults include localhost port 5173. Production runs behind the same HTTPS origin and uses explicit trusted origins.

```sh
npm run typecheck
npm run build
```

Vite emits local assets under `dist/`. The production container serves this directory through the HTTPS reverse proxy. Do not use Vite's development server for production.

## Actual browser workflows

Start the backend and frontend with a disposable synthetic demo database before testing. Tests create source fixtures and append review records, so do not run them against production data.

```sh
# macOS uses an installed Google Chrome by default.
# On Linux, install the Playwright Chromium build from approved infrastructure:
npx playwright install chromium
npm run test:e2e
```

`E2E_BASE_URL` selects a different deployment (for example `https://localhost:8443`). `E2E_PASSWORD` selects the synthetic seed password. `E2E_BROWSER_CHANNEL` optionally selects an installed Chrome channel. The default test password is the documented development-only synthetic password. The browser suite uses no mocked API routes and verifies:

- Source configuration, fixture connection diagnostics, synchronization and service-account resolution.
- Versioned metric calculation, evidence drill-down and an authorized CSV download.
- Employee context submission, independent reviewer approval and forbidden cross-employee exports.
- Every main screen, responsive navigation and narrow-screen overflow.
- No external browser requests during the main workflow and no React runtime errors.

## Interface behavior

The API enforces record authorization. Role-aware navigation complements those server checks. CSRF tokens are obtained from the session endpoint and rotated on authentication. Forms preserve validation errors and do not silently dismiss failed saves. Failed refreshes retain previously loaded records with a visible warning.

Skills, contribution evidence, claims and verified assessments remain distinct. Metric dialogs expose versions, formulas, denominators, exclusions, source freshness and source links. Unknown values are never converted to zero. Queued report downloads recheck current server permissions.

The source is formatted with the pinned Prettier version:

```sh
npx --no-install prettier --check src tests package.json tsconfig.json vite.config.ts playwright.config.ts index.html
```
