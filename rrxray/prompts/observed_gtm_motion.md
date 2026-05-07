## Section A: Observed GTM Motion

You are writing Section A of the GTM X-Ray for **{{ domain }}**. The question is: what is this company's observable GTM motion? Reason from the signals available below. Acknowledge gaps where signals are absent rather than fabricating; honest absence is more diagnostically valuable than padding.

### Signal-by-signal framework guidance

A company's GTM motion can be inferred by reading multiple signals together:

**Pricing & packaging tells you:**

- Public published pricing with tiers and per-seat cadence usually = self-serve / PLG-adjacent, mid-market to SMB
- Contact-us gating with no public prices usually = enterprise-led, sales-driven
- Mixed (some tiers public, top tier "contact us") = hybrid land-and-expand
- Frequent pricing changes = still finding pricing fit
- Tier additions = segment expansion or upmarket
- Tier removals = pruning underperforming segments

**Tech stack tells you:**

- HubSpot only = mid-market sales, marketing-led nurture
- HubSpot + Salesforce signals = upmarket movement, hybrid CRM
- Pendo + Intercom + product-analytics = product-led adoption motion
- Marketo + Demandbase / 6sense = enterprise ABM motion
- No detectable martech = early-stage, privacy-led, server-side tagging, or low GTM maturity (the discovery question disambiguates)
- Live chat without marketing automation = inbound conversations not feeding nurture

**Cross-signal reasoning** is the diagnostic value:

- Pricing gated + Marketo + Demandbase = enterprise ABM motion (consistent)
- Pricing public + Pendo + Intercom = PLG with sales-assist (consistent)
- Pricing gated + HubSpot only = misalignment between intended motion and tooling maturity (diagnostic finding worth surfacing)
- Pricing public + no analytics = unusual; flag in discovery questions

### Available signals for {{ domain }}

{% if pricing %}
**Pricing & Packaging signal**

- Public pricing page found: {{ "yes" if pricing.has_public_pricing else "no" }}
- Contact-us gated: {{ "yes" if pricing.is_contact_us_gated else "no" }}
- Pricing URL: {{ pricing.current_pricing_url or "not found" }}

Current tiers:
{% if pricing.current_tiers %}
{% for t in pricing.current_tiers %}
- {{ t.name }}: {{ t.price }} {{ t.cadence }}{% if t.notes %}. {{ t.notes }}{% endif %}
{% endfor %}
{% else %}
(none extracted)
{% endif %}

Pricing changes observed in the last 18 months:
{% if pricing.detected_changes %}
{% for c in pricing.detected_changes %}
- {{ c.date_observed }}: {{ c.kind }} — `{{ c.before }}` → `{{ c.after }}`
{% endfor %}
{% else %}
(none)
{% endif %}

Historical snapshots: {{ pricing.historical_snapshots | length }} Wayback snapshot(s) recovered.
{% else %}
**Pricing & Packaging signal:** not collected (collector failed or skipped). Note this gap; consider adding pricing-related discovery questions.
{% endif %}

{% if tech_stack %}
**Tech Stack signal**

Detected tools ({{ tech_stack.detected_tools | length }}):
{% if tech_stack.detected_tools %}
{% for tool in tech_stack.detected_tools %}
- {{ tool.category }}: {{ tool.name }} ({{ tool.confidence }} confidence; signature: `{{ tool.signature_id }}`)
{% endfor %}
{% else %}
(none detected)
{% endif %}

Categories observed: {{ tech_stack.categories_observed | join(", ") if tech_stack.categories_observed else "(none)" }}
Categories not detected: {{ tech_stack.categories_absent | join(", ") if tech_stack.categories_absent else "(all 9 categories observed)" }}

Collector findings:
{% if tech_stack.findings %}
{% for f in tech_stack.findings %}
- {{ f.text }}
{% endfor %}
{% else %}
(none)
{% endif %}
{% else %}
**Tech Stack signal:** not collected (collector failed or skipped). Note this gap; consider adding analytics / martech discovery questions.
{% endif %}

### Your task

Write Section A. Reason ACROSS the available signals (not just within each one). Pick out cross-signal patterns that confirm or contradict each other. Be specific: cite which tier, which tool, which date when relevant. State patterns as facts, not opinions ("the current revenue leader has been in seat 11 months" not "leadership might be unstable"). Acknowledge gaps where you can't tell from the data; add those to discovery_questions.

Output 3-5 narrative paragraphs and 3-5 gap_bullets. Each finding cites a source. Each discovery question is one Revenue Reimagined would actually ask in a real conversation.
