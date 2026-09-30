import csv
import io
from datetime import date, timedelta
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction, connection
from django.http import JsonResponse, HttpResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods
from rest_framework import viewsets, status
from rest_framework.decorators import api_view, action, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError, NotFound
from .models import *
from .permissions import (
    role,
    own_employee,
    employee_ids,
    require_roles,
    audit,
    visible_contributions,
    snapshot_visible,
)
from .serializers import serializer_for, SnapshotSerializer
from .metrics import calculate, definition_for, DEFINITIONS
from .sync import adapter_for, run_sync, bind_record, purge_source, quarantine_records


def user_data(user):
    if not user.is_authenticated:
        return None
    employee = own_employee(user)
    return {
        "id": user.id,
        "username": user.username,
        "role": role(user),
        "employee_id": employee.id if employee else None,
    }


def body(request):
    import json

    try:
        value = json.loads(request.body or b"{}")
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, UnicodeDecodeError):
        raise ValueError("Expected a JSON object")


@require_http_methods(["GET"])
def session(request):
    return JsonResponse({"user": user_data(request.user), "csrfToken": get_token(request)})


@csrf_protect
@require_http_methods(["POST"])
def login_view(request):
    try:
        data = body(request)
    except ValueError:
        return JsonResponse({"detail": "Invalid JSON."}, status=400)
    if not isinstance(data.get("username"), str) or not isinstance(data.get("password"), str):
        return JsonResponse({"detail": "Username and password must be text."}, status=400)
    # Server-side rate limit keyed to remote peer and account. Reverse proxy must not
    # forward untrusted client IP values as REMOTE_ADDR.
    key = "login:" + request.META.get("REMOTE_ADDR", "") + ":" + str(data.get("username", ""))[:150]
    failures = cache.get(key, 0)
    if failures >= 10:
        return JsonResponse({"detail": "Too many login attempts. Try again later."}, status=429)
    user = authenticate(request, username=data.get("username"), password=data.get("password"))
    if not user or not role(user):
        cache.set(key, failures + 1, 300)
        return JsonResponse({"detail": "Invalid username or password."}, status=400)
    cache.delete(key)
    login(request, user)
    audit(user, "login", "session")
    return JsonResponse({"user": user_data(user), "csrfToken": get_token(request)})


@csrf_protect
@require_http_methods(["POST"])
def logout_view(request):
    if request.user.is_authenticated:
        audit(request.user, "logout", "session")
    logout(request)
    return JsonResponse({"user": None, "csrfToken": get_token(request)})


@csrf_protect
@require_http_methods(["GET", "POST"])
def setup(request):
    User = get_user_model()
    needed = not User.objects.filter(is_superuser=True).exists()
    if request.method == "GET":
        return JsonResponse({"needs_setup": needed, "csrfToken": get_token(request)})
    if not needed:
        return JsonResponse({"detail": "Initial setup is already complete."}, status=403)
    try:
        data = body(request)
        username = str(data.get("username", "")).strip()
        password = data.get("password", "")
        if not username or len(username) > 150:
            return JsonResponse({"detail": "A valid username is required."}, status=400)
        validate_password(password, User(username=username))
        with transaction.atomic():
            # Serialize bootstrap on PostgreSQL; the database has no singleton row yet.
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(78149231)")
            if User.objects.filter(is_superuser=True).exists():
                return JsonResponse({"detail": "Initial setup is already complete."}, status=403)
            user = User.objects.create_superuser(
                username=username, password=password, email=data.get("email", "")
            )
        login(request, user)
        audit(user, "initial_setup", "user", user.id)
        return JsonResponse({"user": user_data(user), "csrfToken": get_token(request)}, status=201)
    except (ValueError, DjangoValidationError) as exc:
        return JsonResponse(
            {"detail": getattr(exc, "messages", ["Invalid setup details."])}, status=400
        )


@require_http_methods(["GET"])
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return JsonResponse({"status": "ok"})
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)


class ResourceViewSet(viewsets.ModelViewSet):
    model = None

    def get_serializer_class(self):
        return serializer_for(self.model)

    def get_queryset(self):
        user = self.request.user
        r = role(user)
        ids = employee_ids(user)
        if not r:
            raise PermissionDenied("No active application access.")
        qs = self.model.objects.all().order_by("id")
        if self.model == Employee:
            # Integration admins receive minimal directory information for identity resolution.
            if r != "integration_admin":
                qs = qs.filter(id__in=ids)
        elif self.model in [SourceSystem, SyncRun, IdentityMapping, AccessScope]:
            require_roles(user, "system_admin", "integration_admin")
        elif self.model == AuditEvent:
            require_roles(user, "system_admin")
        elif self.model == SourceRecord:
            if r not in ["system_admin", "integration_admin"]:
                qs = qs.filter(
                    contribution__in=visible_contributions(
                        Contribution.objects.filter(employee_id__in=ids)
                    )
                ).distinct()
        elif self.model == WorkItem:
            if r != "system_admin":
                qs = qs.filter(
                    models.Q(
                        contributions__in=visible_contributions(
                            Contribution.objects.filter(employee_id__in=ids)
                        )
                    )
                    | models.Q(created_by=user)
                ).distinct()
            qs = qs.filter(
                models.Q(source_record__isnull=True)
                | models.Q(source_record__available=True, source_record__deleted=False)
            )
        elif self.model == Approval:
            qs = qs.filter(correction__employee_id__in=ids)
        elif any(f.name == "employee" for f in self.model._meta.fields):
            qs = qs.filter(employee_id__in=ids)
        if self.model == Contribution:
            qs = visible_contributions(qs)
        if self.model == MetricSnapshot:
            qs = qs.filter(
                id__in=[s.id for s in qs.select_related("employee") if snapshot_visible(s)]
            )
        if self.request.query_params.get("employee") and any(
            f.name == "employee" for f in self.model._meta.fields
        ):
            try:
                qs = qs.filter(employee_id=int(self.request.query_params["employee"]))
            except ValueError:
                raise ValidationError({"employee": "Expected a numeric ID."})
        return qs

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        if self.model == Employee and role(request.user) == "integration_admin":
            response.data = [
                {
                    k: v
                    for k, v in row.items()
                    if k in ["id", "stable_id", "name", "email", "active"]
                }
                for row in response.data
            ]
        audit(request.user, "list", self.model.__name__)
        return response

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        if self.model == Employee and role(request.user) == "integration_admin":
            response.data = {
                k: v
                for k, v in response.data.items()
                if k in ["id", "stable_id", "name", "email", "active"]
            }
        audit(request.user, "view", self.model.__name__, kwargs.get("pk", ""))
        return response

    def create(self, request, *args, **kwargs):
        self.check_write()
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self.check_write(self.get_object())
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        self.check_write(self.get_object())
        return super().destroy(request, *args, **kwargs)

    def check_write(self, instance=None):
        r = role(self.request.user)
        if (
            self.model == WorkItem
            and instance
            and r == "manager"
            and instance.contributions.exclude(
                employee_id__in=employee_ids(self.request.user)
            ).exists()
        ):
            raise PermissionDenied(
                "A cross-team reviewer must change work shared with employees outside your reporting scope."
            )
        if self.model == Contribution and instance and instance.source_record_id:
            raise PermissionDenied(
                "Imported observations are immutable; use verification or submit a correction."
            )
        if self.model in [
            MetricDefinition,
            MetricSnapshot,
            AuditEvent,
            SourceRecord,
            SyncRun,
            IdentityMapping,
            Approval,
        ]:
            raise PermissionDenied("This history is read-only; use the documented workflow action.")
        if self.model in [SourceSystem, AccessScope]:
            require_roles(self.request.user, "system_admin", "integration_admin")
        elif self.model in [Employee, Team, Role, Membership, Skill, Roadmap, Requirement]:
            require_roles(self.request.user, "system_admin")
        elif self.model in [WorkItem, Review]:
            require_roles(self.request.user, "system_admin", "manager", "reviewer")
        elif self.model == Assessment and instance:
            raise PermissionDenied(
                "Assessments are append-only. Create a new assessment with a previous reference."
            )
        elif self.model == CorrectionRequest and instance:
            raise PermissionDenied(
                "Correction requests are immutable; submit a new request or use review."
            )
        elif r not in ["system_admin", "manager", "reviewer", "employee"]:
            raise PermissionDenied("This role cannot edit workforce records.")

    def perform_create(self, serializer):
        self.check_write()
        extra = {}
        if self.model in [Contribution, Outcome]:
            extra = {"verified": False, "reviewer": None}
        if self.model == Contribution:
            extra["origin"] = "claimed"
        if self.model == Assessment:
            if serializer.validated_data.get("kind") == "verified":
                raise ValidationError({"kind": "Use the separate verification workflow."})
            extra = {"reviewer": None}
        if self.model == Review:
            extra = {"reviewer": self.request.user}
        if self.model == WorkItem:
            extra["created_by"] = self.request.user
        if self.model == WorkItem and any(
            serializer.validated_data.get(k) is not None
            for k in ["accepted", "reopened", "rework", "reviewed_defect"]
        ):
            if not serializer.validated_data.get("evidence_url"):
                raise ValidationError(
                    {"evidence_url": "Reviewed quality observations require an evidence link."}
                )
            extra.update(quality_reviewed_by=self.request.user, quality_reviewed_at=timezone.now())
        obj = serializer.save(**extra)
        if self.model == AccessScope:
            with transaction.atomic():
                source = SourceSystem.objects.select_for_update().get(id=obj.source_id)
                quarantine_records(SourceRecord.objects.filter(source=source))
                source.configuration_revision += 1
                source.cursor = {}
                source.save(update_fields=["configuration_revision", "cursor"])
        if self.model == Employee and obj.team:
            Membership.objects.create(
                employee=obj, team=obj.team, role=obj.role, started_on=timezone.localdate()
            )
        audit(self.request.user, "create", self.model.__name__, obj.id)

    @transaction.atomic
    def perform_update(self, serializer):
        obj = serializer.instance
        self.check_write(obj)
        if self.model in [Contribution, Outcome] and obj.verified:
            raise PermissionDenied(
                "Verified evidence is immutable. Submit a correction or new evidence."
            )
        if self.model == Contribution and any(
            k in serializer.validated_data and serializer.validated_data[k] != getattr(obj, k)
            for k in ["employee", "work_item"]
        ):
            raise PermissionDenied(
                "Keep contribution ownership/history intact; add a new contribution instead."
            )
        if self.model == WorkItem and any(
            k in self.request.data
            for k in [
                "accepted",
                "reopened",
                "rework",
                "reviewed_defect",
                "defect_employee",
                "quality_evidence_url",
            ]
        ):
            raise PermissionDenied(
                "Use the explicit quality review workflow to change reviewed observations or attribution."
            )
        if self.model == WorkItem and obj.source_record_id:
            raise PermissionDenied("Imported work items are updated through synchronization.")
        if self.model == WorkItem:
            old_due = obj.due_date
            new_due = serializer.validated_data.get("due_date", old_due)
            if old_due != new_due:
                changes = list(obj.scope_changes)
                changes.append(
                    {
                        "from": str(old_due) if old_due else None,
                        "to": str(new_due) if new_due else None,
                        "approved_by": self.request.user.id,
                        "approved_at": timezone.now().isoformat(),
                    }
                )
                serializer.validated_data["scope_changes"] = changes
            serializer.validated_data.pop("original_due_date", None)
        if self.model == WorkItem and any(
            k in serializer.validated_data
            for k in ["accepted", "reopened", "rework", "reviewed_defect"]
        ):
            me = own_employee(self.request.user)
            if me and obj.contributions.filter(employee=me).exists():
                raise PermissionDenied(
                    "An independent authorized reviewer must assess work quality."
                )
            if not serializer.validated_data.get("evidence_url", obj.evidence_url):
                raise ValidationError(
                    {"evidence_url": "Reviewed quality observations require an evidence link."}
                )
            serializer.validated_data.update(
                quality_reviewed_by=self.request.user, quality_reviewed_at=timezone.now()
            )
        if self.model == SourceSystem:
            locked = SourceSystem.objects.select_for_update().get(id=obj.id)
            changed = (
                any(
                    k in serializer.validated_data
                    and serializer.validated_data[k] != getattr(locked, k)
                    for k in ["base_url", "kind", "deployment", "scopes", "fields", "config"]
                )
                or "credentials" in serializer.validated_data
            )
            if changed:
                quarantine_records(SourceRecord.objects.filter(source=obj))
                obj.cursor = {}
                obj.configuration_revision = locked.configuration_revision + 1
        if self.model == AccessScope:
            source_ids = {obj.source_id, serializer.validated_data.get("source", obj.source).id}
            for source in SourceSystem.objects.select_for_update().filter(id__in=source_ids):
                quarantine_records(SourceRecord.objects.filter(source=source))
                source.configuration_revision += 1
                source.cursor = {}
                source.save(update_fields=["configuration_revision", "cursor"])
        old_team = getattr(obj, "team_id", None)
        old_role = getattr(obj, "role_id", None)
        if self.model == Roadmap:
            serializer.validated_data["version"] = obj.version + 1
        obj = serializer.save()
        if self.model == Employee and (old_team != obj.team_id or old_role != obj.role_id):
            MetricSnapshot.objects.filter(employee=obj).delete()
            Membership.objects.filter(employee=obj, ended_on__isnull=True).update(
                ended_on=timezone.localdate()
            )
            if obj.team:
                Membership.objects.create(
                    employee=obj, team=obj.team, role=obj.role, started_on=timezone.localdate()
                )
        if self.model == Requirement:
            Roadmap.objects.filter(id=obj.roadmap_id).update(version=models.F("version") + 1)
        audit(self.request.user, "update", self.model.__name__, obj.id)

    @transaction.atomic
    def perform_destroy(self, instance):
        self.check_write(instance)
        if self.model in [Assessment, CorrectionRequest, Review]:
            raise PermissionDenied("Review history is append-only.")
        if self.model in [Contribution, Outcome] and instance.verified:
            raise PermissionDenied("Verified evidence is immutable; use a correction request.")
        if self.model == WorkItem and (
            instance.source_record_id or instance.contributions.exists()
        ):
            raise PermissionDenied(
                "Work items with evidence cannot be deleted through a generic action; use an authorized retention or source lifecycle workflow."
            )
        if self.model == Employee:
            require_roles(self.request.user, "system_admin")
            if instance.user_id:
                instance.user.is_active = False
                instance.user.save(update_fields=["is_active"])
        if self.model == SourceSystem:
            purge_source(instance)
        if self.model == AccessScope:
            source = SourceSystem.objects.select_for_update().get(id=instance.source_id)
            quarantine_records(SourceRecord.objects.filter(source=source))
            source.configuration_revision += 1
            source.cursor = {}
            source.save(update_fields=["configuration_revision", "cursor"])
        audit(self.request.user, "delete", self.model.__name__, instance.id)
        from django.db.models.deletion import ProtectedError

        try:
            instance.delete()
        except ProtectedError:
            raise ValidationError(
                "This record is referenced by retained history and cannot be deleted."
            )


class EmployeeViewSet(ResourceViewSet):
    model = Employee

    @action(detail=True, methods=["get"])
    def metrics(self, request, pk=None):
        employee = self.get_object()
        if employee.id not in employee_ids(request.user):
            raise PermissionDenied("Metrics are outside your authorized scope.")
        latest = {}
        for snap in (
            MetricSnapshot.objects.filter(employee=employee)
            .select_related("definition")
            .order_by("-created_at", "-id")
        ):
            if snap.definition.key not in latest and snapshot_visible(snap):
                latest[snap.definition.key] = snap
        audit(request.user, "metrics", "Employee", employee.id)
        return Response(SnapshotSerializer(list(latest.values()), many=True).data)

    @action(detail=True, methods=["post"])
    def calculate(self, request, pk=None):
        employee = self.get_object()
        if employee.id not in employee_ids(request.user):
            raise PermissionDenied("Metrics are outside your authorized scope.")
        try:
            start = (
                date.fromisoformat(request.data["window_start"])
                if request.data.get("window_start")
                else None
            )
            end = (
                date.fromisoformat(request.data["window_end"])
                if request.data.get("window_end")
                else None
            )
            if start and end and start > end:
                raise ValueError()
            if end and end > timezone.localdate():
                raise ValueError()
            roadmap_id = int(request.data["roadmap"]) if request.data.get("roadmap") else None
        except (ValueError, TypeError):
            raise ValidationError("Provide a valid date range and numeric roadmap ID.")
        if (
            roadmap_id
            and not Roadmap.objects.filter(id=roadmap_id)
            .filter(models.Q(target_role=employee.role) | models.Q(target_role__isnull=True))
            .exists()
        ):
            raise ValidationError({"roadmap": "Choose a roadmap for this employee’s role."})
        snapshots = calculate(employee, start, end, roadmap_id, request.data.get("category"))
        audit(request.user, "calculate", "Employee", employee.id)
        return Response(SnapshotSerializer(snapshots, many=True).data)

    @action(detail=True, methods=["post"])
    def account(self, request, pk=None):
        require_roles(request.user, "system_admin")
        employee = self.get_object()
        if not employee.active:
            raise ValidationError("Reactivate the employee before provisioning an account.")
        username = str(request.data.get("username", "")).strip()
        password = request.data.get("password", "")
        if not username or len(username) > 150:
            raise ValidationError({"username": "A username of 1–150 characters is required."})
        User = get_user_model()
        if employee.user_id and employee.user.username != username:
            raise ValidationError(
                {"username": "Existing usernames cannot be changed through this action."}
            )
        if User.objects.filter(username=username).exclude(id=employee.user_id).exists():
            raise ValidationError({"username": "Username already in use."})
        try:
            validate_password(password, User(username=username, email=employee.email))
        except DjangoValidationError as exc:
            raise ValidationError({"password": exc.messages})
        with transaction.atomic():
            user = employee.user or User(username=username, email=employee.email)
            user.set_password(password)
            user.is_active = True
            user.save()
            employee.user = user
            employee.save(update_fields=["user"])
        audit(request.user, "provision_account", "Employee", employee.id)
        return Response(
            {
                "username": user.username,
                "employee": employee.id,
                "detail": "Local account ready. Share credentials using your approved internal process.",
            }
        )

    @action(detail=True, methods=["post"])
    def offboard(self, request, pk=None):
        require_roles(request.user, "system_admin")
        employee = self.get_object()
        employee.active = False
        employee.save(update_fields=["active"])
        if employee.user_id:
            employee.user.is_active = False
            employee.user.save(update_fields=["is_active"])
        Membership.objects.filter(employee=employee, ended_on__isnull=True).update(
            ended_on=timezone.localdate()
        )
        audit(request.user, "offboard", "Employee", employee.id)
        return Response(self.get_serializer(employee).data)


class SourceViewSet(ResourceViewSet):
    model = SourceSystem

    @action(detail=True, methods=["post"])
    def test(self, request, pk=None):
        source = self.get_object()
        try:
            result = adapter_for(source).test_connection()
        except Exception as exc:
            result = {
                "ok": False,
                "diagnostics": [
                    f"Connection test failed ({type(exc).__name__}). Verify approved endpoint and read permissions."
                ],
                "coverage": {},
            }
        audit(request.user, "test_connection", "SourceSystem", source.id)
        return Response(result)

    @action(detail=True, methods=["post"])
    def sync(self, request, pk=None):
        with transaction.atomic():
            source = self.get_queryset().select_for_update().get(pk=pk)
            if not source.enabled:
                raise ValidationError("Enable this source before synchronizing.")
            if SyncRun.objects.filter(source=source, status__in=["queued", "running"]).exists():
                raise ValidationError("A synchronization is already queued or running.")
            run = SyncRun.objects.create(
                source=source, cursor=source.cursor, source_revision=source.configuration_revision
            )
        # Synthetic fixtures are tiny and local; live sources always run in a worker.
        if source.kind == "fixture":
            run_sync(run)
        audit(request.user, "sync", "SourceSystem", source.id)
        return Response(serializer_for(SyncRun)(run).data, status=202)

    @action(detail=True, methods=["post"])
    def reconcile(self, request, pk=None):
        with transaction.atomic():
            source = self.get_queryset().select_for_update().get(pk=pk)
            if not source.enabled:
                raise ValidationError("Enable this source before reconciling.")
            if SyncRun.objects.filter(source=source, status__in=["queued", "running"]).exists():
                raise ValidationError("A synchronization is already queued or running.")
            run = SyncRun.objects.create(
                source=source, full_reconcile=True, source_revision=source.configuration_revision
            )
        if source.kind == "fixture":
            run_sync(run)
        audit(request.user, "reconcile", "SourceSystem", source.id)
        return Response(serializer_for(SyncRun)(run).data, status=202)

    @action(detail=True, methods=["post"])
    def purge(self, request, pk=None):
        source = self.get_object()
        if source.enabled:
            raise ValidationError("Disable this source before purging its retained records.")
        with transaction.atomic():
            purge_source(source)
        audit(request.user, "purge", "SourceSystem", source.id)
        return Response(
            {
                "detail": "Retained source records, derived evidence, affected snapshots, and identities removed."
            }
        )


class WorkItemViewSet(ResourceViewSet):
    model = WorkItem

    @action(detail=True, methods=["post"])
    def quality(self, request, pk=None):
        require_roles(request.user, "system_admin", "manager", "reviewer")
        item = self.get_object()
        self.check_write(item)
        me = own_employee(request.user)
        if me and item.contributions.filter(employee=me).exists():
            raise PermissionDenied("An independent authorized reviewer must assess work quality.")
        allowed = {
            "accepted",
            "reopened",
            "rework",
            "reviewed_defect",
            "defect_employee",
            "evidence_url",
        }
        if set(request.data) - allowed:
            raise ValidationError(
                "Only quality observations, optional defect_employee, and evidence_url are accepted."
            )
        if not request.data.get("evidence_url"):
            raise ValidationError(
                {"evidence_url": "Reviewed quality observations need an explicit evidence link."}
            )
        if not any(
            k in request.data for k in ["accepted", "reopened", "rework", "reviewed_defect"]
        ):
            raise ValidationError("Provide at least one quality observation.")
        data = dict(request.data)
        data["quality_evidence_url"] = data.pop("evidence_url")
        serializer = self.get_serializer(item, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        item = serializer.save(quality_reviewed_by=request.user, quality_reviewed_at=timezone.now())
        audit(
            request.user,
            "review_quality",
            "WorkItem",
            item.id,
            {"attributed_employee": item.defect_employee_id},
        )
        return Response(self.get_serializer(item).data)

    @action(detail=True, methods=["post"])
    def commit(self, request, pk=None):
        require_roles(request.user, "system_admin", "manager", "reviewer")
        item = self.get_object()
        self.check_write(item)
        try:
            due = date.fromisoformat(request.data["due_date"])
        except (KeyError, ValueError, TypeError):
            raise ValidationError({"due_date": "An agreed due date is required."})
        changes = list(item.scope_changes)
        changes.append(
            {
                "from": str(item.due_date) if item.due_date else None,
                "to": str(due),
                "approved_by": request.user.id,
                "approved_at": timezone.now().isoformat(),
                "note": str(request.data.get("note", ""))[:1000],
            }
        )
        if not item.agreed_commitment:
            item.original_due_date = due
        item.due_date = due
        item.agreed_commitment = True
        item.commitment_approved_by = request.user
        item.scope_changes = changes
        item.save()
        audit(request.user, "approve_commitment", "WorkItem", item.id)
        return Response(self.get_serializer(item).data)


class IdentityViewSet(ResourceViewSet):
    model = IdentityMapping

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        mapping = self.get_object()
        with transaction.atomic():
            if request.data.get("service"):
                mapping.status = "service"
                mapping.employee = None
            else:
                try:
                    employee = Employee.objects.get(id=request.data.get("employee"), active=True)
                except (Employee.DoesNotExist, ValueError, TypeError):
                    raise ValidationError({"employee": "Select an active employee."})
                mapping.employee = employee
                mapping.status = "resolved"
            # Resolution changes must not leave old ownership attached to imported records.
            records = [
                r
                for r in SourceRecord.objects.filter(source=mapping.source)
                if r.account_id == mapping.account_id
                or mapping.account_id in r.data.get("shared_with", [])
                or mapping.account_id
                in [x.get("account_id") for x in r.data.get("reviewers", []) if isinstance(x, dict)]
            ]
            affected = list(
                Contribution.objects.filter(source_record__in=records).values_list(
                    "employee_id", flat=True
                )
            )
            Contribution.objects.filter(source_record__in=records).delete()
            MetricSnapshot.objects.filter(employee_id__in=affected).delete()
            mapping.resolved_by = request.user
            mapping.save()
            for record in records:
                bind_record(record)
        audit(request.user, "resolve_identity", "IdentityMapping", mapping.id)
        return Response(self.get_serializer(mapping).data)


class EvidenceViewSet(ResourceViewSet):
    @action(detail=True, methods=["post"])
    def verify(self, request, pk=None):
        require_roles(request.user, "system_admin", "manager", "reviewer")
        obj = self.get_object()
        me = own_employee(request.user)
        if me and obj.employee_id == me.id:
            raise PermissionDenied("A different authorized reviewer must verify this evidence.")
        if not obj.evidence_url:
            raise ValidationError(
                {"evidence_url": "An evidence link is required for verification."}
            )
        if self.model == Assessment:
            if obj.kind == "verified":
                raise ValidationError("This assessment has already been verified.")
            # Verification is a new immutable assessment linked to its predecessor.
            obj = Assessment.objects.create(
                employee=obj.employee,
                skill=obj.skill,
                level=obj.level,
                kind="verified",
                evidence_url=obj.evidence_url,
                note=obj.note,
                assessed_on=timezone.localdate(),
                reviewer=request.user,
                previous=obj,
            )
        else:
            obj.verified = True
            obj.reviewer = request.user
            obj.save(update_fields=["verified", "reviewer"])
        audit(request.user, "verify", self.model.__name__, obj.id)
        return Response(serializer_for(self.model)(obj).data)


class ContributionViewSet(EvidenceViewSet):
    model = Contribution


class OutcomeViewSet(EvidenceViewSet):
    model = Outcome


class AssessmentViewSet(EvidenceViewSet):
    model = Assessment


class CorrectionViewSet(ResourceViewSet):
    model = CorrectionRequest

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        require_roles(request.user, "system_admin", "manager", "reviewer")
        with transaction.atomic():
            correction = self.get_queryset().select_for_update().get(pk=pk)
            me = own_employee(request.user)
            if me and correction.employee_id == me.id:
                raise PermissionDenied(
                    "A different authorized reviewer must review this correction."
                )
            if correction.status != "pending":
                raise ValidationError("This correction has already been reviewed.")
            decision = request.data.get("decision")
            if decision not in ["approved", "rejected"]:
                raise ValidationError({"decision": "Choose approved or rejected."})
            correction.status = decision
            correction.review_note = str(request.data.get("review_note", ""))[:5000]
            correction.reviewed_by = request.user
            correction.reviewed_at = timezone.now()
            correction.save()
            contribution = correction.contribution
            before = {"context": contribution.context} if contribution else {}
            after = {"context": correction.requested_context} if decision == "approved" else before
            Approval.objects.create(
                correction=correction,
                reviewer=request.user,
                decision=decision,
                before=before,
                after=after,
            )
            # The original observation is preserved. The approval is a dated addendum,
            # visible via correction/approval endpoints and in report provenance.
        audit(
            request.user,
            "review_correction",
            "CorrectionRequest",
            correction.id,
            {"decision": decision},
        )
        return Response(self.get_serializer(correction).data)


@api_view(["GET"])
def dashboard(request):
    ids = employee_ids(request.user)
    employee = own_employee(request.user)
    contributions = visible_contributions(Contribution.objects.filter(employee_id__in=ids))
    me_metrics = []
    if employee:
        latest = {}
        for snap in (
            MetricSnapshot.objects.filter(employee=employee)
            .select_related("definition")
            .order_by("-id")
        ):
            if snapshot_visible(snap):
                latest.setdefault(snap.definition.key, snap)
        me_metrics = SnapshotSerializer(list(latest.values()), many=True).data
    audit(request.user, "view", "Dashboard")
    return Response(
        {
            "employees": Employee.objects.filter(id__in=ids, active=True).count(),
            "contributions": contributions.count(),
            "pending_corrections": CorrectionRequest.objects.filter(
                employee_id__in=ids, status="pending"
            ).count(),
            "verified_skills": Assessment.objects.filter(employee_id__in=ids, kind="verified")
            .values("employee_id", "skill_id")
            .distinct()
            .count(),
            "sources_stale": SourceSystem.objects.filter(
                models.Q(last_success_at__isnull=True)
                | models.Q(last_success_at__lt=timezone.now() - timedelta(days=2))
            ).count()
            if role(request.user) in ["system_admin", "integration_admin"]
            else None,
            "employee": serializer_for(Employee)(employee).data if employee else None,
            "metrics": me_metrics,
            "recent_evidence": serializer_for(Contribution)(
                contributions.order_by("-occurred_on")[:8], many=True
            ).data,
            "team_summary": [
                {
                    "id": t.id,
                    "name": t.name,
                    "employees": Employee.objects.filter(id__in=ids, team=t).count(),
                }
                for t in Team.objects.filter(employee__id__in=ids).distinct()
            ],
        }
    )


@api_view(["GET"])
def export_report(request):
    try:
        employee = Employee.objects.get(id=int(request.query_params.get("employee", "0")))
    except (Employee.DoesNotExist, ValueError):
        raise NotFound("Employee not found.")
    if employee.id not in employee_ids(request.user):
        audit(request.user, "export_denied", "Employee", employee.id)
        raise PermissionDenied("This report is outside your authorized scope.")
    output_format = request.query_params.get("format", "csv")
    if output_format not in ["csv", "pdf"]:
        raise ValidationError("Supported export formats: csv, pdf.")
    response, snapshot_ids = render_report(employee, output_format)
    audit(
        request.user,
        "export",
        "Employee",
        employee.id,
        {"format": output_format, "snapshot_ids": snapshot_ids},
    )
    return response


def render_report(employee, output_format):
    latest = {}
    for snapshot in (
        MetricSnapshot.objects.filter(employee=employee)
        .select_related("definition", "employee")
        .order_by("-created_at", "-id")
    ):
        if snapshot_visible(snapshot):
            latest.setdefault(snapshot.definition.key, snapshot)
    import json

    def display_value(snapshot):
        if snapshot.value is not None:
            return f"{snapshot.value:g}" + (" days" if snapshot.definition.key == "flow" else "%")
        return (
            "Evidence view (no overall score)"
            if snapshot.status == "available"
            else "Insufficient evidence"
        )

    rows = [
        [
            "Employee",
            "Dimension",
            "Metric version",
            "Window start",
            "Window end",
            "Value",
            "Status",
            "Sample size",
            "Formula",
            "Calculated at",
            "Snapshot ID",
            "Provenance JSON",
        ]
    ]
    for snapshot in latest.values():
        rows.append(
            [
                employee.name,
                snapshot.definition.name,
                snapshot.definition.version,
                str(snapshot.window_start),
                str(snapshot.window_end),
                display_value(snapshot),
                snapshot.status,
                snapshot.details.get("sample_size", 0),
                snapshot.definition.formula,
                snapshot.created_at.isoformat(),
                snapshot.id,
                json.dumps(snapshot.details, sort_keys=True),
            ]
        )
    if output_format == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        writer = csv.writer(response)

        def safe_cell(v):
            text = str(v)
            return (
                "'" + text if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")) else text
            )

        writer.writerows([[safe_cell(c) for c in row] for row in rows])
    else:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether
        from reportlab.lib import colors
        from xml.sax.saxutils import escape

        stream = io.BytesIO()
        styles = getSampleStyleSheet()
        story = [
            Paragraph("WorkLens contribution report", styles["Title"]),
            Paragraph(escape(employee.name), styles["Heading2"]),
            Paragraph(
                "Decision support. Separate dimensions; missing evidence stays unknown. No employee worth score or automated employment decisions.",
                styles["BodyText"],
            ),
            Spacer(1, 16),
        ]
        for snapshot in latest.values():
            section = [
                Paragraph(escape(snapshot.definition.name), styles["Heading2"]),
                Paragraph(
                    escape(
                        f"{display_value(snapshot)} · {snapshot.status.replace('_', ' ')} · sample {snapshot.details.get('sample_size', 0)} · version {snapshot.definition.version}"
                    ),
                    styles["BodyText"],
                ),
                Paragraph(escape(snapshot.definition.formula), styles["BodyText"]),
                Paragraph(
                    escape(
                        f"Window {snapshot.window_start} to {snapshot.window_end}; calculated {snapshot.created_at.isoformat()}"
                    ),
                    styles["BodyText"],
                ),
            ]
            if snapshot.details.get("note"):
                section.append(Paragraph(escape(snapshot.details["note"]), styles["BodyText"]))
            freshness = snapshot.details.get("source_freshness", [])
            if freshness:
                section.append(
                    Paragraph(
                        escape(
                            "Source freshness: "
                            + ", ".join(
                                f"{x['name']} ({'stale' if x['stale'] else 'current'}; last successful sync {x['last_success_at'] or 'never'})"
                                for x in freshness
                            )
                        ),
                        styles["BodyText"],
                    )
                )
            section.append(Spacer(1, 10))
            story.append(KeepTogether(section))
        approved = CorrectionRequest.objects.filter(employee=employee, status="approved")
        if approved.exists():
            story.append(Paragraph("Approved context addenda", styles["Heading2"]))
            for correction in approved:
                story.append(Paragraph(escape(correction.requested_context), styles["BodyText"]))

        def footer(canvas, document):
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.HexColor("#56616d"))
            canvas.drawString(
                42, 24, "WorkLens · authorized contribution report · decision support"
            )
            canvas.drawRightString(A4[0] - 42, 24, f"Page {document.page}")
            canvas.restoreState()

        SimpleDocTemplate(
            stream, pagesize=A4, title="WorkLens authorized report", bottomMargin=45
        ).build(story, onFirstPage=footer, onLaterPages=footer)
        response = HttpResponse(stream.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="worklens-employee-{employee.id}.{output_format}"'
    )
    response["Cache-Control"] = "private, no-store"
    return response, [x.id for x in latest.values()]


@api_view(["GET", "POST"])
def retention(request):
    require_roles(request.user, "system_admin")
    sources = list(SourceSystem.objects.all())
    summary = [
        {
            "source": s.id,
            "name": s.name,
            "retention_days": s.retention_days,
            "eligible_records": SourceRecord.objects.filter(source=s)
            .filter(
                models.Q(updated_at__lt=timezone.now() - timedelta(days=s.retention_days))
                | models.Q(
                    updated_at__isnull=True,
                    ingested_at__lt=timezone.now() - timedelta(days=s.retention_days),
                )
            )
            .count(),
        }
        for s in sources
    ]
    if request.method == "GET":
        return Response(
            {
                "sources": summary,
                "note": "Live deletions do not rewrite encrypted backups. Expire backups on their documented retention schedule.",
            }
        )
    if request.data.get("confirm") is not True:
        raise ValidationError({"confirm": "Set true after reviewing the retention preview."})
    deleted = 0
    with transaction.atomic():
        for source in sources:
            records = SourceRecord.objects.filter(source=source).filter(
                models.Q(updated_at__lt=timezone.now() - timedelta(days=source.retention_days))
                | models.Q(
                    updated_at__isnull=True,
                    ingested_at__lt=timezone.now() - timedelta(days=source.retention_days),
                )
            )
            affected = Contribution.objects.filter(source_record__in=records).values_list(
                "employee_id", flat=True
            )
            MetricSnapshot.objects.filter(employee_id__in=affected).delete()
            Contribution.objects.filter(source_record__in=records).delete()
            WorkItem.objects.filter(source_record__in=records).delete()
            deleted += records.count()
            records.delete()
    audit(request.user, "retention_delete", "SourceRecord", detail={"count": deleted})
    return Response({"deleted_records": deleted})


@api_view(["POST"])
def csv_import(request):
    require_roles(request.user, "system_admin")
    kind = request.data.get("kind")
    content = request.data.get("content", "")
    if not isinstance(content, str) or len(content) > 1024 * 1024:
        raise ValidationError("CSV must be text smaller than 1 MiB.")
    types = {
        "employees": Employee,
        "teams": Team,
        "roles": Role,
        "skills": Skill,
        "goals": Goal,
        "assessments": Assessment,
        "historical_records": Contribution,
        "memberships": Membership,
    }
    if kind not in types:
        raise ValidationError({"kind": "Choose " + ", ".join(types)})
    rows = list(csv.DictReader(io.StringIO(content)))
    if not rows or len(rows) > 5000:
        raise ValidationError("Provide 1–5000 CSV records and a header row.")
    model = types[kind]
    created = 0
    updated = 0
    allowed = {
        "employees": {
            "stable_id",
            "name",
            "email",
            "team",
            "role",
            "manager",
            "capacity",
            "context",
        },
        "teams": {"name", "description"},
        "roles": {"name", "description"},
        "skills": {"name", "category", "description"},
        "goals": {"employee", "title", "description", "due_date", "progress", "status"},
        "assessments": {"employee", "skill", "level", "assessed_on", "evidence_url", "note"},
        "historical_records": {
            "employee",
            "title",
            "kind",
            "occurred_on",
            "evidence_url",
            "context",
        },
        "memberships": {"employee", "team", "role", "started_on", "ended_on"},
    }[kind]
    with transaction.atomic():
        for line, row in enumerate(rows, 2):
            if set(row) - allowed:
                raise ValidationError(
                    {
                        "line": line,
                        "detail": "Unknown or protected CSV fields: "
                        + ", ".join(str(x) for x in set(row) - allowed),
                    }
                )
            data = {k: v.strip() for k, v in row.items() if v is not None and v.strip()}
            if "employee" in data:
                employee = Employee.objects.filter(stable_id=data["employee"]).first()
                if employee:
                    data["employee"] = employee.id
            for fk in ["employee", "team", "role", "manager", "skill"]:
                if fk in data:
                    try:
                        data[fk] = int(data[fk])
                    except (TypeError, ValueError):
                        raise ValidationError(
                            {
                                "line": line,
                                "detail": f"{fk} must identify an existing numeric record; employee also accepts a stable_id.",
                            }
                        )
            existing = None
            if kind == "employees":
                existing = Employee.objects.filter(stable_id=data.get("stable_id")).first()
            elif kind in ["teams", "roles", "skills"]:
                existing = model.objects.filter(name=data.get("name")).first()
            elif kind == "goals":
                existing = Goal.objects.filter(
                    employee_id=data.get("employee"), title=data.get("title")
                ).first()
            elif kind == "assessments":
                data["kind"] = "evidence_supported"
                existing = Assessment.objects.filter(
                    employee_id=data.get("employee"),
                    skill_id=data.get("skill"),
                    assessed_on=data.get("assessed_on"),
                    kind="evidence_supported",
                    level=data.get("level"),
                    evidence_url=data.get("evidence_url", ""),
                ).first()
            elif kind == "historical_records":
                existing = Contribution.objects.filter(
                    employee_id=data.get("employee"),
                    title=data.get("title"),
                    occurred_on=data.get("occurred_on"),
                    evidence_url=data.get("evidence_url", ""),
                    origin="claimed",
                ).first()
            elif kind == "memberships":
                existing = Membership.objects.filter(
                    employee_id=data.get("employee"),
                    team_id=data.get("team"),
                    started_on=data.get("started_on"),
                ).first()
            old_team = getattr(existing, "team_id", None)
            old_role = getattr(existing, "role_id", None)
            if existing and kind in ["assessments", "historical_records"]:
                updated += 1
                continue
            serializer = serializer_for(model)(
                existing, data=data, partial=bool(existing), context={"request": request}
            )
            if not serializer.is_valid():
                raise ValidationError({"line": line, "errors": serializer.errors})
            obj = serializer.save()
            if existing:
                updated += 1
            else:
                created += 1
            if kind == "employees":
                if existing and (old_team != obj.team_id or old_role != obj.role_id):
                    MetricSnapshot.objects.filter(employee=obj).delete()
                    Membership.objects.filter(employee=obj, ended_on__isnull=True).update(
                        ended_on=timezone.localdate()
                    )
                if (
                    obj.team_id
                    and not Membership.objects.filter(employee=obj, ended_on__isnull=True).exists()
                ):
                    Membership.objects.create(
                        employee=obj, team=obj.team, role=obj.role, started_on=timezone.localdate()
                    )
    audit(request.user, "csv_import", kind, detail={"created": created, "updated": updated})
    return Response({"created": created, "updated": updated, "rows": len(rows)})


class ReportJobViewSet(viewsets.ReadOnlyModelViewSet):
    def get_serializer_class(self):
        return serializer_for(ReportJob)

    def get_queryset(self):
        queryset = ReportJob.objects.filter(
            employee_id__in=employee_ids(self.request.user)
        ).order_by("-id")
        if role(self.request.user) != "system_admin":
            queryset = queryset.filter(requested_by=self.request.user)
        return queryset

    def create(self, request):
        from django.conf import settings

        if not request.user.is_active or not role(request.user):
            raise PermissionDenied("Active application access is required.")
        try:
            employee = Employee.objects.get(id=request.data.get("employee"), active=True)
        except (Employee.DoesNotExist, ValueError, TypeError):
            raise ValidationError({"employee": "Select an active employee."})
        if employee.id not in employee_ids(request.user):
            raise PermissionDenied("This report is outside your authorized scope.")
        output_format = request.data.get("format", "pdf")
        if output_format not in ["csv", "pdf"]:
            raise ValidationError({"format": "Choose csv or pdf."})
        with transaction.atomic():
            # Serialize global admission on PostgreSQL, and also lock the requester.
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(78149232)")
            get_user_model().objects.select_for_update().get(id=request.user.id)
            retained = ReportJob.objects.filter(expires_at__gt=timezone.now())
            if retained.filter(requested_by=request.user).count() >= 20:
                raise ValidationError(
                    "You have reached the 20-report retention limit. Wait for older artifacts to expire."
                )
            if retained.count() >= 500:
                raise ValidationError(
                    "The artifact retention limit is reached. Try again after older artifacts expire."
                )
            if (
                ReportJob.objects.filter(
                    requested_by=request.user, status__in=["queued", "running"]
                ).count()
                >= 3
            ):
                raise ValidationError("You already have three pending report jobs.")
            if ReportJob.objects.filter(status__in=["queued", "running"]).count() >= 100:
                raise ValidationError(
                    "The report queue is full. Try again after existing jobs finish."
                )
            job = ReportJob.objects.create(
                requested_by=request.user,
                employee=employee,
                format=output_format,
                expires_at=timezone.now()
                + timedelta(hours=getattr(settings, "REPORT_EXPIRY_HOURS", 24)),
            )
        audit(
            request.user,
            "queue_report",
            "ReportJob",
            job.id,
            {"employee": employee.id, "format": output_format},
        )
        return Response(self.get_serializer(job).data, status=202)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        from .reporting import downloadable

        job = self.get_object()
        if not downloadable(job, request.user):
            audit(request.user, "report_download_denied", "ReportJob", job.id)
            raise PermissionDenied(
                "This artifact is unavailable, expired, or its employee/source authorization has changed. Queue a fresh report if access permits."
            )
        response = HttpResponse(
            bytes(job.payload),
            content_type="application/pdf" if job.format == "pdf" else "text/csv; charset=utf-8",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="worklens-report-{job.id}.{job.format}"'
        )
        response["Cache-Control"] = "private, no-store"
        audit(request.user, "download_report", "ReportJob", job.id)
        return response
