## Section A: Observed GTM Motion (Phase 1: pricing-only)

You are writing Section A of the GTM X-Ray for **{{ domain }}**. This Phase 1 version of Section A is restricted to what's observable from the company's pricing and packaging only. (Phase 2 will widen this to include hiring shape, tech stack, and content cadence.)

### What pricing tells you about GTM motion

A company's published pricing reveals motion in ways the company often doesn't realize:

- **Public published pricing** with multiple tiers and clear per-seat / per-month cadence usually means a self-serve or PLG-adjacent motion, sold mid-market to SMB.
- **Contact-us gating** with no public prices usually means an enterprise-led, sales-driven motion. The company believes its ACV is high enough that public prices anchor wrong.
- **Mixed** (some tiers public, top tier "contact us") means hybrid land-and-expand, often PLG-into-enterprise.
- **Frequent pricing changes** suggest the company is still finding pricing fit. Two consecutive price increases in 18 months is a strong signal of either (a) market traction giving them pricing power or (b) under-pricing they're trying to correct.
- **Tier additions** suggest segment expansion or upmarket motion. Tier removals suggest pruning underperforming segments.

### Pricing data observed

**Public pricing page found:** {{ "yes" if data.has_public_pricing else "no" }}
**Contact-us gated:** {{ "yes" if data.is_contact_us_gated else "no" }}
**Pricing URL:** {{ data.current_pricing_url or "not found" }}

**Current tiers:**
{% if data.current_tiers %}
{% for t in data.current_tiers %}
- {{ t.name }}: {{ t.price }} {{ t.cadence }}{% if t.notes %}. {{ t.notes }}{% endif %}
{% endfor %}
{% else %}
(none extracted)
{% endif %}

**Pricing changes observed in the last 18 months:**
{% if data.detected_changes %}
{% for c in data.detected_changes %}
- {{ c.date_observed }}: {{ c.kind }} — `{{ c.before }}` → `{{ c.after }}`
{% endfor %}
{% else %}
(none)
{% endif %}

**Historical snapshots:** {{ data.historical_snapshots | length }} Wayback snapshot(s) recovered.

### Your task

Write Section A for this prospect. Focus on what the pricing data shows about their motion. Be honest about what you cannot tell from pricing alone (and add those to discovery_questions). Stay in Revenue Reimagined's practitioner voice.
