from rest_framework.exceptions import PermissionDenied
from .models import Employee, AuditEvent


def role(user):
    if not user.is_authenticated:
        return None
    if user.is_superuser:
        return "system_admin"
    try:
        return user.employee.access_role if user.employee.active else None
    except Employee.DoesNotExist:
        return None


def own_employee(user):
    try:
        return user.employee if user.employee.active else None
    except Employee.DoesNotExist:
        return None


def employee_ids(user):
    r = role(user)
    if r in ["system_admin", "reviewer"]:
        return list(Employee.objects.values_list("id", flat=True))
    me = own_employee(user)
    if not me:
        return []
    ids = {me.id}
    if r == "manager":
        pending = {me.id}
        while pending:
            following = (
                set(Employee.objects.filter(manager_id__in=pending).values_list("id", flat=True))
                - ids
            )
            ids.update(following)
            pending = following
    return list(ids)


def require_roles(user, *roles):
    if role(user) not in roles:
        raise PermissionDenied("Your application role does not permit this action.")


def audit(user, action, resource, object_id="", detail=None):
    AuditEvent.objects.create(
        actor=user if user.is_authenticated else None,
        action=action,
        resource=resource,
        object_id=str(object_id),
        detail=detail or {},
    )


def record_allowed_for_employee(record, employee):
    """Optional explicit team bindings narrow identity-based record access."""
    from .models import AccessScope

    if not record.available or record.deleted:
        return False
    bindings = AccessScope.objects.filter(source_id=record.source_id)
    if not bindings.exists():
        return True
    from django.db.models import Q

    return (
        bindings.filter(scope=record.scope)
        .filter(Q(team__isnull=True) | Q(team_id=employee.team_id))
        .exists()
    )


def visible_contributions(queryset):
    from django.db.models import Q, F

    no_binding = Q(source_record__source__accessscope__isnull=True)
    matching = Q(source_record__source__accessscope__scope=F("source_record__scope")) & (
        Q(source_record__source__accessscope__team__isnull=True)
        | Q(source_record__source__accessscope__team_id=F("employee__team_id"))
    )
    return queryset.filter(
        Q(source_record__isnull=True)
        | (Q(source_record__available=True, source_record__deleted=False) & (no_binding | matching))
    ).distinct()


def snapshot_visible(snapshot):
    from .models import SourceRecord

    references = snapshot.details.get("source_records", [])
    if not references and snapshot.details.get("source_freshness"):
        # Old snapshots without record-level provenance cannot establish current access.
        return False
    for reference in references:
        record = SourceRecord.objects.filter(
            id=reference.get("id"), source_id=reference.get("source_id")
        ).first()
        if not record or not record_allowed_for_employee(record, snapshot.employee):
            return False
    return True
