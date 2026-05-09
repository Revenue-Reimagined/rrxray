Domain: {{ domain }}

# Section B: Observed Stability and Trajectory

You are diagnosing the prospect's leadership stability and trajectory based on publicly observable signals.

You will receive aggregated leadership data — counts and tenures, never names. Do not invent names. Refer to roles by descriptor only ("the CRO", "the CEO", "the founder").

## Aggregated leadership signals

**Seat changes (past 18 months):**
{% if aggregates.seat_changes %}
{% for role, count in aggregates.seat_changes.items() %}
- {{ role }}: {{ count }} change(s)
{% endfor %}
{% else %}
- No exec-change records recovered.
{% endif %}

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

Also produce findings, gaps, and discovery questions if applicable.
