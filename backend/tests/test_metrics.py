from datetime import timedelta
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from core.models import *
from core.metrics import calculate


class MetricsTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.now = timezone.now()
        self.reviewer = get_user_model().objects.create_user("reviewer")
        self.role = Role.objects.create(name="Engineer")
        self.employee = Employee.objects.create(
            stable_id="E1", name="Person One", email="one@example.test", role=self.role
        )

    def item(self, offset=40, late=False, employee=None, **extra):
        due = self.today - timedelta(days=offset)
        complete = self.now - timedelta(days=offset - (1 if late else -1))
        fields = {
            "title": "Agreed shared work",
            "agreed_commitment": True,
            "commitment_approved_by": self.reviewer,
            "due_date": due,
            "original_due_date": due,
            "completed_at": complete,
            "started_at": complete - timedelta(days=5),
            "accepted": True,
            "quality_reviewed_by": self.reviewer,
        }
        fields.update(extra)
        item = WorkItem.objects.create(**fields)
        Contribution.objects.create(
            employee=employee or self.employee,
            work_item=item,
            title=item.title,
            occurred_on=complete.date(),
            origin="assessed",
            verified=True,
            reviewer=self.reviewer,
        )
        return item

    def results(self, employee=None):
        return {s.definition.key: s for s in calculate(employee or self.employee)}

    def test_missing_data_never_zero(self):
        result = self.results()
        self.assertEqual(len(result), 7)
        self.assertIsNone(result["delivery"].value)
        self.assertEqual(result["delivery"].details["denominator"], 0)
        self.assertIsNone(result["alignment"].value)
        self.assertEqual(result["alignment"].status, "insufficient_evidence")

    def test_on_time_formula_and_mature_quality(self):
        self.item()
        self.item(45)
        self.item(50, late=True)
        self.item(5, accepted=False)
        result = self.results()
        self.assertEqual(result["delivery"].value, 75.0)
        self.assertEqual(result["quality"].value, 100.0)
        self.assertEqual(result["quality"].details["sample_size"], 3)
        self.assertEqual(len(result["quality"].details["exclusions"]), 1)

    def test_unapproved_import_does_not_become_commitment(self):
        for _ in range(3):
            self.item(agreed_commitment=False)
        result = self.results()["delivery"]
        self.assertIsNone(result.value)
        self.assertEqual(result.details["sample_size"], 0)

    def test_shared_work_available_to_both_verified_contributors(self):
        other = Employee.objects.create(
            stable_id="E2", name="Second", email="second@example.test", role=self.role
        )
        for _ in range(3):
            item = self.item()
            Contribution.objects.create(
                employee=other,
                work_item=item,
                title="Pairing contribution",
                share=0.4,
                kind="pairing",
                occurred_on=self.today - timedelta(days=40),
                verified=True,
                reviewer=self.reviewer,
            )
        self.assertEqual(self.results(other)["delivery"].value, 100)
        self.assertEqual(
            self.results()["delivery"].details["inputs"][0]["contributions"][1]["share"], 0.4
        )

    def test_unverified_claim_does_not_borrow_other_person_verification(self):
        other = Employee.objects.create(stable_id="E2", name="Second", email="second@example.test")
        for _ in range(3):
            item = self.item(employee=other)
            Contribution.objects.create(
                employee=self.employee,
                work_item=item,
                title="Unverified claim",
                occurred_on=self.today,
            )
        self.assertIsNone(self.results()["delivery"].value)

    def test_categories_never_combined_for_flow(self):
        for _ in range(3):
            self.item(category="feature")
        self.item(category="maintenance")
        flow = self.results()["flow"]
        self.assertIsNone(flow.value)
        self.assertEqual(
            {x["category"]: x["status"] for x in flow.details["groups"]},
            {"feature": "available", "maintenance": "insufficient_evidence"},
        )

    def test_incomplete_changelog_suppresses_flow(self):
        for _ in range(3):
            self.item(flow_complete=False)
        self.assertEqual(self.results()["flow"].status, "insufficient_evidence")

    def test_historical_snapshot_copies_inputs_and_versions(self):
        for _ in range(3):
            self.item()
        old = self.results()["delivery"]
        original = old.details
        WorkItem.objects.update(due_date=self.today - timedelta(days=70))
        with override_settings(METRIC_MIN_SAMPLE=4):
            new = self.results()["delivery"]
        old.refresh_from_db()
        self.assertEqual(old.details, original)
        self.assertNotEqual(old.definition_id, new.definition_id)
        self.assertEqual(old.value, 100)

    def test_alignment_weighted_verified_fresh_assessments(self):
        roadmap = Roadmap.objects.create(
            name="Explicit priorities",
            target_date=self.today + timedelta(days=365),
            target_role=self.role,
        )
        for name, level, required, weight in [("Python", 2, 4, 3), ("Design", 4, 4, 1)]:
            skill = Skill.objects.create(name=name)
            Requirement.objects.create(
                roadmap=roadmap, skill=skill, required_level=required, weight=weight
            )
            Assessment.objects.create(
                employee=self.employee,
                skill=skill,
                level=level,
                kind="verified",
                assessed_on=self.today,
                evidence_url="https://example.test/evidence",
                reviewer=self.reviewer,
            )
        result = self.results()["alignment"]
        self.assertEqual(result.value, 62.5)
        self.assertEqual(result.details["coverage"], 100)

    def test_missing_or_stale_skill_suppresses_roadmap_score(self):
        skill = Skill.objects.create(name="Python")
        roadmap = Roadmap.objects.create(name="R", target_date=self.today, target_role=self.role)
        Requirement.objects.create(roadmap=roadmap, skill=skill, required_level=3)
        Assessment.objects.create(
            employee=self.employee,
            skill=skill,
            level=4,
            kind="verified",
            assessed_on=self.today - timedelta(days=200),
            reviewer=self.reviewer,
        )
        result = self.results()["alignment"]
        self.assertIsNone(result.value)
        self.assertEqual(result.details["coverage"], 0)

    def test_candidate_skill_rules_do_not_establish_proficiency(self):
        source = SourceSystem.objects.create(name="Fixture", kind="fixture", deployment="fixture")
        record = SourceRecord.objects.create(
            source=source,
            external_id="1",
            kind="work_item",
            title="Evidence",
            data={"labels": ["python"]},
        )
        Contribution.objects.create(
            employee=self.employee,
            source_record=record,
            title="Observed work",
            occurred_on=self.today,
            origin="observed",
        )
        Skill.objects.create(name="Python", candidate_rules={"labels": ["python"]})
        result = self.results()["skills"]
        self.assertEqual(result.details["verified_skill_count"], 0)
        self.assertEqual(len(result.details["candidate_evidence"]), 1)

    def test_shared_work_defect_not_automatically_attributed_to_everyone(self):
        other = Employee.objects.create(stable_id="E2", name="Other", email="other@example.test")
        for _ in range(3):
            item = self.item(
                reviewed_defect=True,
                defect_employee=other,
                quality_evidence_url="https://example.test/review",
            )
            Contribution.objects.create(
                employee=other,
                work_item=item,
                title="Shared contribution",
                occurred_on=self.today - timedelta(days=40),
                verified=True,
                reviewer=self.reviewer,
            )
        own = self.results()["quality"]
        others = self.results(other)["quality"]
        self.assertEqual(own.details["indicators"]["reviewed_defect"]["observed"], 0)
        self.assertEqual(others.details["indicators"]["reviewed_defect"]["yes"], 3)
