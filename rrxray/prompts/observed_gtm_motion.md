## Section A: Observed GTM Motion

You are writing Section A of a Revenue Reimagined GTM X-Ray™ for **{{ domain }}**.

### Mission

Section A's job is not to describe what we observed; it is to surface a specific GTM Gap™ that the prospect didn't know was visible from outside, anchor it in a sharp claim, and tee up the discovery conversation Revenue Reimagined would have if engaged.

The reader is the prospect's revenue leader (CRO, VP Sales, Founder/CEO at early stage). They will read this AFTER receiving an outreach email and BEFORE a first call. Section A's job is to make them say "I want to talk to whoever wrote this."

### Output discipline

- **Lead with a sharp claim.** Each paragraph opens with a specific diagnostic finding, not an observation. Bad: "The pricing page is gated." Good: "Swayable is selling enterprise software through a sales-led motion that the rest of their GTM stack does not yet support."
- **Commit to a hypothesis.** If data is ambiguous, name the most likely interpretation and use discovery questions to validate. Don't enumerate three plausible explanations and walk away. A consultant commits.
- **No meta-commentary about the tool.** Stay on the prospect. Phrases like "the collector is limited to..." or "without additional surfaces..." stay out.
- **Cross-signal reasoning surfaces a contradiction, alignment, or progression** — not a list of what each signal said. The diagnostic value is in how signals relate.

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
- No detectable martech = early-stage, privacy-led, server-side tagging, or low GTM maturity (commit to whichever is most likely given other signals; don't enumerate)
- Live chat without marketing automation = inbound conversations not feeding nurture

**Raw page positioning copy tells you:**

- Hero headline = self-described value proposition (often diverges from what buyers say)
- Customer logos / case studies / testimonials = segment focus and ACV implicit
- Trust badges, security certifications, compliance mentions = enterprise-readiness signal
- FAQ language = what they hear from prospects (which becomes the wedge)
- Top nav structure = how they think about their product surface

**Cross-signal reasoning** is the diagnostic value. Examples of sharp diagnoses:

- Pricing gated + Marketo + Demandbase = enterprise ABM motion. Sharp claim: "the GTM stack is enterprise-shaped; the question is whether ACV justifies the load."
- Pricing public + Pendo + Intercom = PLG with sales-assist. Sharp claim: "this is bottoms-up; the question is whether they can convert PQL to paid without leaving revenue on the table."
- Pricing gated + HubSpot only + no CRM signature = motion-tooling misalignment. Sharp claim: "they're trying to sell enterprise on a mid-market stack; the friction shows up in pipeline conversion."
- Pricing public + no analytics = unusual. Sharp claim: "they're either privacy-first by design (defensible) or running a self-serve motion blind (a real problem); confirm which."

### Available data for {{ domain }}

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
**Pricing & Packaging signal:** not collected.
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
{% else %}
**Tech Stack signal:** not collected.
{% endif %}

{% if raw_pricing_text %}
**Raw pricing page excerpt** (first ~3000 chars — read for FAQ language, tier descriptions, trust signals, customer logos, CTA copy):

```
{{ raw_pricing_text }}
```
{% endif %}

{% if raw_homepage_text %}
**Raw homepage excerpt** (first ~3000 chars — read for hero positioning, sub-hero, customer logos, top nav structure, security badges, footer signals):

```
{{ raw_homepage_text }}
```
{% endif %}

### Your task

Write Section A. Four required components:

1. **3-5 paragraphs of narrative.** Each leads with a sharp claim. Cross-signal reasoning required: surface a contradiction, alignment, or progression across pricing, tech stack, and raw page positioning. State patterns as facts, not opinions. Cite specifics: which tier, which tool, which date, which exact copy from the raw page.

2. **3-5 gap_bullets** naming specific GTM Gaps. Not generic ("no marketing automation detected"). Specific ("the pricing page promises enterprise-grade infrastructure but the security/compliance footer is bare — gap between segment positioning and trust signal").

3. **Final paragraph: the consulting hypothesis.** What would an engaged Revenue Reimagined consultant explore FIRST with this prospect if they became a client? Concrete. Anchored in the data above. Implies a path forward. This paragraph anchors the sales conversation.

4. **3-5 discovery questions.** Wedge questions — the specific hypotheses Revenue Reimagined would open a first call with. Each tied to a finding above. Each starts a real conversation. NOT "what's your rationale for X" boilerplate. Specific to this prospect.

The reader is a CRO who will only finish reading if the first sentence makes them want to. Don't bury the diagnostic.
