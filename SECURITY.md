# Security reporting and operating boundaries

Do not put production credentials, personal employee records or vulnerable
deployment details in public issues. Use the repository's private vulnerability
reporting feature if enabled, or arrange a private channel with the maintainer.
Until then, report only a minimal synthetic reproduction without sensitive data.

This is a tested reference implementation, not a certification
of suitability for a particular employer. Review [verification and limitations](docs/VERIFICATION.md),
identity-provider boundaries, connector scopes, employee access, retention and
infrastructure controls before importing real records.

The application does not make employment decisions. Its deterministic evidence
views must not be presented as employee worth, potential, or automatic hiring,
termination, promotion or pay recommendations.

Runtime network access is opt-in. Development dependency installation and public
CI use network services; they are separate from the company-controlled runtime.
Never run public CI against production employee databases or source credentials.

Keep `.env`, databases, backups, private TLS keys and local integration credentials
out of version control. `.gitignore` helps prevent accidents, but operators must
inspect staged files before publication. Rotate any accidentally exposed secret.

Employee/manager authorization is enforced by the API, including exports.
Integration administrators administer sources and identity mappings. System
administrators and database administrators are privileged operators; audit logs
are application-append-only but not cryptographically tamper-proof against a
database administrator. Forward them only to an approved, self-hosted audit
system if stronger operational separation is required.
