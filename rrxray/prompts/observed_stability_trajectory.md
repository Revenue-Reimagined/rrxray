Domain: {{ domain }}

# Section B: Observed Stability and Trajectory

You are diagnosing the prospect's leadership stability and trajectory based on publicly observable signals.

You will receive aggregated leadership data — counts and tenures, never names. Do not invent names. Refer to roles by descriptor only ("the CRO", "the CEO", "the founder").

## Aggregated leadership signals

**Seat changes (with derived timeframe):**
{% if aggregates.seat_changes %}
{% for role, count in aggregates.seat_changes.items() %}
- {{ role }}: {{ count }} change(s){% if aggregates.seat_change_ages_months[role] is not none %}, last change ~{{ aggregates.seat_change_ages_months[role] }} months ago{% else %}, timeframe undatable{% endif %}
{% endfor %}
{% else %}
- No exec-change records recovered.
{% endif %}

**Important:** Use the "last change ~N months ago" figure as the AUTHORITATIVE timeframe when describing when changes happened. Do not infer or estimate timeframe brackets when an explicit number is provided. Note that "N months ago" can exceed 18 — search results sometimes return older changes; the explicit number is correct, regardless of whether the lookback window was 18 months.

**Recent changes (within 9 months):**
{% if aggregates.recent_changes %}
{% for change in aggregates.recent_changes %}
- {{ change.role }}: {{ change.action }} ~{{ change.occurred_at_months_ago }} months ago
{% endfor %}
{% else %}
- None.
{% endif %}

**Current incumbents (high confidence only):**
{% if aggregates.current_incumbents_by_role %}
{% for role, info in aggregates.current_incumbents_by_role.items() %}
- {{ role }}: in seat ~{{ info.tenure_months or "unknown" }} months ({{ info.confidence }} confidence)
{% endfor %}
{% else %}
- None recovered.
{% endif %}

**Founder presence:**
- Founder in CEO seat: {{ "yes" if aggregates.founder_present_in_ceo_seat else "no" }}
{% if aggregates.founder_tenure_years %}
- Founder tenure: ~{{ aggregates.founder_tenure_years }} years
{% endif %}

**Tenure confirmation:** {{ aggregates.tenure_confirmed_count }} of {{ aggregates.tenure_confirmed_total }} current incumbents have tenure data confirmed via PeopleDataLabs.

**Hire-origin pattern:**
- External hires (incumbents who came from outside the company): {{ aggregates.external_hire_count }}
- Internal promotions (incumbents promoted from within): {{ aggregates.internal_promotion_count }}

**Prior employer per role (where confirmed):**
{% for role, prior in aggregates.prior_employer_signals.items() %}
{% if prior %}
- {{ role }}: came from {{ prior }}
{% else %}
- {{ role }}: prior employer not recovered
{% endif %}
{% endfor %}

**Leadership enrichment status:** {{ aggregates.enrichment_aborted_reason }} (spend: ${{ "%.2f"|format(aggregates.enrichment_spend_dollars) }})
{% if aggregates.enrichment_aborted_reason == "cost_cap" or aggregates.enrichment_aborted_reason == "circuit_breaker" %}
Note: PDL enrichment was partial. Some incumbents may lack tenure / prior-employer context. Frame findings accordingly.
{% endif %}

**Seats with no public change in 18 months:** {{ aggregates.seats_with_no_change_18mo | join(", ") if aggregates.seats_with_no_change_18mo else "none" }}

**Collector findings (rule-based):**
{% if aggregates.collector_findings %}
{% for f in aggregates.collector_findings %}
- {{ f }}
{% endfor %}
{% else %}
- (none)
{% endif %}

## Diagnostic posture

Commit to a single hypothesis about this company's leadership stability and trajectory. Do not enumerate possibilities; pick the strongest read of the data and write it.

Possible hypotheses:
- **Stable, founder-led** — founder still in CEO seat with multi-year tenure, no recent exec changes
- **Stable, professionalized** — non-founder CEO with tenure, no recent changes
- **In active transition** — one or more recent exec changes (≤9 months); motion direction likely shifting
- **Unstable / churning** — multiple changes in same seat in past 18 months; motion uncertainty high
- **Signal not recovered** — public sources insufficient to commit to a hypothesis; discovery must establish

Output 2-4 paragraphs. Each paragraph commits to a specific observation and its diagnostic implication. Use → for recommendation bullets when applicable. Avoid em dashes; use commas, periods, or colons. Do not use the words: leverage, leveraging, leveraged, synergies, synergy, holistic, streamline, impactful. Use GTM Gap™ on first reference if relevant.

**Prior-employer motion lens:** When you see a prior_employer for a revenue or marketing role, infer the motion shape that incumbent likely brings:
- Came from an enterprise SaaS (Salesforce, Oracle, etc.) → likely enterprise outbound motion bias
- Came from a PLG company (Figma, Notion, etc.) → likely product-led pipeline bias
- Came from a smaller startup / unknown → bias unclear; do not speculate
- Came from the same vertical → motion stays domain-aligned; market expertise > motion shift
This is a working hypothesis only — state it as such ("the incoming CRO came from X, suggesting...") rather than as a confirmed fact.

**Anchoring timeframes accurately:** When you describe WHEN a change happened, anchor on `current_incumbents_by_role[role].tenure_months` if available — that is the most reliable timeframe in the aggregates. If a seat has 1 change AND a current incumbent with `tenure_months: N`, the change happened approximately N months ago. Do not assume changes fall in the "9-18 months ago" bucket just because they are not in `recent_changes`; the lookback window is 18 months but `recent_changes` only captures the past 9. Changes can be much older than 18 months if the search returned results from before the lookback bound — explicitly state the actual age based on tenure_months rather than guessing a window.

Findings, gaps, and discovery questions:

- **Findings** are observations supported by the data. Always cite a specific source field from the aggregates.
- **Gaps** are questions a human at the company must answer because public data cannot. BEFORE listing a gap, reason from the data provided:
  - If the question is "X vs Y are distinct or the same role" — check whether incumbents/changes differ in name; if different people, the roles are distinct, state that as a finding.
  - If the question is "tenure unconfirmed" — check `recent_changes` for a date; if a date is present, state the inferred tenure as a finding instead of listing a gap.
  - If the question is "is the founder operationally involved" — check whether the founder appears in `current_incumbents_by_role`; if present, state that.
  - In general: if you can answer it from the aggregates, answer it as a finding. Do not list answerable questions as gaps.
- **Discovery questions** are for the human-to-human discovery call, not for AI to derive. Limit to 3-5; each must require a primary source (someone inside the company) to answer.
- Quality threshold: a reader should never see a gap or discovery question whose answer is sitting in the aggregates above.
