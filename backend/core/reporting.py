"""Bounded local report generation. Artifact access is checked again on download."""

from django.conf import settings
from django.utils import timezone
from .models import ReportJob, MetricSnapshot
from .permissions import employee_ids, role, snapshot_visible, audit


def expire_reports():
    return (
        ReportJob.objects.filter(expires_at__lte=timezone.now())
        .exclude(status="expired")
        .update(status="expired", payload=None, error="Artifact retention expired.")
    )


def authorized(job, user):
    return bool(
        user.is_active
        and role(user)
        and job.employee.active
        and job.employee_id in employee_ids(user)
    )


def downloadable(job, user):
    if job.status != "succeeded" or job.expires_at <= timezone.now() or not job.payload:
        return False
    if not authorized(job, user) or not authorized(job, job.requested_by):
        return False
    if user.id != job.requested_by_id and role(user) != "system_admin":
        return False
    snapshots = list(
        MetricSnapshot.objects.filter(id__in=job.snapshot_ids).select_related(
            "employee", "definition"
        )
    )
    return len(snapshots) == len(job.snapshot_ids) and all(
        snapshot_visible(snapshot) for snapshot in snapshots
    )


def run_report(job):
    from .views import render_report

    job.refresh_from_db()
    if job.expires_at <= timezone.now():
        job.status = "expired"
        job.payload = None
        job.save()
        return job
    if not authorized(job, job.requested_by):
        job.status = "failed"
        job.error = "Requester or employee access changed before report generation."
        job.finished_at = timezone.now()
        job.save()
        return job
    job.status = "running"
    job.started_at = timezone.now()
    job.save()
    try:
        response, snapshot_ids = render_report(job.employee, job.format)
        payload = response.content
        if len(payload) > getattr(settings, "REPORT_MAX_BYTES", 2 * 1024 * 1024):
            raise ValueError("Report exceeds bounded artifact size")
        job.payload = payload
        job.snapshot_ids = snapshot_ids
        job.status = "succeeded"
        job.error = ""
        # Recheck after rendering too; configuration changes can occur mid-generation.
        job.finished_at = timezone.now()
        job.save()
        job.refresh_from_db()
        if not downloadable(job, job.requested_by):
            job.payload = None
            job.status = "failed"
            job.error = "Authorization or source provenance changed during generation."
            job.save()
        audit(
            job.requested_by,
            "generate_report",
            "ReportJob",
            job.id,
            {"status": job.status, "snapshot_ids": snapshot_ids},
        )
    except Exception as exc:
        job.payload = None
        job.status = "failed"
        job.error = f"Report generation failed ({type(exc).__name__}); reduce the report window or inspect local worker configuration."
        job.finished_at = timezone.now()
        job.save()
    return job
