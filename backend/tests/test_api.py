from datetime import timedelta
from django.test import TestCase, override_settings, Client
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from core.models import *
from core.metrics import calculate


@override_settings(DEBUG=True, SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False)
class APITests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin = User.objects.create_superuser("admin", password="Strong-demo-test-2026!")
        self.manager_user = User.objects.create_user("manager", password="Strong-demo-test-2026!")
        self.user = User.objects.create_user("employee", password="Strong-demo-test-2026!")
        self.manager = Employee.objects.create(
            user=self.manager_user,
            stable_id="M",
            name="Manager",
            email="manager@example.test",
            access_role="manager",
        )
        self.employee = Employee.objects.create(
            user=self.user,
            stable_id="E",
            name="Employee",
            email="employee@example.test",
            manager=self.manager,
        )
        self.other = Employee.objects.create(
            stable_id="O", name="Outside scope", email="outside@example.test"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_scope_list_detail_and_export(self):
        self.assertEqual(
            [x["id"] for x in self.client.get("/api/employees/").json()], [self.employee.id]
        )
        self.assertEqual(self.client.get(f"/api/employees/{self.other.id}/").status_code, 404)
        self.assertEqual(
            self.client.get(
                f"/api/reports/export/?employee={self.other.id}&format=csv"
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(
                f"/api/reports/export/?employee={self.employee.id}&format=csv"
            ).status_code,
            200,
        )

    def test_manager_only_reporting_scope(self):
        self.client.force_authenticate(self.manager_user)
        self.assertEqual(
            set(x["id"] for x in self.client.get("/api/employees/").json()),
            {self.manager.id, self.employee.id},
        )
        self.assertEqual(
            self.client.get(f"/api/employees/{self.other.id}/metrics/").status_code, 404
        )

    def test_nonadmin_cannot_escalate_role(self):
        self.assertEqual(
            self.client.patch(
                f"/api/employees/{self.employee.id}/",
                {"access_role": "system_admin"},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post("/api/roles/", {"name": "Unauthorized"}, format="json").status_code,
            403,
        )

    def test_correction_foreign_key_manipulation_denied(self):
        other_evidence = Contribution.objects.create(
            employee=self.other, title="Private evidence", occurred_on=timezone.localdate()
        )
        response = self.client.post(
            "/api/corrections/",
            {
                "employee": self.employee.id,
                "contribution": other_evidence.id,
                "reason": "Fake",
                "requested_context": "Unauthorized",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CorrectionRequest.objects.count(), 0)

    def test_employee_workflow_and_immutable_approved_correction(self):
        result = self.client.post(
            "/api/contributions/",
            {
                "employee": self.employee.id,
                "title": "Mentored a peer",
                "kind": "mentoring",
                "occurred_on": str(timezone.localdate()),
                "evidence_url": "https://example.test/evidence",
                "context": "Original",
                "verified": True,
            },
            format="json",
        )
        self.assertEqual(result.status_code, 201)
        contribution = Contribution.objects.get(id=result.json()["id"])
        self.assertFalse(contribution.verified)
        result = self.client.post(
            "/api/corrections/",
            {
                "employee": self.employee.id,
                "contribution": contribution.id,
                "reason": "Missing shared context",
                "requested_context": "Shared contribution",
            },
            format="json",
        )
        self.assertEqual(result.status_code, 201)
        correction_id = result.json()["id"]
        self.client.force_authenticate(self.manager_user)
        response = self.client.post(
            f"/api/corrections/{correction_id}/review/",
            {"decision": "approved", "review_note": "Reviewed source evidence"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        contribution.refresh_from_db()
        self.assertEqual(contribution.context, "Original")
        self.assertEqual(Approval.objects.get().after, {"context": "Shared contribution"})
        self.assertEqual(
            self.client.post(
                f"/api/corrections/{correction_id}/review/", {"decision": "approved"}, format="json"
            ).status_code,
            400,
        )

    def test_verification_creates_new_assessment(self):
        skill = Skill.objects.create(name="Python")
        a = Assessment.objects.create(
            employee=self.employee,
            skill=skill,
            level=3,
            assessed_on=timezone.localdate(),
            evidence_url="https://example.test/evidence",
        )
        self.client.force_authenticate(self.manager_user)
        response = self.client.post(f"/api/assessments/{a.id}/verify/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        a.refresh_from_db()
        self.assertEqual(a.kind, "self_declared")
        self.assertEqual(Assessment.objects.get(previous=a).kind, "verified")

    def test_employee_cannot_self_verify(self):
        contribution = Contribution.objects.create(
            employee=self.employee,
            title="Claim",
            occurred_on=timezone.localdate(),
            evidence_url="https://example.test/e",
        )
        self.assertEqual(
            self.client.post(
                f"/api/contributions/{contribution.id}/verify/", {}, format="json"
            ).status_code,
            403,
        )

    def test_auth_csrf_is_required_for_login_and_mutation(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(
            client.post(
                "/api/auth/login/",
                {"username": "employee", "password": "Strong-demo-test-2026!"},
                content_type="application/json",
            ).status_code,
            403,
        )
        token = client.get("/api/auth/session/").json()["csrfToken"]
        result = client.post(
            "/api/auth/login/",
            {"username": "employee", "password": "Strong-demo-test-2026!"},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(
            client.post("/api/contributions/", {}, content_type="application/json").status_code, 403
        )

    def test_metrics_calculate_and_authorized_pdf(self):
        response = self.client.post(
            f"/api/employees/{self.employee.id}/calculate/", {}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 7)
        result = self.client.get(f"/api/reports/export/?employee={self.employee.id}&format=pdf")
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.content.startswith(b"%PDF"))

    def test_roadmap_rejects_other_role(self):
        role = Role.objects.create(name="Different function")
        roadmap = Roadmap.objects.create(
            name="Other", target_role=role, target_date=timezone.localdate()
        )
        result = self.client.post(
            f"/api/employees/{self.employee.id}/calculate/", {"roadmap": roadmap.id}, format="json"
        )
        self.assertEqual(result.status_code, 400)

    def test_csv_injection_escaped(self):
        self.employee.name = "=DANGEROUS()"
        self.employee.save()
        calculate(self.employee)
        result = self.client.get(f"/api/reports/export/?employee={self.employee.id}&format=csv")
        self.assertIn(b"'=DANGEROUS()", result.content)

    def test_csv_import_atomic_idempotent_and_membership_history(self):
        self.client.force_authenticate(self.admin)
        first = Team.objects.create(name="First")
        second = Team.objects.create(name="Second")
        self.employee.team = first
        self.employee.save()
        Membership.objects.create(
            employee=self.employee, team=first, started_on=timezone.localdate() - timedelta(days=10)
        )
        result = self.client.post(
            "/api/csv-import/",
            {
                "kind": "employees",
                "content": f"stable_id,name,email,team\nE,Employee,employee@example.test,{second.id}",
            },
            format="json",
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(
            Membership.objects.filter(employee=self.employee, ended_on__isnull=True).get().team,
            second,
        )
        csv = f"employee,title,kind,occurred_on,evidence_url\nE,History,delivery,{timezone.localdate()},https://example.test/e"
        for _ in range(2):
            self.assertEqual(
                self.client.post(
                    "/api/csv-import/",
                    {"kind": "historical_records", "content": csv},
                    format="json",
                ).status_code,
                200,
            )
        self.assertEqual(Contribution.objects.filter(title="History").count(), 1)
        count = Skill.objects.count()
        result = self.client.post(
            "/api/csv-import/",
            {"kind": "skills", "content": "name,category\nGood,Engineering\n,Engineering"},
            format="json",
        )
        self.assertEqual(result.status_code, 400)
        self.assertEqual(Skill.objects.count(), count)

    def test_offboard_disables_login_and_account_provisioning(self):
        self.client.force_authenticate(self.admin)
        result = self.client.post(
            f"/api/employees/{self.other.id}/account/",
            {"username": "new-person", "password": "Strong-new-person-2026!"},
            format="json",
        )
        self.assertEqual(result.status_code, 200)
        result = self.client.post(f"/api/employees/{self.employee.id}/offboard/", {}, format="json")
        self.assertEqual(result.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_retention_removes_derived_data(self):
        source = SourceSystem.objects.create(
            name="Fixture", kind="fixture", deployment="fixture", retention_days=30
        )
        record = SourceRecord.objects.create(
            source=source,
            external_id="old",
            kind="work_item",
            title="Old",
            updated_at=timezone.now() - timedelta(days=60),
        )
        Contribution.objects.create(
            employee=self.employee,
            source_record=record,
            title="Old",
            occurred_on=timezone.localdate(),
        )
        calculate(self.employee)
        self.client.force_authenticate(self.admin)
        response = self.client.post("/api/retention/", {"confirm": True}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SourceRecord.objects.exists())
        self.assertFalse(Contribution.objects.exists())
        self.assertFalse(MetricSnapshot.objects.exists())

    def test_nonfinite_requirement_rejected(self):
        self.client.force_authenticate(self.admin)
        skill = Skill.objects.create(name="Skill")
        roadmap = Roadmap.objects.create(name="R", target_date=timezone.localdate())
        result = self.client.post(
            "/api/requirements/",
            {"roadmap": roadmap.id, "skill": skill.id, "required_level": 0, "weight": 0},
            format="json",
        )
        self.assertEqual(result.status_code, 400)

    def test_nonfinite_float_string_rejected(self):
        self.client.force_authenticate(self.admin)
        skill = Skill.objects.create(name="Finite")
        roadmap = Roadmap.objects.create(name="Finite roadmap", target_date=timezone.localdate())
        for value in ["NaN", "Infinity", "-Infinity"]:
            response = self.client.post(
                "/api/requirements/",
                {"roadmap": roadmap.id, "skill": skill.id, "required_level": 3, "weight": value},
                format="json",
            )
            self.assertEqual(response.status_code, 400)
        self.assertFalse(Requirement.objects.exists())

    def test_imported_quality_review_explicit_individual_attribution(self):
        source = SourceSystem.objects.create(name="Fixture", kind="fixture", deployment="fixture")
        record = SourceRecord.objects.create(
            source=source, external_id="1", kind="work_item", title="Work"
        )
        item = WorkItem.objects.create(source_record=record, title="Work")
        Contribution.objects.create(
            employee=self.employee,
            work_item=item,
            source_record=record,
            title="Observed",
            occurred_on=timezone.localdate(),
            origin="observed",
        )
        self.client.force_authenticate(self.manager_user)
        response = self.client.post(
            f"/api/work-items/{item.id}/quality/",
            {
                "reviewed_defect": True,
                "defect_employee": self.other.id,
                "evidence_url": "https://example.test/review",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.post(
            f"/api/work-items/{item.id}/quality/",
            {
                "reviewed_defect": True,
                "defect_employee": self.employee.id,
                "accepted": True,
                "evidence_url": "https://example.test/review",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.quality_reviewed_by, self.manager_user)
        self.assertEqual(item.defect_employee, self.employee)

    def test_manager_can_create_manual_work_then_link_first_contributor(self):
        self.client.force_authenticate(self.manager_user)
        result = self.client.post(
            "/api/work-items/", {"title": "New manual work", "category": "feature"}, format="json"
        )
        self.assertEqual(result.status_code, 201)
        item_id = result.json()["id"]
        self.assertEqual(self.client.get(f"/api/work-items/{item_id}/").status_code, 200)
        result = self.client.post(
            "/api/contributions/",
            {
                "employee": self.employee.id,
                "work_item": item_id,
                "title": "First contribution",
                "occurred_on": str(timezone.localdate()),
            },
            format="json",
        )
        self.assertEqual(result.status_code, 201)

    def test_connector_credentials_encrypted_and_never_serialized(self):
        from cryptography.fernet import Fernet
        from core.crypto import decrypt

        self.client.force_authenticate(self.admin)
        with override_settings(FERNET_KEY=Fernet.generate_key().decode()):
            result = self.client.post(
                "/api/sources/",
                {
                    "name": "Secret fixture",
                    "kind": "fixture",
                    "deployment": "fixture",
                    "credentials": {"token": "synthetic-test-token"},
                },
                format="json",
            )
            self.assertEqual(result.status_code, 201)
            self.assertNotIn("credentials", result.json())
            self.assertNotIn("encrypted_credentials", result.json())
            source = SourceSystem.objects.get(id=result.json()["id"])
            self.assertNotIn("synthetic-test-token", source.encrypted_credentials)
            self.assertEqual(decrypt(source.encrypted_credentials)["token"], "synthetic-test-token")

    def test_undated_imports_expire_using_local_ingestion_time(self):
        self.client.force_authenticate(self.admin)
        source = SourceSystem.objects.create(
            name="Undated fixture", kind="fixture", deployment="fixture", retention_days=30
        )
        SourceRecord.objects.create(
            source=source,
            external_id="no-timestamp",
            kind="document",
            title="Undated",
            ingested_at=timezone.now() - timedelta(days=60),
        )
        preview = self.client.get("/api/retention/").json()
        self.assertEqual(preview["sources"][0]["eligible_records"], 1)
        result = self.client.post("/api/retention/", {"confirm": True}, format="json")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["deleted_records"], 1)
