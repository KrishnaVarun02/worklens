from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient
from core.models import *
from core.metrics import calculate
from core.reporting import run_report, expire_reports


@override_settings(DEBUG=True)
class ReportJobTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("report-user")
        self.employee = Employee.objects.create(
            user=self.user, stable_id="R", name="Report Employee", email="report@example.test"
        )
        self.outside = Employee.objects.create(
            stable_id="O", name="Outside", email="outside@example.test"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        calculate(self.employee)

    def queue(self, output_format="pdf"):
        response = self.client.post(
            "/api/report-jobs/",
            {"employee": self.employee.id, "format": output_format},
            format="json",
        )
        self.assertEqual(response.status_code, 202, response.data)
        self.assertNotIn("payload", response.data)
        return ReportJob.objects.get(id=response.data["id"])

    def test_worker_generates_then_downloads_authorized_pdf(self):
        job = self.queue()
        call_command("run_worker", once=True)
        job.refresh_from_db()
        self.assertEqual(job.status, "succeeded")
        response = self.client.get(f"/api/report-jobs/{job.id}/download/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))
        listed = self.client.get("/api/report-jobs/").json()
        self.assertNotIn("payload", listed[0])

    def test_employee_cannot_queue_or_download_outside_scope(self):
        response = self.client.post(
            "/api/report-jobs/", {"employee": self.outside.id, "format": "csv"}, format="json"
        )
        self.assertEqual(response.status_code, 403)
        job = self.queue("csv")
        run_report(job)
        other = get_user_model().objects.create_user("outside")
        self.outside.user = other
        self.outside.save()
        self.client.force_authenticate(other)
        self.assertEqual(self.client.get(f"/api/report-jobs/{job.id}/download/").status_code, 404)

    def test_revocation_after_generation_prevents_download(self):
        source = SourceSystem.objects.create(name="Source", kind="fixture", deployment="fixture")
        record = SourceRecord.objects.create(
            source=source, external_id="r", kind="document", title="Sensitive"
        )
        Contribution.objects.create(
            employee=self.employee,
            source_record=record,
            title="Sensitive",
            origin="observed",
            occurred_on=timezone.localdate(),
        )
        calculate(self.employee)
        job = self.queue("csv")
        run_report(job)
        self.assertEqual(job.status, "succeeded")
        record.available = False
        record.save()
        self.assertEqual(self.client.get(f"/api/report-jobs/{job.id}/download/").status_code, 403)

    def test_offboarding_blocks_pending_generation_and_existing_artifact(self):
        first = self.queue()
        run_report(first)
        pending = self.queue()
        self.employee.active = False
        self.employee.save()
        run_report(pending)
        self.assertEqual(pending.status, "failed")
        self.assertIsNone(pending.payload)
        self.assertIn(
            self.client.get(f"/api/report-jobs/{first.id}/download/").status_code, [403, 404]
        )

    def test_expiry_clears_blob_and_prevents_download(self):
        job = self.queue()
        run_report(job)
        job.expires_at = timezone.now() - timedelta(seconds=1)
        job.save()
        expire_reports()
        job.refresh_from_db()
        self.assertEqual(job.status, "expired")
        self.assertIsNone(job.payload)
        self.assertEqual(self.client.get(f"/api/report-jobs/{job.id}/download/").status_code, 403)

    def test_pending_queue_and_artifact_size_bounds(self):
        for _ in range(3):
            self.queue()
        self.assertEqual(
            self.client.post(
                "/api/report-jobs/", {"employee": self.employee.id, "format": "pdf"}, format="json"
            ).status_code,
            400,
        )
        with override_settings(REPORT_MAX_BYTES=8):
            job = ReportJob.objects.first()
            run_report(job)
        self.assertEqual(job.status, "failed")
        self.assertIsNone(job.payload)

    def test_scope_change_during_render_discards_artifact(self):
        from core.views import render_report

        job = self.queue()

        def changed(employee, output_format):
            response = render_report(employee, output_format)
            Employee.objects.filter(id=employee.id).update(active=False)
            return response

        with patch("core.views.render_report", side_effect=changed):
            run_report(job)
        self.assertEqual(job.status, "failed")
        self.assertIsNone(job.payload)
