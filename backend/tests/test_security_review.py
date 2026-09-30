"""Independent authorization/provenance regression review; synthetic records only."""

from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import (
    AccessScope,
    Contribution,
    Employee,
    SourceRecord,
    SourceSystem,
    Team,
    WorkItem,
)
from core.metrics import calculate


@override_settings(
    DEBUG=True, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False, METRIC_MIN_SAMPLE=1
)
class IndependentSecurityReviewTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.user = users.objects.create_user("review-employee")
        self.manager_user = users.objects.create_user("review-manager")
        self.team = Team.objects.create(name="Permitted team")
        self.other_team = Team.objects.create(name="Different team")
        self.manager = Employee.objects.create(
            user=self.manager_user,
            stable_id="RM",
            name="Manager",
            email="manager@example.test",
            access_role="manager",
            team=self.other_team,
        )
        self.employee = Employee.objects.create(
            user=self.user,
            stable_id="RE",
            name="Employee",
            email="employee@example.test",
            team=self.other_team,
            manager=self.manager,
        )
        self.source = SourceSystem.objects.create(
            name="Synthetic private source",
            kind="fixture",
            deployment="fixture",
            scopes=["PRIVATE"],
        )
        self.record = SourceRecord.objects.create(
            source=self.source,
            external_id="private-1",
            scope="PRIVATE",
            kind="work_item",
            title="Sensitive imported title",
            available=True,
        )
        self.item = WorkItem.objects.create(
            source_record=self.record,
            title=self.record.title,
            agreed_commitment=True,
            due_date=timezone.localdate(),
            completed_at=timezone.now() - timedelta(days=1),
            scope_changes=[
                {"from": None, "to": str(timezone.localdate()), "approved_by": self.manager_user.id}
            ],
        )
        self.contribution = Contribution.objects.create(
            employee=self.employee,
            source_record=self.record,
            work_item=self.item,
            title=self.record.title,
            origin="observed",
            occurred_on=timezone.localdate(),
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_employee_cannot_detach_imported_provenance(self):
        response = self.client.patch(
            f"/api/contributions/{self.contribution.id}/",
            {"source_record": None, "work_item": None, "title": "Changed source observation"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.contribution.refresh_from_db()
        self.assertEqual(self.contribution.source_record_id, self.record.id)
        self.assertEqual(self.contribution.title, self.record.title)

    def test_employee_cannot_delete_imported_observation(self):
        response = self.client.delete(f"/api/contributions/{self.contribution.id}/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Contribution.objects.filter(id=self.contribution.id).exists())

    def test_manager_cannot_delete_imported_work_item_and_its_evidence(self):
        self.client.force_authenticate(self.manager_user)
        response = self.client.delete(f"/api/work-items/{self.item.id}/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(WorkItem.objects.filter(id=self.item.id).exists())
        self.assertTrue(Contribution.objects.filter(id=self.contribution.id).exists())

    def test_manager_cannot_delete_manual_work_item_with_verified_evidence(self):
        self.client.force_authenticate(self.manager_user)
        manual = WorkItem.objects.create(title="Shared reviewed evidence")
        evidence = Contribution.objects.create(
            employee=self.employee,
            work_item=manual,
            title="Verified evidence",
            verified=True,
            reviewer=self.manager_user,
            occurred_on=timezone.localdate(),
        )
        response = self.client.delete(f"/api/work-items/{manual.id}/")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Contribution.objects.filter(id=evidence.id).exists())

    def test_manager_cannot_rewrite_other_teams_shared_commitment(self):
        outsider = Employee.objects.create(
            stable_id="OUT",
            name="Other manager's report",
            email="outside@example.test",
            team=self.team,
        )
        Contribution.objects.create(
            employee=outsider,
            source_record=self.record,
            work_item=self.item,
            title="Shared contribution",
            origin="observed",
            occurred_on=timezone.localdate(),
        )
        self.client.force_authenticate(self.manager_user)
        new_due = str(timezone.localdate() + timedelta(days=20))
        response = self.client.post(
            f"/api/work-items/{self.item.id}/commit/",
            {"due_date": new_due, "note": "Change shared commitment"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.item.refresh_from_db()
        self.assertNotEqual(str(self.item.due_date), new_due)

    def test_explicit_source_team_boundary_applies_to_evidence_endpoints(self):
        AccessScope.objects.create(source=self.source, scope="PRIVATE", team=self.team)
        self.assertEqual(self.client.get(f"/api/source-records/{self.record.id}/").status_code, 404)
        self.assertEqual(
            self.client.get(f"/api/contributions/{self.contribution.id}/").status_code, 404
        )
        self.assertEqual(self.client.get(f"/api/work-items/{self.item.id}/").status_code, 404)

    def test_explicit_source_team_boundary_applies_to_calculations(self):
        AccessScope.objects.create(source=self.source, scope="PRIVATE", team=self.team)
        snapshots = calculate(self.employee)
        delivery = next(s for s in snapshots if s.definition.key == "delivery")
        self.assertEqual(delivery.details["sample_size"], 0)
        self.assertEqual(delivery.details["inputs"], [])

    def test_old_snapshot_and_csv_recheck_current_source_audience(self):
        snapshots = calculate(self.employee)
        delivery = next(s for s in snapshots if s.definition.key == "delivery")
        self.assertEqual(delivery.details["sample_size"], 1)
        # The record remains retained; access narrows independently of source availability.
        AccessScope.objects.create(source=self.source, scope="PRIVATE", team=self.team)
        self.assertEqual(self.client.get(f"/api/snapshots/{delivery.id}/").status_code, 404)
        metrics = self.client.get(f"/api/employees/{self.employee.id}/metrics/")
        self.assertEqual(metrics.status_code, 200)
        self.assertNotIn(delivery.id, [row["id"] for row in metrics.json()])
        report = self.client.get(f"/api/reports/export/?employee={self.employee.id}&format=csv")
        self.assertEqual(report.status_code, 200)
        self.assertNotIn(b"Sensitive imported title", report.content)

    def test_approved_commitment_history_cannot_be_erased_by_generic_patch(self):
        self.client.force_authenticate(self.manager_user)
        manual = WorkItem.objects.create(
            title="Manual commitment",
            agreed_commitment=True,
            due_date=timezone.localdate(),
            scope_changes=[
                {"from": None, "to": str(timezone.localdate()), "approved_by": self.manager_user.id}
            ],
        )
        Contribution.objects.create(
            employee=self.employee,
            work_item=manual,
            title="Claim",
            occurred_on=timezone.localdate(),
        )
        response = self.client.patch(
            f"/api/work-items/{manual.id}/", {"scope_changes": []}, format="json"
        )
        self.assertIn(response.status_code, (200, 400, 403))
        manual.refresh_from_db()
        self.assertEqual(len(manual.scope_changes), 1)
