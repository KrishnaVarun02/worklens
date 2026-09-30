from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


class Role(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    work_categories = models.JSONField(default=list)


class Team(models.Model):
    name = models.CharField(max_length=120, unique=True)
    description = models.TextField(blank=True)


class Employee(models.Model):
    ACCESS = [
        (x, x) for x in ["employee", "manager", "reviewer", "integration_admin", "system_admin"]
    ]
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    stable_id = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=120)
    email = models.EmailField()
    aliases = models.JSONField(default=list)
    role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, blank=True)
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True)
    manager = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True)
    access_role = models.CharField(max_length=30, choices=ACCESS, default="employee")
    active = models.BooleanField(default=True)
    capacity = models.PositiveSmallIntegerField(default=100, validators=[MaxValueValidator(100)])
    context = models.CharField(
        max_length=250,
        blank=True,
        help_text="Capacity/work context only; do not record sensitive absence reasons",
    )
    created_at = models.DateTimeField(auto_now_add=True)


class Membership(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.PROTECT)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, null=True, blank=True)
    started_on = models.DateField()
    ended_on = models.DateField(null=True, blank=True)


class SourceSystem(models.Model):
    name = models.CharField(max_length=120)
    kind = models.CharField(
        max_length=30, choices=[(x, x) for x in ["jira", "bitbucket", "confluence", "fixture"]]
    )
    deployment = models.CharField(
        max_length=30, choices=[(x, x) for x in ["cloud", "data_center", "fixture"]]
    )
    base_url = models.URLField(blank=True)
    scopes = models.JSONField(default=list)
    fields = models.JSONField(default=list)
    config = models.JSONField(default=dict)
    encrypted_credentials = models.TextField(blank=True)
    configuration_revision = models.PositiveIntegerField(default=1)
    enabled = models.BooleanField(default=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    cursor = models.JSONField(default=dict)
    retention_days = models.PositiveIntegerField(
        default=365, validators=[MinValueValidator(1), MaxValueValidator(3650)]
    )
    created_at = models.DateTimeField(auto_now_add=True)


class AccessScope(models.Model):
    source = models.ForeignKey(SourceSystem, on_delete=models.CASCADE)
    scope = models.CharField(max_length=200)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        unique_together = [("source", "scope", "team")]


class IdentityMapping(models.Model):
    source = models.ForeignKey(SourceSystem, on_delete=models.CASCADE)
    account_id = models.CharField(max_length=200)
    email = models.EmailField(blank=True)
    employee = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(
        max_length=20,
        default="unresolved",
        choices=[(x, x) for x in ["unresolved", "ambiguous", "resolved", "service"]],
    )
    candidates = models.JSONField(default=list)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        unique_together = [("source", "account_id")]


class SourceRecord(models.Model):
    ingested_at = models.DateTimeField(default=timezone.now, editable=False)
    source = models.ForeignKey(SourceSystem, on_delete=models.CASCADE)
    external_id = models.CharField(max_length=240)
    kind = models.CharField(max_length=40)
    scope = models.CharField(max_length=200, blank=True)
    title = models.CharField(max_length=400)
    url = models.URLField(max_length=1200, blank=True)
    occurred_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    account_id = models.CharField(max_length=200, blank=True)
    data = models.JSONField(default=dict)
    available = models.BooleanField(default=True)
    deleted = models.BooleanField(default=False)

    class Meta:
        unique_together = [("source", "external_id")]


class SyncRun(models.Model):
    source = models.ForeignKey(SourceSystem, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, default="queued")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    records_processed = models.PositiveIntegerField(default=0)
    cursor = models.JSONField(default=dict)
    error = models.CharField(max_length=500, blank=True)
    diagnostics = models.JSONField(default=dict)
    full_reconcile = models.BooleanField(default=False)
    source_revision = models.PositiveIntegerField(default=1)
    seen_record_ids = models.JSONField(default=list)


class WorkItem(models.Model):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_work_items",
    )
    source_record = models.OneToOneField(
        SourceRecord, on_delete=models.SET_NULL, null=True, blank=True
    )
    title = models.CharField(max_length=300)
    category = models.CharField(max_length=80, default="feature")
    status = models.CharField(max_length=40, default="planned")
    agreed_commitment = models.BooleanField(default=False)
    commitment_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    flow_complete = models.BooleanField(default=True)
    original_due_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    active_days = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0)])
    blocked_days = models.FloatField(
        default=None, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    accepted = models.BooleanField(null=True, blank=True)
    reopened = models.BooleanField(null=True, blank=True)
    rework = models.BooleanField(null=True, blank=True)
    reviewed_defect = models.BooleanField(null=True, blank=True)
    quality_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quality_reviews",
    )
    quality_reviewed_at = models.DateTimeField(null=True, blank=True)
    quality_evidence_url = models.URLField(max_length=1200, blank=True)
    defect_employee = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attributed_defects",
    )
    scope_changes = models.JSONField(default=list)
    dependencies = models.JSONField(default=list)
    assignment_history = models.JSONField(default=list)
    complexity = models.CharField(max_length=40, blank=True)
    evidence_url = models.URLField(max_length=1200, blank=True)


class Contribution(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    work_item = models.ForeignKey(
        WorkItem, on_delete=models.CASCADE, related_name="contributions", null=True, blank=True
    )
    source_record = models.ForeignKey(
        SourceRecord, on_delete=models.SET_NULL, null=True, blank=True
    )
    title = models.CharField(max_length=300)
    kind = models.CharField(max_length=40, default="delivery")
    origin = models.CharField(
        max_length=20,
        choices=[(x, x) for x in ["observed", "claimed", "assessed"]],
        default="claimed",
    )
    share = models.FloatField(
        default=None, null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(1)]
    )
    occurred_on = models.DateField()
    evidence_url = models.URLField(max_length=1200, blank=True)
    context = models.TextField(blank=True)
    verified = models.BooleanField(default=False)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)


class Goal(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    title = models.CharField(max_length=250)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    progress = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(100)])
    status = models.CharField(max_length=30, default="active")


class Outcome(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    goal = models.ForeignKey(Goal, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=250)
    impact = models.TextField()
    evidence_url = models.URLField(max_length=1200)
    verified = models.BooleanField(default=False)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    occurred_on = models.DateField()


class Skill(models.Model):
    name = models.CharField(max_length=120, unique=True)
    category = models.CharField(max_length=100, default="Engineering")
    description = models.TextField(blank=True)
    rubric = models.JSONField(default=dict)
    candidate_rules = models.JSONField(default=dict)


class Assessment(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT)
    level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    kind = models.CharField(
        max_length=30,
        choices=[(x, x) for x in ["self_declared", "evidence_supported", "verified"]],
        default="self_declared",
    )
    evidence_url = models.URLField(max_length=1200, blank=True)
    note = models.TextField(blank=True)
    assessed_on = models.DateField()
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    previous = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Roadmap(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    target_date = models.DateField()
    target_role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, blank=True)
    minimum_coverage = models.FloatField(
        default=1, validators=[MinValueValidator(0.5), MaxValueValidator(1)]
    )
    freshness_days = models.PositiveIntegerField(
        default=180, validators=[MinValueValidator(1), MaxValueValidator(730)]
    )
    active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)


class Requirement(models.Model):
    roadmap = models.ForeignKey(Roadmap, on_delete=models.CASCADE, related_name="requirements")
    skill = models.ForeignKey(Skill, on_delete=models.PROTECT)
    required_level = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    weight = models.FloatField(
        default=1, validators=[MinValueValidator(0.01), MaxValueValidator(100)]
    )
    development_action = models.CharField(max_length=300, blank=True)

    class Meta:
        unique_together = [("roadmap", "skill")]


class MetricDefinition(models.Model):
    key = models.CharField(max_length=80)
    version = models.PositiveIntegerField(default=1)
    name = models.CharField(max_length=160)
    definition = models.TextField()
    intended_use = models.TextField()
    formula = models.TextField()
    config = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("key", "version")]


class MetricSnapshot(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    definition = models.ForeignKey(MetricDefinition, on_delete=models.PROTECT)
    window_start = models.DateField()
    window_end = models.DateField()
    value = models.FloatField(null=True)
    status = models.CharField(max_length=40)
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class Review(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    assessment = models.TextField()
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class CorrectionRequest(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    contribution = models.ForeignKey(Contribution, on_delete=models.SET_NULL, null=True, blank=True)
    requested_context = models.TextField()
    reason = models.TextField()
    status = models.CharField(max_length=20, default="pending")
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Approval(models.Model):
    correction = models.ForeignKey(CorrectionRequest, on_delete=models.CASCADE)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    decision = models.CharField(max_length=20)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=100)
    resource = models.CharField(max_length=120)
    object_id = models.CharField(max_length=100, blank=True)
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class ReportJob(models.Model):
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    format = models.CharField(max_length=3, choices=[("csv", "csv"), ("pdf", "pdf")])
    status = models.CharField(max_length=20, default="queued")
    snapshot_ids = models.JSONField(default=list)
    payload = models.BinaryField(null=True, blank=True)
    error = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
