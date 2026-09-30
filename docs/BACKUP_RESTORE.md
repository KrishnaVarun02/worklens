# Encrypted backups and restoration

Backups are sensitive employee data. Store them on company-controlled encrypted storage with restricted access. The script uses the established `cryptography` library's streaming AES-256-GCM with a fresh random nonce and authenticated version header. Every restore verifies the full authentication tag before passing any bytes to PostgreSQL. An incorrect key, altered archive or truncated archive must fail.

Generate a separate backup key (do not reuse the connector encryption key):

```sh
mkdir -p secrets backups
.venv/bin/python scripts/backup.py keygen --key-file secrets/backup.key
```

Store this key separately from backups. Both the backup key and the application's `WORKLENS_ENCRYPTION_KEY` are required for full recovery of encrypted connector credentials. Loss of either key can be irreversible.

Install PostgreSQL 17 client tools on the controlled backup host. Supply libpq credentials through a restricted `PGPASSFILE` or locally injected environment; never include passwords in command arguments. Set `PGHOST`, `PGPORT`, `PGUSER`, and `PGDATABASE` for the approved database connection. The production Compose database has no host port: run backup tooling on its private network or use `docker compose exec -T db pg_dump` as below.

```sh
# A protected staging directory on an encrypted filesystem; umask restricts files.
umask 077
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner' > backups/staging.dump
.venv/bin/python scripts/backup.py encrypt --key-file secrets/backup.key \
  --input backups/staging.dump --output backups/worklens.dump.enc
rm backups/staging.dump
```

The dump contains a transactionally consistent database snapshot; do not copy live PostgreSQL data files. Check `pg_dump` exit status before encrypting. A scheduled wrapper should use `set -e` and a unique backup filename. With local PostgreSQL clients, `backup.py create --key-file ... --output ...` pipes `pg_dump` into encryption and only publishes the archive on successful completion.

Restore into an **empty, isolated database** first. With local client tools, set `PGDATABASE` to that restoration target, then run:

```sh
.venv/bin/python scripts/backup.py restore --key-file secrets/backup.key \
  --input backups/worklens.dump.enc --confirm-database worklens_restore
```

The confirmation must exactly match `PGDATABASE`. `pg_restore` uses a single transaction and exits on errors; it does not clean or overwrite a populated database. Decryption stages a private temporary file, so use an encrypted filesystem or controlled tmpfs for `TMPDIR`.

For the container approach, decrypt to a private staging file, create a new database, and stream the verified file to `pg_restore --single-transaction --exit-on-error --no-owner --no-acl`. Test login, row counts, historical metric snapshots and decryption of a synthetic connector credential. Record the backup ID, restoration duration, test results and operator. Only switch the application after this rehearsal succeeds. Never run destructive restoration against the live database just to test a backup.

Run `python -m unittest discover -s scripts -p 'test_*.py'` for encryption, tampering and wrong-key tests. The verified database-restoration results for this version are recorded in [VERIFICATION.md](VERIFICATION.md).

## Retention and deletion

Choose a backup retention period with the company data owner and implement expiration in company storage. A suggested operational starting point is daily copies retained for 30 days, subject to organizational requirements. Enforce deletion of expired backups and keys for expired encryption generations; filesystem deletion is not guaranteed secure erasure on SSDs, snapshots or replicated storage.

Application deletion removes active records but does **not** rewrite old backups. Keep a separately controlled deletion/offboarding ledger. After restoring an older backup, reapply all subsequent deletion requests and revoked source permissions before opening access or restarting synchronization. Avoid recording sensitive reasons for offboarding. Document legal holds through your organization's process rather than silently changing application retention behavior.

Self-hosting and encryption do not guarantee zero leakage or zero data loss. Test backups and restoration regularly, and measure recovery objectives against actual data volumes.
