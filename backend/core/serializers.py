from rest_framework import serializers
from .models import *
from .crypto import encrypt
from .permissions import employee_ids, role


class ScopedSerializer(serializers.ModelSerializer):
    def validate(self, attrs):
        import math

        for key, value in attrs.items():
            if isinstance(value, float) and not math.isfinite(value):
                raise serializers.ValidationError({key: "A finite numeric value is required."})
        request = self.context.get("request")
        if not request:
            return attrs
        allowed = employee_ids(request.user)
        for key in ["employee", "manager", "defect_employee"]:
            related = attrs.get(key)
            if related and related.id not in allowed and role(request.user) != "system_admin":
                raise serializers.ValidationError(
                    {key: "Employee is outside your authorized scope."}
                )
        contribution = attrs.get("contribution")
        employee = attrs.get("employee", getattr(self.instance, "employee", None))
        if contribution and (
            contribution.employee_id not in allowed
            or not employee
            or contribution.employee_id != employee.id
        ):
            raise serializers.ValidationError(
                {"contribution": "Contribution must belong to the selected authorized employee."}
            )
        goal = attrs.get("goal")
        if goal and (
            goal.employee_id not in allowed or not employee or goal.employee_id != employee.id
        ):
            raise serializers.ValidationError(
                {"goal": "Goal must belong to the selected authorized employee."}
            )
        work_item = attrs.get("work_item")
        if (
            work_item
            and role(request.user) not in ["system_admin", "reviewer"]
            and work_item.created_by_id != request.user.id
            and not work_item.contributions.filter(employee_id__in=allowed).exists()
        ):
            raise serializers.ValidationError(
                {"work_item": "Work item is outside your authorized scope."}
            )
        if attrs.get("source_record") and role(request.user) not in [
            "system_admin",
            "integration_admin",
        ]:
            raise serializers.ValidationError(
                {"source_record": "Source observations can only be linked by administrators."}
            )
        previous = attrs.get("previous")
        if previous and (not employee or previous.employee_id != employee.id):
            raise serializers.ValidationError(
                {"previous": "Prior assessment must belong to this employee."}
            )
        if self.Meta.model == WorkItem and attrs.get("defect_employee"):
            if (
                not self.instance
                or not self.instance.contributions.filter(
                    employee=attrs["defect_employee"]
                ).exists()
            ):
                raise serializers.ValidationError(
                    {
                        "defect_employee": "Defect attribution requires an existing documented contributor."
                    }
                )
        if self.Meta.model == Employee:
            manager = attrs.get("manager")
            seen = {self.instance.id} if self.instance else set()
            while manager:
                if manager.id in seen:
                    raise serializers.ValidationError(
                        {"manager": "Reporting relationships cannot form a cycle."}
                    )
                seen.add(manager.id)
                manager = manager.manager
        if self.Meta.model == Skill and "candidate_rules" in attrs:
            rules = attrs["candidate_rules"]
            if (
                not isinstance(rules, dict)
                or set(rules) - {"labels", "work_categories", "languages", "training"}
                or any(
                    not isinstance(v, list) or any(not isinstance(i, str) for i in v)
                    for v in rules.values()
                )
            ):
                raise serializers.ValidationError(
                    {
                        "candidate_rules": "Use declarative string lists for labels, work_categories, languages, or training."
                    }
                )
        if self.Meta.model == Membership:
            start = attrs.get("started_on", getattr(self.instance, "started_on", None))
            end = attrs.get("ended_on", getattr(self.instance, "ended_on", None))
            if start and end and end < start:
                raise serializers.ValidationError("Membership end must follow start.")
        return attrs


class EmployeeSerializer(ScopedSerializer):
    role_name = serializers.CharField(source="role.name", read_only=True, default="")
    team_name = serializers.CharField(source="team.name", read_only=True, default="")

    class Meta:
        model = Employee
        fields = "__all__"
        read_only_fields = ["created_at", "user"]


class SourceSerializer(ScopedSerializer):
    credentials = serializers.JSONField(write_only=True, required=False)
    has_credentials = serializers.SerializerMethodField()

    def get_has_credentials(self, obj):
        return bool(obj.encrypted_credentials)

    class Meta:
        model = SourceSystem
        exclude = ["encrypted_credentials"]
        read_only_fields = ["last_success_at", "cursor", "created_at", "configuration_revision"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        deployment = attrs.get("deployment", getattr(self.instance, "deployment", None))
        if (kind == "fixture") != (deployment == "fixture"):
            raise serializers.ValidationError("Fixture kind and deployment must be paired.")
        if kind != "fixture" and not attrs.get("base_url", getattr(self.instance, "base_url", "")):
            raise serializers.ValidationError({"base_url": "An explicit endpoint is required."})
        for field in ["scopes", "fields"]:
            if field in attrs and (
                not isinstance(attrs[field], list)
                or any(not isinstance(x, str) for x in attrs[field])
            ):
                raise serializers.ValidationError({field: "Expected a list of strings."})
        config = attrs.get("config", {})
        if not isinstance(config, dict):
            raise serializers.ValidationError({"config": "Expected an object."})
        sensitive = {
            "token",
            "password",
            "secret",
            "authorization",
            "credentials",
            "access_token",
            "refresh_token",
        }

        def has_secret(value):
            return (
                isinstance(value, dict)
                and any(str(k).lower() in sensitive or has_secret(v) for k, v in value.items())
                or isinstance(value, list)
                and any(has_secret(v) for v in value)
            )

        workflow = config.get("workflow", {})
        if (
            not isinstance(workflow, dict)
            or set(workflow) - {"active", "blocked", "done"}
            or any(
                not isinstance(v, list) or any(not isinstance(x, str) for x in v)
                for v in workflow.values()
            )
        ):
            raise serializers.ValidationError(
                {"config": "workflow must contain active, blocked, and done string lists."}
            )
        if has_secret(config):
            raise serializers.ValidationError(
                {"config": "Save secrets only through the credentials field."}
            )
        return attrs

    def create(self, data):
        credentials = data.pop("credentials", None)
        if credentials is not None:
            try:
                data["encrypted_credentials"] = encrypt(credentials)
            except Exception:
                raise serializers.ValidationError(
                    {"credentials": "The server encryption key is not configured correctly."}
                )
        return super().create(data)

    def update(self, instance, data):
        credentials = data.pop("credentials", None)
        if credentials is not None:
            try:
                data["encrypted_credentials"] = encrypt(credentials)
            except Exception:
                raise serializers.ValidationError(
                    {"credentials": "The server encryption key is not configured correctly."}
                )
        return super().update(instance, data)


class SnapshotSerializer(ScopedSerializer):
    metric_key = serializers.CharField(source="definition.key", read_only=True)
    metric_name = serializers.CharField(source="definition.name", read_only=True)
    metric_version = serializers.IntegerField(source="definition.version", read_only=True)

    class Meta:
        model = MetricSnapshot
        fields = "__all__"


READONLY = {
    Contribution: ["verified", "reviewer", "created_at", "origin", "source_record"],
    Outcome: ["verified", "reviewer"],
    Assessment: ["reviewer", "created_at"],
    CorrectionRequest: ["status", "review_note", "reviewed_by", "reviewed_at", "created_at"],
    Review: ["reviewer", "created_at"],
    IdentityMapping: ["employee", "status", "candidates", "resolved_by"],
    WorkItem: [
        "created_by",
        "source_record",
        "original_due_date",
        "scope_changes",
        "agreed_commitment",
        "commitment_approved_by",
        "flow_complete",
        "quality_reviewed_by",
        "quality_reviewed_at",
    ],
}


class ReportJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportJob
        exclude = ["payload"]


def serializer_for(model):
    if model == ReportJob:
        return ReportJobSerializer
    if model == Employee:
        return EmployeeSerializer
    if model == SourceSystem:
        return SourceSerializer
    if model == MetricSnapshot:
        return SnapshotSerializer
    meta = type(
        "Meta",
        (),
        {"model": model, "fields": "__all__", "read_only_fields": READONLY.get(model, [])},
    )
    return type(model.__name__ + "Serializer", (ScopedSerializer,), {"Meta": meta})
