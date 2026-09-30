# Optional company identity provider

Local Django login works without any hosted authentication provider. WorkLens also
includes an optional trusted **WSGI `REMOTE_USER`** adapter built on Django's
established remote-user authentication mechanism. It is disabled by default.

This adapter is for an organization-operated authenticating WSGI web server,
for example Apache/mod_wsgi integrated with the company's existing Kerberos,
LDAP or OpenID Connect authentication module. That server validates the identity
provider's authentication and supplies the resulting stable username as the WSGI
environment variable `REMOTE_USER`. WorkLens does not perform email-based login
inference and never automatically creates users from provider identities.

1. Provision a local user and explicitly link it to the correct active employee.
2. Configure the company authentication module to supply that exact local username.
3. Deploy `config.wsgi.application` behind that trusted WSGI server and set
   `WORKLENS_REMOTE_USER=1` in its environment. Preserve session/CSRF/HTTPS settings.
4. Ensure all routes pass through authentication where required. Restrict direct
   application access and limit required provider endpoints using company egress rules.
5. Verify login, user switching, revoked/disabled identities and logout in staging.

The default nginx/Gunicorn Compose deployment does **not** set WSGI `REMOTE_USER`;
enabling the flag there by itself does not enable SSO. Client headers including
`Remote-User` and `X-Auth-User` are not accepted as identity. Do not change the
middleware to trust `HTTP_*` values. This adapter rejects ASGI requests to avoid
different header semantics. An unknown username or offboarded employee cannot log in.

Local login remains available for a controlled administrator recovery account.
An upstream authenticated session may log the person back in immediately after
local logout, so the company authentication module must provide its own logout
route/session policy. WorkLens ends an existing remote-authenticated session when
the WSGI identity is no longer supplied.

The repository tests cover trusted WSGI login, header-spoof rejection and inactive
accounts. No live company provider, Apache configuration, OIDC token flow, or
Kerberos environment was available for verification. Provider-specific modules,
certificates and mappings require a separate deployment test.

Reference: [Django remote-user authentication](https://docs.djangoproject.com/en/5.2/howto/auth-remote-user/).
