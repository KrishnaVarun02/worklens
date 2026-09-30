from unittest.mock import patch
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from connectors import AccessRevoked
from core.models import *
from core.sync import run_sync, match_identity, bind_record
from core.metrics import calculate


class SyncTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            "admin", password="Strong-test-password-2026!"
        )
        self.alex = Employee.objects.create(stable_id="A", name="Alex", email="alex@example.test")
        self.sam = Employee.objects.create(stable_id="S", name="Sam", email="sam@example.test")
        self.source = SourceSystem.objects.create(
            name="Fixture", kind="fixture", deployment="fixture", scopes=["DEMO"]
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_fixture_identity_resolution_shared_and_idempotent_sync(self):
        run = run_sync(SyncRun.objects.create(source=self.source))
        self.assertEqual(run.status, "succeeded")
        self.assertEqual(SourceRecord.objects.count(), 5)
        self.assertFalse(Contribution.objects.exists())
        for account, employee in [("demo-alex", self.alex), ("demo-sam", self.sam)]:
            identity = IdentityMapping.objects.get(source=self.source, account_id=account)
            self.assertIsNone(identity.employee_id)
            result = self.client.post(
                f"/api/identities/{identity.id}/resolve/", {"employee": employee.id}, format="json"
            )
            self.assertEqual(result.status_code, 200)
        record = SourceRecord.objects.get(external_id="DEMO-101")
        self.assertEqual(
            set(
                Contribution.objects.filter(source_record=record).values_list(
                    "employee_id", flat=True
                )
            ),
            {self.alex.id, self.sam.id},
        )
        self.assertTrue(
            all(x.share is None for x in Contribution.objects.filter(source_record=record))
        )
        count = Contribution.objects.count()
        run_sync(SyncRun.objects.create(source=self.source))
        self.assertEqual(SourceRecord.objects.count(), 5)
        self.assertEqual(Contribution.objects.count(), count)
        self.assertFalse(WorkItem.objects.filter(agreed_commitment=True).exists())

    def test_ambiguous_email_requires_admin_resolution(self):
        Employee.objects.create(stable_id="A2", name="Alex Duplicate", email="alex@example.test")
        identity = match_identity(self.source, "ambiguous", "alex@example.test")
        self.assertEqual(identity.status, "ambiguous")
        self.assertEqual(len(identity.candidates), 2)
        self.assertIsNone(identity.employee_id)

    def test_interrupted_page_checkpoint_and_retry(self):
        class Broken:
            def iter_pages(self, cursor=None):
                yield {
                    "records": [
                        {
                            "external_id": "one",
                            "kind": "document",
                            "scope": "DEMO",
                            "title": "One",
                            "data": {},
                        }
                    ],
                    "cursor": {"page": 2},
                    "complete": False,
                }
                raise RuntimeError("Sensitive upstream secret should never appear")

        run = SyncRun.objects.create(source=self.source)
        with patch("core.sync.adapter_for", return_value=Broken()):
            run_sync(run)
        self.assertEqual(run.status, "failed")
        self.assertEqual(run.cursor, {"page": 2})
        self.assertNotIn("Sensitive", run.error)

        class Recovered:
            def iter_pages(inner, cursor=None):
                self.assertEqual(cursor, {"page": 2})
                yield {
                    "records": [
                        {
                            "external_id": "one",
                            "kind": "document",
                            "scope": "DEMO",
                            "title": "One",
                            "data": {},
                        },
                        {
                            "external_id": "two",
                            "kind": "document",
                            "scope": "DEMO",
                            "title": "Two",
                            "data": {},
                        },
                    ],
                    "cursor": {},
                    "complete": True,
                }

        with patch("core.sync.adapter_for", return_value=Recovered()):
            run_sync(run)
        self.assertEqual(run.status, "succeeded")
        self.assertEqual(SourceRecord.objects.count(), 2)

    def test_revocation_hides_lists_snapshots_exports(self):
        user = get_user_model().objects.create_user("alex")
        self.alex.user = user
        self.alex.save()
        record = SourceRecord.objects.create(
            source=self.source, external_id="one", kind="document", title="Private title"
        )
        Contribution.objects.create(
            employee=self.alex,
            source_record=record,
            title="Private title",
            occurred_on=timezone.localdate(),
            origin="observed",
        )
        calculate(self.alex)

        class Revoked:
            def iter_pages(self, cursor=None):
                raise AccessRevoked("secret")
                yield

        with patch("core.sync.adapter_for", return_value=Revoked()):
            run = run_sync(SyncRun.objects.create(source=self.source))
        self.assertEqual(run.status, "revoked")
        self.assertFalse(MetricSnapshot.objects.exists())
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get("/api/contributions/").json(), [])
        self.assertNotIn(
            "Private title",
            self.client.get(
                f"/api/reports/export/?employee={self.alex.id}&format=csv"
            ).content.decode(),
        )

    def test_scope_change_quarantines_retained_records(self):
        record = SourceRecord.objects.create(
            source=self.source, external_id="one", kind="document", scope="DEMO", title="Private"
        )
        Contribution.objects.create(
            employee=self.alex,
            source_record=record,
            title="Private",
            occurred_on=timezone.localdate(),
        )
        calculate(self.alex)
        result = self.client.patch(
            f"/api/sources/{self.source.id}/", {"scopes": ["NEW"]}, format="json"
        )
        self.assertEqual(result.status_code, 200)
        record.refresh_from_db()
        self.assertFalse(record.available)
        self.assertFalse(MetricSnapshot.objects.exists())

    def test_full_reconcile_absence_is_unavailable_not_deleted(self):
        stale = SourceRecord.objects.create(
            source=self.source,
            external_id="gone",
            kind="document",
            scope="DEMO",
            title="Previously accessible",
        )
        run = run_sync(SyncRun.objects.create(source=self.source, full_reconcile=True))
        self.assertEqual(run.status, "succeeded")
        stale.refresh_from_db()
        self.assertFalse(stale.available)
        self.assertFalse(stale.deleted)

    def test_purge_requires_disable_and_cleans_all_derived_records(self):
        self.assertEqual(
            self.client.post(
                f"/api/sources/{self.source.id}/purge/", {}, format="json"
            ).status_code,
            400,
        )
        run_sync(SyncRun.objects.create(source=self.source))
        self.source.enabled = False
        self.source.save()
        self.assertEqual(
            self.client.post(
                f"/api/sources/{self.source.id}/purge/", {}, format="json"
            ).status_code,
            200,
        )
        self.assertFalse(SourceRecord.objects.exists())
        self.assertFalse(WorkItem.objects.exists())
        self.assertFalse(IdentityMapping.objects.exists())

    def test_inflight_configuration_change_cannot_reimport_quarantined_fields(self):
        class Changed:
            def iter_pages(inner, cursor=None):
                result = self.client.patch(
                    f"/api/sources/{self.source.id}/", {"fields": ["status"]}, format="json"
                )
                self.assertEqual(result.status_code, 200)
                yield {
                    "records": [
                        {
                            "external_id": "private",
                            "kind": "document",
                            "scope": "DEMO",
                            "title": "No longer allowed",
                            "data": {},
                        }
                    ],
                    "cursor": {},
                    "complete": True,
                }

        with patch("core.sync.adapter_for", return_value=Changed()):
            run = run_sync(SyncRun.objects.create(source=self.source))
        self.assertEqual(run.status, "failed")
        self.assertFalse(SourceRecord.objects.exists())
        self.source.refresh_from_db()
        self.assertEqual(self.source.cursor, {})
        self.assertIsNone(self.source.last_success_at)

    def test_queued_old_configuration_revision_fails_closed(self):
        run = SyncRun.objects.create(source=self.source)
        self.client.patch(f"/api/sources/{self.source.id}/", {"fields": ["status"]}, format="json")
        run.refresh_from_db()
        run_sync(run)
        self.assertEqual(run.status, "failed")
        self.assertFalse(SourceRecord.objects.exists())

    def test_changed_source_content_does_not_reuse_prior_human_verification(self):
        self.source.refresh_from_db()
        run_sync(SyncRun.objects.create(source=self.source))
        mapping = IdentityMapping.objects.get(account_id="demo-alex")
        mapping.status = "resolved"
        mapping.employee = self.alex
        mapping.save()
        record = SourceRecord.objects.get(external_id="DEMO-101")
        bind_record(record)
        contribution = Contribution.objects.get(source_record=record, employee=self.alex)
        contribution.verified = True
        contribution.reviewer = self.admin
        contribution.save()

        class Changed:
            def iter_pages(self, cursor=None):
                yield {
                    "records": [
                        {
                            "external_id": "DEMO-101",
                            "kind": "work_item",
                            "scope": "DEMO",
                            "title": "Changed material evidence",
                            "account_id": "demo-alex",
                            "data": {},
                        }
                    ],
                    "cursor": {},
                    "complete": True,
                }

        with patch("core.sync.adapter_for", return_value=Changed()):
            run_sync(SyncRun.objects.create(source=self.source))
        contribution.refresh_from_db()
        self.assertFalse(contribution.verified)
        self.assertIsNone(contribution.reviewer)
