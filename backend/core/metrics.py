"""Deterministic dimensions. Snapshots copy all calculation inputs and configuration."""

from datetime import timedelta
from statistics import median
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import *
from .permissions import record_allowed_for_employee

DEFINITIONS = {
    "delivery": (
        "Delivery reliability",
        "Eligible shared commitments completed by their agreed due date divided by commitments due during the window.",
        "100 × on_time / eligible_due",
        "Assess agreed delivery commitments with capacity and scope context.",
    ),
    "flow": (
        "Delivery flow",
        "Median elapsed workflow days for completed work in the same category; this is not actual hours worked.",
        "median((completed_at - started_at).total_seconds / 86400), grouped by work category",
        "Inspect process flow and impediments within comparable work.",
    ),
    "quality": (
        "Work quality",
        "Reviewed acceptance, reopening, rework, and defect observations on work completed before the quality observation cutoff.",
        "100 × accepted / mature_items_with_known_acceptance",
        "Review mature evidence; missing quality observations remain unknown.",
    ),
    "business": (
        "Business contribution",
        "Progress on agreed goals alongside human-verified outcomes. No financial value is inferred.",
        "mean(goal.progress), with independently reviewed outcome evidence",
        "Discuss progress and documented business impact.",
    ),
    "collaboration": (
        "Collaboration and knowledge sharing",
        "Human-reviewed mentoring, useful review, shared delivery, and documentation evidence. Counts describe evidence coverage, never quality.",
        "count(verified collaboration evidence); no quality score",
        "Inspect evidence and structured assessments of usefulness.",
    ),
    "skills": (
        "Verified skills",
        "Distinct skills with dated reviewer-verified assessments; declarations and candidate evidence are separate.",
        "count(distinct fresh verified skills)",
        "Plan development from rubrics and reviewed evidence.",
    ),
    "alignment": (
        "Alignment with the selected roadmap",
        "Verified proficiency compared with explicitly dated, role-specific company requirements. Unassessed requirements remain unknown.",
        "100 × sum(weight × min(verified_level / required_level, 1)) / sum(weight)",
        "Plan development against a selected roadmap; never predict personal worth or potential.",
    ),
}


def definition_for(key):
    name, description, formula, use = DEFINITIONS[key]
    config = {
        "minimum_sample": settings.METRIC_MIN_SAMPLE,
        "quality_observation_days": settings.QUALITY_OBSERVATION_DAYS,
        "skills_freshness_days": 180,
    }
    latest = MetricDefinition.objects.filter(key=key).order_by("-version").first()
    if latest and latest.config == config and latest.formula == formula:
        return latest
    definition, _ = MetricDefinition.objects.get_or_create(
        key=key,
        version=(latest.version + 1 if latest else 1),
        defaults={
            "name": name,
            "definition": description,
            "formula": formula,
            "intended_use": use,
            "config": config,
        },
    )
    return definition


def item_input(item):
    return {
        "id": item.id,
        "title": item.title,
        "category": item.category,
        "agreed_commitment": item.agreed_commitment,
        "commitment_approved_by": item.commitment_approved_by_id,
        "flow_complete": item.flow_complete,
        "original_due_date": str(item.original_due_date) if item.original_due_date else None,
        "due_date": str(item.due_date) if item.due_date else None,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        "active_days": item.active_days,
        "blocked_days": item.blocked_days,
        "accepted": item.accepted,
        "reopened": item.reopened,
        "rework": item.rework,
        "reviewed_defect": item.reviewed_defect,
        "quality_reviewed_by": item.quality_reviewed_by_id,
        "quality_evidence_url": item.quality_evidence_url,
        "defect_employee_id": item.defect_employee_id,
        "quality_reviewed_at": item.quality_reviewed_at.isoformat()
        if item.quality_reviewed_at
        else None,
        "scope_changes": item.scope_changes,
        "dependencies": item.dependencies,
        "assignment_history": item.assignment_history,
        "evidence_url": item.evidence_url,
        "complexity": item.complexity,
        "contributions": list(item.contributions.values("employee_id", "kind", "share")),
    }


@transaction.atomic
def calculate(employee, start=None, end=None, roadmap_id=None, category=None):
    end = end or timezone.localdate()
    start = start or end - timedelta(days=89)
    contributions = Contribution.objects.filter(
        employee=employee, occurred_on__gte=start, occurred_on__lte=end
    ).select_related("source_record")
    # Unavailable/revoked source observations are never reused in fresh calculations.
    valid_contributions = [
        c
        for c in contributions
        if not c.source_record or record_allowed_for_employee(c.source_record, employee)
    ]
    all_items = (
        WorkItem.objects.filter(
            models.Q(contributions__employee=employee)
            & (models.Q(contributions__verified=True) | models.Q(contributions__origin="observed"))
        )
        .distinct()
        .prefetch_related("contributions")
        .select_related("source_record")
    )
    items = [
        x
        for x in all_items
        if (not category or x.category == category)
        and (not x.source_record or record_allowed_for_employee(x.source_record, employee))
    ]
    source_ids = {x.source_record.source_id for x in items if x.source_record} | {
        x.source_record.source_id for x in valid_contributions if x.source_record
    }
    freshness = [
        {
            "id": s.id,
            "name": s.name,
            "last_success_at": s.last_success_at.isoformat() if s.last_success_at else None,
            "enabled": s.enabled,
            "stale": not s.last_success_at
            or s.last_success_at < timezone.now() - timedelta(days=2),
        }
        for s in SourceSystem.objects.filter(id__in=source_ids)
    ]
    results = []

    def save(key, value, status, extra):
        definition = definition_for(key)
        details = {
            "definition": definition.definition,
            "intended_use": definition.intended_use,
            "formula": definition.formula,
            "metric_version": definition.version,
            "configuration": definition.config,
            "origin": "calculated",
            "sample_size": 0,
            "numerator": None,
            "denominator": None,
            "inputs": [],
            "exclusions": [],
            "missing_data": [],
            "source_freshness": freshness,
            "work_category": category or "grouped comparable categories",
            "employee_context": {
                "capacity": employee.capacity,
                "context": employee.context,
                "role_id": employee.role_id,
                "team_id": employee.team_id,
            },
            "window": {"start": str(start), "end": str(end)},
        }
        record_refs = {x.source_record_id for x in items if x.source_record_id} | {
            x.source_record_id for x in valid_contributions if x.source_record_id
        }
        details["source_records"] = list(
            SourceRecord.objects.filter(id__in=record_refs).values("id", "source_id", "scope")
        )
        details["approved_corrections"] = [
            {
                "id": c.id,
                "contribution_id": c.contribution_id,
                "context": c.requested_context,
                "reviewer_id": c.reviewed_by_id,
                "reviewed_at": c.reviewed_at.isoformat() if c.reviewed_at else None,
            }
            for c in CorrectionRequest.objects.filter(employee=employee, status="approved")
        ]
        details.update(extra)
        results.append(
            MetricSnapshot.objects.create(
                employee=employee,
                definition=definition,
                window_start=start,
                window_end=end,
                value=value,
                status=status,
                details=details,
            )
        )

    minimum = settings.METRIC_MIN_SAMPLE
    due = [x for x in items if x.agreed_commitment and x.due_date and start <= x.due_date <= end]
    on_time = [x for x in due if x.completed_at and x.completed_at.date() <= x.due_date]
    save(
        "delivery",
        round(100 * len(on_time) / len(due), 1) if len(due) >= minimum else None,
        "available" if len(due) >= minimum else "insufficient_evidence",
        {
            "sample_size": len(due),
            "numerator": len(on_time),
            "denominator": len(due),
            "inputs": [item_input(x) for x in due],
            "missing_data": [
                {"id": x.id, "reason": "No approved commitment or agreed due date"}
                for x in items
                if not x.agreed_commitment or not x.due_date
            ],
            "exclusions": [
                {"id": x.id, "reason": "Due date outside selected window"}
                for x in items
                if x.due_date and x not in due
            ],
            "note": "A shared commitment is visible to each documented contributor; shares and assignment history are shown. No individual credit allocation is inferred.",
        },
    )
    finished = [x for x in items if x.completed_at and start <= x.completed_at.date() <= end]
    flow = [
        x for x in finished if x.flow_complete and x.started_at and x.completed_at >= x.started_at
    ]
    groups = []
    for cat in sorted(set(x.category for x in flow)):
        subset = [x for x in flow if x.category == cat]
        times = [round((x.completed_at - x.started_at).total_seconds() / 86400, 2) for x in subset]
        groups.append(
            {
                "category": cat,
                "sample_size": len(times),
                "median_days": median(times) if len(times) >= minimum else None,
                "distribution_days": sorted(times),
                "blocked_days": [x.blocked_days for x in subset],
                "active_days": [x.active_days for x in subset],
                "status": "available" if len(times) >= minimum else "insufficient_evidence",
            }
        )
    save(
        "flow",
        groups[0]["median_days"] if len(groups) == 1 else None,
        "available" if any(g["status"] == "available" for g in groups) else "insufficient_evidence",
        {
            "sample_size": len(flow),
            "groups": groups,
            "inputs": [item_input(x) for x in flow],
            "missing_data": [
                {
                    "id": x.id,
                    "reason": "Missing/invalid workflow start or incomplete transition history",
                }
                for x in finished
                if x not in flow
            ],
            "note": "Days describe workflow elapsed time, not employee working hours. Different categories are not combined.",
        },
    )
    cutoff = end - timedelta(days=settings.QUALITY_OBSERVATION_DAYS)
    mature = [x for x in finished if x.completed_at.date() <= cutoff]

    def current_review(item):
        return not item.source_record or bool(
            item.quality_reviewed_at
            and item.source_record.updated_at
            and item.quality_reviewed_at >= item.source_record.updated_at
        )

    reviewed_mature = [x for x in mature if current_review(x)]
    known = [x for x in reviewed_mature if x.accepted is not None]
    accepted = [x for x in known if x.accepted]
    indicators = {
        field: {
            "yes": sum(getattr(x, field) is True for x in reviewed_mature),
            "observed": sum(getattr(x, field) is not None for x in reviewed_mature),
        }
        for field in ["reopened", "rework"]
    }
    attributed = [
        x
        for x in reviewed_mature
        if x.defect_employee_id == employee.id
        and x.quality_reviewed_by_id
        and x.quality_evidence_url
    ]
    indicators["reviewed_defect"] = {
        "yes": sum(x.reviewed_defect is True for x in attributed),
        "observed": sum(x.reviewed_defect is not None for x in attributed),
    }
    save(
        "quality",
        round(100 * len(accepted) / len(known), 1) if len(known) >= minimum else None,
        "available" if len(known) >= minimum else "insufficient_evidence",
        {
            "sample_size": len(known),
            "numerator": len(accepted),
            "denominator": len(known),
            "observation_cutoff": str(cutoff),
            "indicators": indicators,
            "inputs": [item_input(x) for x in mature],
            "exclusions": [
                {"id": x.id, "reason": "Quality observation window is not mature"}
                for x in finished
                if x not in mature
            ],
            "missing_data": [
                {"id": x.id, "reason": "Acceptance unobserved or source changed after review"}
                for x in mature
                if x.accepted is None or not current_review(x)
            ],
            "note": "Confirmed defect flags require reviewed individual attribution. Team reliability is not attributed to individuals.",
        },
    )
    goals = list(
        Goal.objects.filter(employee=employee).values(
            "id", "title", "progress", "status", "due_date"
        )
    )
    for goal in goals:
        goal["due_date"] = str(goal["due_date"]) if goal["due_date"] else None
    outcomes = list(
        Outcome.objects.filter(
            employee=employee,
            verified=True,
            reviewer__isnull=False,
            occurred_on__range=(start, end),
        ).values("id", "title", "impact", "evidence_url", "reviewer_id", "occurred_on")
    )
    for out in outcomes:
        out["occurred_on"] = str(out["occurred_on"])
    save(
        "business",
        round(sum(x["progress"] for x in goals) / len(goals), 1) if len(goals) >= minimum else None,
        "available" if len(goals) >= minimum else "insufficient_evidence",
        {
            "sample_size": len(goals),
            "goals": goals,
            "verified_outcomes": outcomes,
            "inputs": goals + outcomes,
            "note": "Goal progress is structured human input, not financial value or an employee worth score.",
        },
    )
    collab = [
        c
        for c in valid_contributions
        if c.kind in ["mentoring", "review", "documentation", "pairing", "shared_delivery"]
        and c.verified
        and c.reviewer_id
    ]
    save(
        "collaboration",
        None,
        "available" if len(collab) >= minimum else "insufficient_evidence",
        {
            "origin": "assessed",
            "sample_size": len(collab),
            "evidence_count": len(collab),
            "inputs": [
                {
                    "id": c.id,
                    "title": c.title,
                    "kind": c.kind,
                    "context": c.context,
                    "evidence_url": c.evidence_url,
                    "occurred_on": str(c.occurred_on),
                    "reviewer_id": c.reviewer_id,
                }
                for c in collab
            ],
            "note": "Inspect reviewer-supported usefulness; evidence count is not a quality score.",
        },
    )
    assessments = (
        Assessment.objects.filter(employee=employee, assessed_on__lte=end)
        .select_related("skill")
        .order_by("-assessed_on", "-id")
    )
    latest = {}
    for a in assessments:
        if a.kind == "verified" and a.reviewer_id and a.skill_id not in latest:
            latest[a.skill_id] = a

    def skill_input(a):
        return {
            "id": a.id,
            "skill_id": a.skill_id,
            "skill": a.skill.name,
            "level": a.level,
            "kind": a.kind,
            "assessed_on": str(a.assessed_on),
            "evidence_url": a.evidence_url,
            "reviewer_id": a.reviewer_id,
            "rubric": a.skill.rubric,
        }

    fresh = [a for a in latest.values() if a.assessed_on >= end - timedelta(days=180)]
    candidates = []
    for skill in Skill.objects.all():
        rules = skill.candidate_rules
        for c in valid_contributions:
            data = c.source_record.data if c.source_record else {}
            evidence_sets = {
                "labels": data.get("labels", []),
                "languages": data.get("languages", []),
                "training": data.get("training", []),
                "work_categories": [c.work_item.category] if c.work_item else [],
            }
            matches = [
                key
                for key, values in evidence_sets.items()
                if isinstance(values, list)
                and set(str(v).casefold() for v in values)
                & set(str(v).casefold() for v in rules.get(key, []))
            ]
            if matches:
                candidates.append(
                    {
                        "skill_id": skill.id,
                        "skill": skill.name,
                        "contribution_id": c.id,
                        "matched_rules": matches,
                        "evidence_url": c.evidence_url,
                        "status": "candidate_only",
                        "note": "Candidate evidence does not establish proficiency.",
                    }
                )
    save(
        "skills",
        None,
        "available" if fresh else "insufficient_evidence",
        {
            "origin": "assessed",
            "sample_size": len(fresh),
            "verified_skill_count": len(fresh),
            "candidate_evidence": candidates,
            "inputs": [skill_input(a) for a in fresh],
            "assessments": [skill_input(a) for a in assessments],
            "missing_data": [
                {"skill_id": a.skill_id, "reason": "Verified assessment is stale"}
                for a in latest.values()
                if a not in fresh
            ],
        },
    )
    roadmap = (
        Roadmap.objects.filter(id=roadmap_id).first()
        if roadmap_id
        else Roadmap.objects.filter(active=True)
        .filter(models.Q(target_role=employee.role) | models.Q(target_role__isnull=True))
        .order_by("-target_date")
        .first()
    )
    requirements = list(roadmap.requirements.select_related("skill")) if roadmap else []
    matches = []
    score = 0
    total = sum(r.weight for r in requirements)
    covered = 0
    for r in requirements:
        a = latest.get(r.skill_id)
        is_fresh = bool(a and a.assessed_on >= end - timedelta(days=roadmap.freshness_days))
        if is_fresh:
            covered += 1
            score += r.weight * min(a.level / r.required_level, 1)
        matches.append(
            {
                "skill_id": r.skill_id,
                "skill": r.skill.name,
                "required_level": r.required_level,
                "verified_level": a.level if is_fresh else None,
                "weight": r.weight,
                "gap": max(r.required_level - a.level, 0) if is_fresh else None,
                "assessment": skill_input(a) if a else None,
                "fresh": is_fresh,
                "development_action": r.development_action,
            }
        )
    coverage = covered / len(requirements) if requirements else 0
    # Every required skill needs an assessment before publishing a score; optional relaxed
    # coverage settings expose coverage only, never turn an unknown skill into zero.
    publish = bool(
        requirements
        and covered == len(requirements)
        and coverage >= roadmap.minimum_coverage
        and total > 0
    )
    save(
        "alignment",
        round(100 * score / total, 1) if publish else None,
        "available" if publish else "insufficient_evidence",
        {
            "sample_size": covered,
            "numerator": round(score, 4) if publish else None,
            "denominator": total,
            "coverage": round(coverage * 100, 1),
            "roadmap": {
                "id": roadmap.id,
                "name": roadmap.name,
                "version": roadmap.version,
                "target_date": str(roadmap.target_date),
                "target_role": roadmap.target_role_id,
                "minimum_coverage": roadmap.minimum_coverage,
                "freshness_days": roadmap.freshness_days,
            }
            if roadmap
            else None,
            "requirements": matches,
            "inputs": matches,
            "missing_data": [
                {"skill_id": m["skill_id"], "reason": "Missing or stale verified assessment"}
                for m in matches
                if not m["fresh"]
            ],
            "note": "Alignment with the selected roadmap. Unknown skills suppress the overall result; this is not a prediction of future worth or potential.",
        },
    )
    return results
