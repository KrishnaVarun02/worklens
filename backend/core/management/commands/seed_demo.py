from datetime import timedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from core.models import *
from core.metrics import calculate


class Command(BaseCommand):
    help = "Create only synthetic demo records. Safe to rerun; existing user passwords are never reset."

    def add_arguments(self, p):
        p.add_argument("--password")

    @transaction.atomic
    def handle(self, *args, **options):
        password = options["password"] or ("WorkLens-demo-2026!" if settings.DEBUG else None)
        if not password:
            raise CommandError(
                "Pass --password locally, or use DEBUG=1 for the documented demo default."
            )
        User = get_user_model()
        today = timezone.localdate()
        users = {}
        for name in ["admin", "manager", "alex", "reviewer", "integrations"]:
            user, created = User.objects.get_or_create(
                username=name,
                defaults={
                    "email": f"{name}@example.test",
                    "is_staff": name == "admin",
                    "is_superuser": name == "admin",
                },
            )
            if created:
                user.set_password(password)
                user.save()
            users[name] = user
        engineer, _ = Role.objects.get_or_create(
            name="Software Engineer",
            defaults={
                "description": "Build and maintain reliable company capabilities.",
                "work_categories": ["feature", "maintenance", "documentation"],
            },
        )
        lead, _ = Role.objects.get_or_create(
            name="Engineering Manager",
            defaults={"description": "Support delivery, development, and context-aware reviews."},
        )
        product, _ = Team.objects.get_or_create(
            name="Platform", defaults={"description": "Synthetic platform engineering team"}
        )
        experience, _ = Team.objects.get_or_create(
            name="Experience", defaults={"description": "Synthetic product experience team"}
        )
        maya, _ = Employee.objects.get_or_create(
            stable_id="EMP-001",
            defaults={
                "user": users["manager"],
                "name": "Maya Chen",
                "email": "maya@example.test",
                "role": lead,
                "team": product,
                "access_role": "manager",
            },
        )
        alex, _ = Employee.objects.get_or_create(
            stable_id="EMP-002",
            defaults={
                "user": users["alex"],
                "name": "Alex Morgan",
                "email": "alex@example.test",
                "role": engineer,
                "team": product,
                "manager": maya,
                "capacity": 80,
                "context": "Agreed capacity adjusted for mentoring commitments; reasons are not collected.",
            },
        )
        sam, _ = Employee.objects.get_or_create(
            stable_id="EMP-003",
            defaults={
                "name": "Sam Rivera",
                "email": "sam@example.test",
                "role": engineer,
                "team": product,
                "manager": maya,
            },
        )
        jordan, _ = Employee.objects.get_or_create(
            stable_id="EMP-004",
            defaults={
                "name": "Jordan Patel",
                "email": "jordan@example.test",
                "role": engineer,
                "team": experience,
                "context": "Recent role change; evidence window is limited.",
            },
        )
        for username, name, access in [
            ("reviewer", "Riley Brooks", "reviewer"),
            ("integrations", "Casey Reed", "integration_admin"),
        ]:
            Employee.objects.get_or_create(
                stable_id="EMP-" + username.upper(),
                defaults={
                    "user": users[username],
                    "name": name,
                    "email": username + "@example.test",
                    "role": lead,
                    "team": experience,
                    "access_role": access,
                },
            )
        for employee in Employee.objects.all():
            if employee.team:
                Membership.objects.get_or_create(
                    employee=employee,
                    team=employee.team,
                    started_on=today - timedelta(days=180),
                    defaults={"role": employee.role},
                )
        skills = []
        for name, category in [
            ("Python", "Engineering"),
            ("System design", "Engineering"),
            ("Technical mentoring", "Collaboration"),
            ("Platform reliability", "Engineering"),
        ]:
            skill, _ = Skill.objects.get_or_create(
                name=name,
                defaults={
                    "category": category,
                    "description": f"Explicit evidence and human review for {name.lower()}.",
                    "rubric": {
                        "1": "Foundational knowledge with guided practice",
                        "2": "Delivers bounded work with support",
                        "3": "Independent practice in representative contexts",
                        "4": "Guides others and solves complex cases",
                        "5": "Sets standards with sustained reviewed evidence",
                    },
                    "candidate_rules": {"labels": [name.lower().replace(" ", "-")]},
                },
            )
            skills.append(skill)
        for index, skill in enumerate(skills):
            Assessment.objects.get_or_create(
                employee=alex,
                skill=skill,
                kind="verified",
                defaults={
                    "level": [4, 3, 3, 2][index],
                    "evidence_url": f"https://example.test/reviews/alex-{index}",
                    "note": "Synthetic reviewer assessment using the published rubric.",
                    "assessed_on": today - timedelta(days=20 + index),
                    "reviewer": users["manager"],
                },
            )
            Assessment.objects.get_or_create(
                employee=sam,
                skill=skill,
                kind="self_declared",
                defaults={
                    "level": 3,
                    "assessed_on": today - timedelta(days=10),
                    "note": "Self-declared; awaiting evidence and reviewer.",
                },
            )
        roadmap, _ = Roadmap.objects.get_or_create(
            name="Platform foundations · next 12 months",
            defaults={
                "description": "Explicit company priorities: resilient systems, maintainable Python services, and shared engineering knowledge.",
                "target_date": today + timedelta(days=365),
                "target_role": engineer,
            },
        )
        for skill, level, weight in [
            (skills[0], 4, 2),
            (skills[1], 4, 3),
            (skills[2], 3, 1),
            (skills[3], 3, 3),
        ]:
            Requirement.objects.get_or_create(
                roadmap=roadmap,
                skill=skill,
                defaults={
                    "required_level": level,
                    "weight": weight,
                    "development_action": f"Agree a supported practice opportunity and gather reviewed {skill.name.lower()} evidence.",
                },
            )
        for i, (title, offset, late, cat) in enumerate(
            [
                ("Deliver service ownership catalogue", 56, False, "feature"),
                ("Reduce retry storms in ingestion", 48, False, "feature"),
                ("Ship access review workflow", 38, True, "feature"),
                ("Document recovery rehearsal", 15, False, "documentation"),
                ("Support bounded schema migration", 8, False, "maintenance"),
                ("Establish dependency health checks", 3, False, "maintenance"),
            ]
        ):
            due = today - timedelta(days=offset)
            completed = timezone.now() - timedelta(days=offset - (2 if late else -1))
            started = completed - timedelta(days=5 + i)
            item, _ = WorkItem.objects.get_or_create(
                title=title,
                defaults={
                    "category": cat,
                    "status": "done",
                    "agreed_commitment": True,
                    "commitment_approved_by": users["manager"],
                    "original_due_date": due,
                    "due_date": due,
                    "started_at": started,
                    "completed_at": completed,
                    "active_days": 4 + i,
                    "blocked_days": 1,
                    "accepted": True,
                    "reopened": i == 2,
                    "rework": i == 2,
                    "reviewed_defect": False,
                    "quality_reviewed_by": users["manager"],
                    "quality_reviewed_at": timezone.now(),
                    "complexity": "medium",
                    "evidence_url": f"https://example.test/work/PLAT-{100 + i}",
                    "assignment_history": [
                        {"employee_id": alex.id, "role": "shared_delivery"},
                        {"employee_id": sam.id, "role": "pairing"},
                    ],
                },
            )
            Contribution.objects.get_or_create(
                employee=alex,
                work_item=item,
                defaults={
                    "title": title,
                    "kind": "shared_delivery" if i < 3 else "delivery",
                    "origin": "assessed",
                    "share": 0.6 if i < 3 else 1,
                    "occurred_on": completed.date(),
                    "evidence_url": item.evidence_url,
                    "context": "Reviewed contribution: designed implementation, paired on tests, and documented operational decisions.",
                    "verified": True,
                    "reviewer": users["manager"],
                },
            )
            if i < 3:
                Contribution.objects.get_or_create(
                    employee=sam,
                    work_item=item,
                    defaults={
                        "title": "Pairing: " + title,
                        "kind": "pairing",
                        "origin": "assessed",
                        "share": 0.4,
                        "occurred_on": completed.date(),
                        "evidence_url": item.evidence_url,
                        "context": "Reviewed shared delivery: test design and rollout checklist.",
                        "verified": True,
                        "reviewer": users["manager"],
                    },
                )
        for title, kind in [
            ("Mentor on resilient job design", "mentoring"),
            ("Review API authorization boundaries", "review"),
            ("Publish accepted recovery playbook", "documentation"),
        ]:
            Contribution.objects.get_or_create(
                employee=alex,
                title=title,
                defaults={
                    "kind": kind,
                    "origin": "assessed",
                    "occurred_on": today - timedelta(days=12),
                    "evidence_url": "https://example.test/reviews/shared-knowledge",
                    "context": "Reviewer confirmed that this evidence helped the recipient complete a documented task.",
                    "verified": True,
                    "reviewer": users["manager"],
                },
            )
        for title, progress in [
            ("Complete service ownership coverage", 100),
            ("Improve recovery readiness", 75),
            ("Share platform operating knowledge", 60),
        ]:
            goal, _ = Goal.objects.get_or_create(
                employee=alex,
                title=title,
                defaults={
                    "progress": progress,
                    "due_date": today + timedelta(days=30),
                    "description": "Agreed synthetic development and delivery objective.",
                },
            )
        Outcome.objects.get_or_create(
            employee=alex,
            title="Recovery rehearsal completed",
            defaults={
                "goal": goal,
                "impact": "The platform team demonstrated the documented recovery process in a synthetic rehearsal. No financial value is inferred.",
                "evidence_url": "https://example.test/outcomes/recovery",
                "verified": True,
                "reviewer": users["manager"],
                "occurred_on": today - timedelta(days=9),
            },
        )
        contribution = Contribution.objects.filter(employee=alex).first()
        CorrectionRequest.objects.get_or_create(
            employee=alex,
            contribution=contribution,
            reason="Add shared delivery context",
            defaults={
                "requested_context": "Sam and I paired on this work. Sam designed the rollout checks; I implemented the service changes. The evidence should retain both contributions."
            },
        )
        Review.objects.get_or_create(
            employee=alex,
            title="Quarterly development discussion",
            defaults={
                "assessment": "Strong reviewed Python evidence. Prioritize reliability practice and system-design review against the selected roadmap. Capacity and shared work are considered.",
                "reviewer": users["manager"],
            },
        )
        SourceSystem.objects.get_or_create(
            name="Synthetic connector fixture",
            defaults={
                "kind": "fixture",
                "deployment": "fixture",
                "scopes": ["DEMO"],
                "fields": [],
                "config": {},
            },
        )
        for employee in [alex, sam, jordan]:
            calculate(employee)
        self.stdout.write(
            self.style.SUCCESS(
                "Synthetic demo ready: admin, manager, alex, reviewer, integrations. Existing passwords were not changed."
            )
        )
