# rrxray

Revenue Reimagined GTM X-Ray: externally-sourced GTM diagnostic for B2B prospects.

**Phase 1 (current):** Foundation. Pricing-packaging collector wired through Section A synthesizer to internal-mode Markdown report. Other modules and modes ship in Phase 2-4.

## Install

```bash
uv sync
```

## Run

Set `ANTHROPIC_API_KEY` and `FIRECRAWL_API_KEY` in env or `.env`, then:

```bash
uv run rrxray run --domain example.com
```

## Test

```bash
uv run pytest
```

See `docs/superpowers/specs/` for the design spec and `docs/superpowers/plans/` for the implementation plan.
