"""Database-backed, resumable connector import. Each page and checkpoint commit together."""

from datetime import datetime
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime, parse_date
from .models import *
from .crypto import decrypt
from .permissions import record_allowed_for_employee


def adapter_for(source, full_reconcile=False):
    from connectors import get_adapter

    config = {
        key: getattr(source, key)
        for key in ["kind", "deployment", "base_url", "scopes", "fields", "config"]
    }
    if full_reconcile:
        config["config"] = dict(config["config"])
        config["config"].pop("since", None)
    return get_adapter(config, secret=decrypt(source.encrypted_credentials))


def match_identity(source, account_id, email=""):
    if not account_id:
        return None
    mapping, _ = IdentityMapping.objects.get_or_create(
        source=source, account_id=account_id, defaults={"email": email or ""}
    )
    if mapping.status in ["resolved", "service"]:
        return mapping
    email = (email or "").casefold().strip()
    candidates = [
        e.id
        for e in Employee.objects.filter(active=True)
        if email
        and (e.email.casefold() == email or email in [str(x).casefold() for x in e.aliases])
    ]
    mapping.email = email
    mapping.candidates = candidates
    # Even a unique email is a proposed match; an administrator confirms the account.
    mapping.status = "ambiguous" if len(candidates) > 1 else "unresolved"
    mapping.save()
    return mapping


def moment(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    parsed = parse_datetime(value)
    return timezone.make_aware(parsed) if parsed and timezone.is_naive(parsed) else parsed


def quarantine_records(records):
    affected = list(
        Contribution.objects.filter(source_record__in=records).values_list("employee_id", flat=True)
    )
    records.update(available=False)
    MetricSnapshot.objects.filter(employee_id__in=affected).delete()


def bind_record(record):
    identity = IdentityMapping.objects.filter(
        source=record.source, account_id=record.account_id, status="resolved", employee__active=True
    ).first()
    data = record.data
    if record.deleted or not record.available:
        MetricSnapshot.objects.filter(
            employee_id__in=Contribution.objects.filter(source_record=record).values_list(
                "employee_id", flat=True
            )
        ).delete()
        Contribution.objects.filter(source_record=record).delete()
        WorkItem.objects.filter(source_record=record).delete()
        return
    item = None
    if record.kind in ["issue", "work_item", "jira_issue"]:
        due = parse_date(str(data["due_date"])[:10]) if data.get("due_date") else None
        item, created = WorkItem.objects.get_or_create(
            source_record=record, defaults={"title": record.title, "original_due_date": due}
        )
        item.title = record.title
        item.status = data.get("status", "unknown")
        item.category = data.get("work_type", "unspecified")
        if not item.agreed_commitment:
            item.due_date = due
        item.flow_complete = bool(
            data.get(
                "changelog_complete", record.source.kind == "fixture" and data.get("started_at")
            )
        )
        item.started_at = moment(data.get("started_at"))
        item.completed_at = moment(data.get("completed_at"))
        item.dependencies = data.get("dependencies", [])
        item.assignment_history = data.get("assignments", [])
        item.scope_changes = (
            item.scope_changes if item.agreed_commitment else data.get("scope_changes", [])
        )
        item.evidence_url = record.url
        item.active_days = None
        item.blocked_days = None
        workflow = record.source.config.get("workflow", {})
        if record.source.kind != "fixture":
            item.flow_complete = bool(item.flow_complete and workflow and data.get("transitions"))
            if item.flow_complete:
                active = {x.casefold() for x in workflow.get("active", [])}
                blocked = {x.casefold() for x in workflow.get("blocked", [])}
                done = {x.casefold() for x in workflow.get("done", [])}
                transitions = sorted(
                    [t for t in data.get("transitions", []) if t.get("at")], key=lambda t: t["at"]
                )
                started = None
                active_seconds = 0
                blocked_seconds = 0
                for i, t in enumerate(transitions):
                    at = moment(t["at"])
                    state = str(t.get("to_label", t.get("to", ""))).casefold()
                    if state in active | blocked and started is None:
                        started = at
                    stop = (
                        moment(transitions[i + 1]["at"])
                        if i + 1 < len(transitions)
                        else item.completed_at
                    )
                    if at and stop and stop >= at:
                        if state in active:
                            active_seconds += (stop - at).total_seconds()
                        if state in blocked:
                            blocked_seconds += (stop - at).total_seconds()
                item.started_at = started
                item.active_days = active_seconds / 86400 if started else None
                item.blocked_days = blocked_seconds / 86400
                if not started:
                    item.flow_complete = False
        # Quality attribution is never inferred from workflow activity.
        item.save()
    account_ids = (
        {record.account_id}
        | set(data.get("shared_with", []))
        | {r.get("account_id") for r in data.get("reviewers", []) if isinstance(r, dict)}
    )
    valid_employees = set(
        IdentityMapping.objects.filter(
            source=record.source,
            account_id__in=[a for a in account_ids if a],
            status="resolved",
            employee__active=True,
        ).values_list("employee_id", flat=True)
    )
    valid_employees = {
        e.id
        for e in Employee.objects.filter(id__in=valid_employees)
        if record_allowed_for_employee(record, e)
    }
    stale = Contribution.objects.filter(source_record=record).exclude(
        employee_id__in=valid_employees
    )
    MetricSnapshot.objects.filter(
        employee_id__in=stale.values_list("employee_id", flat=True)
    ).delete()
    stale.delete()
    if identity and record_allowed_for_employee(record, identity.employee):
        kind = {
            "pull_request": "authorship",
            "page": "documentation",
            "document": "documentation",
        }.get(record.kind, "delivery")
        Contribution.objects.update_or_create(
            source_record=record,
            employee=identity.employee,
            defaults={
                "share": None,
                "work_item": item,
                "title": record.title,
                "kind": kind,
                "origin": "observed",
                "occurred_on": (record.occurred_at or timezone.now()).date(),
                "evidence_url": record.url,
                "context": "Imported structured source observation; usefulness and proficiency need human review.",
            },
        )

    # Explicit shared accounts and documented reviewers become observations only.
    shared = list(data.get("shared_with", []))
    review_accounts = [
        r.get("account_id") for r in data.get("reviewers", []) if isinstance(r, dict)
    ]
    for account in set(shared + review_accounts):
        if not account or account == record.account_id:
            continue
        mapping = IdentityMapping.objects.filter(
            source=record.source, account_id=account, status="resolved", employee__active=True
        ).first()
        if mapping and record_allowed_for_employee(record, mapping.employee):
            Contribution.objects.update_or_create(
                source_record=record,
                employee=mapping.employee,
                defaults={
                    "share": None,
                    "work_item": item,
                    "title": record.title,
                    "kind": "shared_delivery" if account in shared else "review",
                    "origin": "observed",
                    "occurred_on": (record.occurred_at or timezone.now()).date(),
                    "evidence_url": record.url,
                    "context": "Explicitly linked shared account/reviewer observation; credit share and usefulness are not inferred.",
                },
            )


def purge_source(source):
    affected = Contribution.objects.filter(source_record__source=source).values_list(
        "employee_id", flat=True
    )
    MetricSnapshot.objects.filter(employee_id__in=affected).delete()
    Contribution.objects.filter(source_record__source=source).delete()
    WorkItem.objects.filter(source_record__source=source).delete()
    SourceRecord.objects.filter(source=source).delete()
    IdentityMapping.objects.filter(source=source).delete()
    source.cursor = {}
    source.last_success_at = None
    source.save(update_fields=["cursor", "last_success_at"])


def run_sync(run):
    from connectors import AccessRevoked, RecordUnavailable

    source = SourceSystem.objects.get(id=run.source_id)
    if not source.enabled or source.configuration_revision != run.source_revision:
        run.status = "failed"
        run.error = "Source is disabled or its configuration changed after this job was queued."
        run.finished_at = timezone.now()
        run.save()
        return run
    run.status = "running"
    run.started_at = timezone.now()
    run.save()
    try:
        adapter = adapter_for(source, full_reconcile=run.full_reconcile)
        initial_cursor = run.cursor or (None if run.full_reconcile else source.cursor) or None
        seen = set(run.seen_record_ids)
        for page in adapter.iter_pages(cursor=initial_cursor):
            with transaction.atomic():
                source.refresh_from_db()
                if not source.enabled or source.configuration_revision != run.source_revision:
                    raise ValueError("Source was disabled during synchronization")
                for raw in page["records"]:
                    # Adapters enforce field allowlists; persistence also enforces scope membership.
                    if source.scopes and raw.get("scope") not in source.scopes:
                        continue
                    data = raw.get("data", {})
                    defaults = {
                        key: raw.get(key, "")
                        for key in ["kind", "scope", "title", "url", "account_id"]
                    }
                    defaults.update(
                        data=data,
                        occurred_at=moment(raw.get("occurred_at")),
                        updated_at=moment(raw.get("updated_at")),
                        deleted=bool(raw.get("deleted")),
                        available=not bool(raw.get("deleted")),
                    )
                    previous = SourceRecord.objects.filter(
                        source=source, external_id=str(raw["external_id"])
                    ).first()
                    changed = bool(
                        previous
                        and any(
                            getattr(previous, key) != defaults[key]
                            for key in ["title", "url", "data", "account_id"]
                        )
                    )
                    if changed:
                        # Human verification applies to the reviewed observation version.
                        # Copied historical snapshot inputs stay unchanged.
                        Contribution.objects.filter(source_record=previous).update(
                            verified=False, reviewer=None
                        )
                        AuditEvent.objects.create(
                            action="source_observation_changed",
                            resource="SourceRecord",
                            object_id=str(previous.id),
                            detail={"source": source.id},
                        )
                    record, _ = SourceRecord.objects.update_or_create(
                        source=source, external_id=str(raw["external_id"]), defaults=defaults
                    )
                    seen.add(record.id)
                    match_identity(source, record.account_id, raw.get("email", ""))
                    for account in data.get("shared_with", []):
                        match_identity(source, account)
                    for reviewer in data.get("reviewers", []):
                        if isinstance(reviewer, dict):
                            match_identity(
                                source, reviewer.get("account_id"), reviewer.get("email", "")
                            )
                    bind_record(record)
                    run.records_processed += 1
                run.cursor = page.get("cursor") or {}
                source.cursor = run.cursor
                run.seen_record_ids = sorted(seen)
                run.save(update_fields=["records_processed", "cursor", "seen_record_ids"])
                source.save(update_fields=["cursor"])
        with transaction.atomic():
            source = SourceSystem.objects.select_for_update().get(id=source.id)
            if not source.enabled or source.configuration_revision != run.source_revision:
                raise ValueError("Source configuration changed during synchronization")
            if run.full_reconcile:
                unseen = SourceRecord.objects.filter(source=source).exclude(id__in=seen)
                quarantine_records(unseen)
            source.last_success_at = timezone.now()
            source.save(update_fields=["last_success_at"])
        run.status = "succeeded"
        run.error = ""
    except (AccessRevoked, RecordUnavailable) as exc:
        source.enabled = False
        source.save(update_fields=["enabled"])
        affected = list(
            Contribution.objects.filter(source_record__source=source).values_list(
                "employee_id", flat=True
            )
        )
        SourceRecord.objects.filter(source=source).update(available=False)
        MetricSnapshot.objects.filter(employee_id__in=affected).delete()
        run.status = "revoked"
        run.error = "Source is missing or access is unavailable; deletion is unconfirmed. Retained observations are unavailable until access is explicitly restored."
    except Exception as exc:
        # No exception text: upstream responses and URLs can contain credentials or source content.
        run.status = "failed"
        run.error = f"Synchronization failed ({type(exc).__name__}). Check endpoint, allowlists, permissions, and worker connectivity."
    run.finished_at = timezone.now()
    run.save()
    return run
