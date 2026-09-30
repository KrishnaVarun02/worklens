# Metric dictionary

There is no total score, rank, worth score, or predicted potential. Every result is
a separate evidence dimension. Frozen snapshots retain a formula version,
configuration, inputs, source links, evidence dates, selected period, exclusions,
sample size, missing data, and source freshness. An absent observation is unknown.

## Delivery reliability

`100 × on-time eligible commitments / eligible commitments due in the period`.
An incomplete commitment that was due belongs in the denominator; a due date
outside the selected window does not. A missing agreed due date is shown as
missing data. Original commitments and approved changes remain inspectable.

Example: five eligible due commitments, four completed by their due dates, one
late or unfinished: **80%**, numerator 4, denominator 5. With only two eligible
commitments and the default minimum of 3, the value is **insufficient evidence**,
not 0%. Shared delivery retains documented contributors and shares; the application
does not infer that the final assignee did all the work.

## Delivery flow

Median elapsed workflow days for completed comparable work, grouped by category.
Example: feature cycle times `[2, 4, 8]` produce **4 days**. A bug's cycle time is
kept in a separate group. The view includes the distribution, active/blocked
workflow intervals when observed, and sample sizes. Missing/invalid or incomplete
workflow histories must not imply zero active time. Workflow days are process
observations, never actual employee working hours.

## Work quality

Known acceptance rate: `100 × accepted mature items / mature items with observed acceptance`.
Reopening, rework and reviewed defect attribution are separate indicators with
known observation counts. Default maturity is 30 days after completion.

Example: five mature items, four with known acceptance, three accepted: **75%**,
numerator 3, denominator 4; the fifth is unknown. Recently completed items are
excluded with a stated reason. A defect flag requires a human-reviewed attribution;
service reliability does not become an individual employee metric.

## Business contribution

Structured goal progress appears beside separately reviewed, evidenced outcomes.
Goal progress averages are descriptive only and are sample-thresholded. Example:
three equally tracked goals at 40%, 70% and 100% produce **70% mean reported goal
progress**. That number does not express financial value. A claimed cost saving
or customer improvement appears as verified only after review and evidence.

## Collaboration and knowledge sharing

Mentoring, useful reviews, pairing, shared delivery and documentation are supported
by evidence and human assessments. The number of reviewed evidence records measures
coverage only. Neither raw review/document counts nor message volume establish
quality. This dimension has no numerical quality score.

## Skills

Skill records use explicit proficiency rubrics and three distinct states:
self-declared, evidence-supported and reviewer-verified. Candidate evidence from
work mappings is not a proficiency assessment. Fresh, verified assessments support
the skills view; dated/stale assessments remain visible with their status. Current
levels do not silently replace historical assessment records.

## Alignment with the selected roadmap

Administrators define the dated roadmap, target role, required skill levels,
importance weights, assessment freshness and completeness policy.

`100 × Σ(weight × min(verified_level / required_level, 1)) / Σ(weight)`

Example: Python requires level 4 with weight 2 and PostgreSQL requires level 3
with weight 1. Fresh verified levels 3 and 3 yield
`100 × (2 × 3/4 + 1 × 3/3) / 3 = 83.3%`. Higher-than-required proficiency is
capped at 100% of that requirement. Required levels and weights must be positive.

If PostgreSQL has no fresh verified assessment, coverage is **50% of requirements**
and the overall alignment is **insufficient evidence**, not a score calculated by
assigning the missing skill zero. The initial implementation requires full
assessment coverage before publishing a score even if a looser coverage preference
is configured; partial coverage remains visible. Matching skills, gaps, dates and
development actions are shown independently of score availability.

## Interpretation and change control

Capacity, onboarding, changed responsibilities, dependencies, complexity and
non-sensitive absence context accompany evidence. They are not hidden multipliers
that fabricate adjusted productivity. Managers must interpret these factors during
review. Do not compare different roles or team story-point scales.

Formulas are fixed deterministic Python implementations. Administrator settings are
validated data, never executable code. Formula/configuration versions are copied
into snapshots; changes produce new snapshots. Corrections create explicit approval
history and subsequent calculations. Current access restrictions still apply to
historical data; a frozen snapshot is not permission to reveal revoked source material.
