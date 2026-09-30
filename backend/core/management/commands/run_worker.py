import time
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from core.models import SyncRun, ReportJob
from core.sync import run_sync
from core.reporting import run_report, expire_reports


class Command(BaseCommand):
    help = "Process bounded local sync and report jobs. PostgreSQL supports concurrent workers; use one worker with SQLite."

    def add_arguments(self, p):
        p.add_argument(
            "--once",
            action="store_true",
            help="Process at most one sync and one report job, then exit.",
        )
        p.add_argument("--poll", type=float, default=3)

    def handle(self, *args, **opts):
        while True:
            expire_reports()
            with transaction.atomic():
                SyncRun.objects.filter(
                    status="running", started_at__lt=timezone.now() - timedelta(hours=2)
                ).update(status="queued")
                ReportJob.objects.filter(
                    status="running",
                    started_at__lt=timezone.now() - timedelta(hours=2),
                    expires_at__gt=timezone.now(),
                ).update(status="queued", payload=None)
                run = (
                    SyncRun.objects.select_for_update(skip_locked=True)
                    .filter(status="queued")
                    .order_by("id")
                    .first()
                )
                if run:
                    run.status = "running"
                    run.started_at = timezone.now()
                    run.save()
                report = (
                    ReportJob.objects.select_for_update(skip_locked=True)
                    .filter(status="queued")
                    .order_by("id")
                    .first()
                )
                if report:
                    report.status = "running"
                    report.started_at = timezone.now()
                    report.save()
            if run:
                run_sync(run)
                self.stdout.write(f"Sync job {run.id}: {run.status}")
            if report:
                run_report(report)
                self.stdout.write(f"Report job {report.id}: {report.status}")
            if opts["once"]:
                break
            if not run and not report:
                time.sleep(max(0.2, opts["poll"]))
