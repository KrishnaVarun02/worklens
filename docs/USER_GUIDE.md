# Administrator and employee guide

## Start with purpose and scope

Agree what evidence is useful for development, mentoring and work allocation.
Explain the source scopes, retention, reviewer responsibilities and correction
process to employees before importing real records. WorkLens has no global
individual leaderboard or automatic employment decisions. A metric is a view of
bounded evidence, not a complete account of a person.

## System administrator

Bootstrap the installation on a restricted network. Set up teams and role
templates, then create employees with stable IDs, reporting relationships and
appropriate application access roles. Record team and role changes through the
application so historical memberships remain available. Employee emails and aliases
may change without changing stable IDs.

Provision local user accounts explicitly, or link pre-provisioned accounts to the
optional company identity adapter. A directory entry alone does not grant login.
Use unique passwords and the organization's account-recovery process. The initial
superuser can also use Django's local `/admin/` account-management interface.

Define the skill taxonomy and proficiency rubrics before collecting assessments.
Create a dated roadmap, select its target role, and add required skills, positive
levels and importance weights. Specify assessment freshness and coverage rules.
The initial scoring policy requires all required skill assessments to be current
before showing an overall alignment percentage; partial coverage and gaps remain
visible without inventing proficiency values.

Use Administration to inspect audit events, import CSV records, preview retention
deletions and manage organization data. Review deletion counts before applying a
policy. Disable an employee through offboarding to end login and active membership;
delete retained records only under the agreed lifecycle policy. The separate backup
retention process remains necessary after active-record deletion.

## Integration administrator

Choose a supported source/deployment pair. Configure exact endpoint, source scopes,
field allowlists, workflow mappings and separately entered read-only credentials.
The server owner must first approve endpoint and network policies. Use Test
connection, review permission diagnostics, then synchronize. A source email is
never a credential and matching it never grants broader access.

Review source-account identity suggestions. Resolve unique and ambiguous matches
explicitly; do not guess based on duplicate names. Mark service accounts as service
identities. Check email aliases and employment status when resolving changed emails.
Record IDs remain linked to stable source account IDs rather than display names.

Inspect sync runs for status, checkpoint, errors, records processed and last
success. Repeated synchronization updates existing source IDs. Use full reconciliation
after scope/permission changes or suspected omissions. A confirmed access failure
quarantines retained observations. Ordinary outages preserve prior data with stale
indicators. Review [connector-specific coverage](CONNECTORS.md) before treating a
sync as complete evidence for a purpose.

Disable a connector before purging its data. Purging removes observations,
attributions, affected snapshots and identity mappings from active storage. It does
not rewrite old backups or revoke the token at its original source system.

## Employee

Your dashboard and profile show your permitted evidence, goals, skills and
calculated dimensions. Inspect each metric's definition, version, period, inputs,
sample size and missing-data notes before interpreting its value.

Use Add evidence to submit a contribution claim with a date, supporting link and
context. Include shared delivery, pairing, useful reviews, mentoring and accepted
documentation where supported. A claim remains separate from an imported observation
and from a reviewer's assessment. Activity counts alone do not prove usefulness.

If evidence lacks context or contains a mistake, submit a correction explaining
the requested change. The reviewer approves or rejects it with a note. Approved
context becomes a dated addendum; the original observation is preserved. You cannot
approve your own evidence or correction.

Record a self-declared or evidence-supported skill assessment with its rubric
level, date and supporting link. An authorized different reviewer must verify it.
Candidate skills suggested by configured labels or work categories are starting
points for review and never establish proficiency automatically.

Reports use the same authorization scope as the profile. Downloaded CSV/PDF files
are sensitive company records; store and share them under your organization's rules.
Use an immediate export for a small report, or queue it for the company-controlled
worker and download it from report history when generation succeeds. Server-held
artifacts expire after 24 hours and are checked against current access rules again
at download time.

## Manager and reviewer

Managers see their authorized reporting hierarchy. Reviewers have the expressly
assigned cross-team review responsibility. Inspect commitments, dependencies,
blocked workflow periods, role changes, work complexity and available capacity
alongside any calculated result. Do not collect sensitive reasons for absence.

Approve actual delivery commitments and changes explicitly. Imported ticket due
dates are observations until a reviewer records the agreed commitment. Reviewed
contribution records determine supported participation; the final assignee is not
automatically awarded all credit.

Verify contribution usefulness and business impact only with evidence. Record
quality observations after the appropriate maturity window. Individual defect
attribution requires explicit reviewed support; team/service reliability stays at
its own level. Assessments and reviews retain their dates and provenance.

Discuss roadmap gaps as development actions—training, mentoring or better work
allocation—not as predictions of future worth. Missing/stale assessments mean
unknown alignment. Different work categories, unrelated roles and different
teams' story-point scales do not support direct individual comparisons.

## Understanding common states

| State | Meaning / next action |
| --- | --- |
| Loading | The application is retrieving authorized records |
| No records | There is no permitted evidence in this view; configure or submit relevant evidence |
| Stale source | Check last successful synchronization and source availability |
| Insufficient evidence | Check sample threshold, missing inputs and assessment freshness |
| Unresolved / ambiguous identity | Integration administrator must review attribution |
| Claimed / evidence-supported | Awaiting independent review; not verified proficiency or impact |
| Revoked / unavailable source | Reconcile authorization before using retained observations |
| Available evidence, no overall score | A qualitative or grouped view; inspect its evidence rather than inventing a number |
