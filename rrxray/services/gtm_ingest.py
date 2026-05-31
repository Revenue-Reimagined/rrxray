"""gtm_ingest service: builds and posts completed X-Ray reports to gtmfoundations ingestion endpoint."""

from __future__ import annotations

import asyncio
import logging

import httpx

from rrxray.config import Config
from rrxray.schemas.data import XrayData

log = logging.getLogger("rrxray.gtm_ingest")


def build_ingestion_payload(config: Config, data: XrayData, markdown_content: str) -> dict:
    """Builds the ingestion payload from XrayData and rendered Markdown content.

    Complies with the GTM Foundations X-Ray Ingestion Contract.
    """
    # 1. Map sources and build url_to_index
    url_to_index = {}
    sources_payload = []
    for idx, source in enumerate(data.sources):
        url_to_index[source.url] = idx
        sources_payload.append(
            {
                "index": idx,
                "url": source.url,
                "extracted_at": source.timestamp.isoformat()
                if hasattr(source.timestamp, "isoformat")
                else str(source.timestamp),
                "content_summary": None,
            }
        )

    # 2. Map synthesizers (observed_gtm_motion and observed_stability_trajectory)
    observed_gtm_motion_payload = None
    if data.synthesizers.observed_gtm_motion:
        motion = data.synthesizers.observed_gtm_motion
        observed_gtm_motion_payload = {
            "narrative_paragraphs": motion.narrative_paragraphs,
            "gap_bullets": motion.gap_bullets,
            "findings": [{"text": f.text, "source_index": url_to_index.get(f.source.url, 0)} for f in motion.findings],
            "gaps": motion.gaps,
            "discovery_questions": motion.discovery_questions,
        }

    observed_stability_trajectory_payload = None
    if data.synthesizers.observed_stability_trajectory:
        stab = data.synthesizers.observed_stability_trajectory
        observed_stability_trajectory_payload = {
            "narrative_paragraphs": stab.narrative_paragraphs,
            "findings": [{"text": f.text, "source_index": url_to_index.get(f.source.url, 0)} for f in stab.findings],
            "gaps": stab.gaps,
            "discovery_questions": stab.discovery_questions,
        }

    # 3. Map collectors_data
    collectors_data = {
        "pricing_packaging": data.collectors.pricing_packaging.model_dump()
        if data.collectors.pricing_packaging
        else None,
        "tech_stack": data.collectors.tech_stack.model_dump() if data.collectors.tech_stack else None,
        "revenue_motion": data.collectors.revenue_motion.model_dump() if data.collectors.revenue_motion else None,
        "content_demand": data.collectors.content_demand.model_dump() if data.collectors.content_demand else None,
        "leadership_stability": data.collectors.leadership_stability.model_dump()
        if data.collectors.leadership_stability
        else None,
        "funding_trajectory": data.collectors.funding_trajectory.model_dump()
        if data.collectors.funding_trajectory
        else None,
        "positioning_drift": data.collectors.positioning_drift.model_dump()
        if data.collectors.positioning_drift
        else None,
    }

    # 4. Read evidence files under config.evidence_dir
    evidence_payload = []
    for source in data.sources:
        if source.evidence_path:
            evidence_file_path = config.evidence_dir / source.evidence_path
            if evidence_file_path.is_file():
                try:
                    content = evidence_file_path.read_text(encoding="utf-8", errors="ignore")
                    evidence_payload.append(
                        {
                            "url": source.url,
                            "title": source.evidence_path.split("/")[-1]
                            if "/" in source.evidence_path
                            else source.evidence_path,
                            "type": "WAYBACK"
                            if "wayback" in source.evidence_path.lower()
                            else (
                                "PDL_ENRICHMENT"
                                if "pdl" in source.evidence_path.lower() or "leadership" in source.evidence_path.lower()
                                else "WEB_CRAWL"
                            ),
                            "content": content,
                            "extracted_at": source.timestamp.isoformat()
                            if hasattr(source.timestamp, "isoformat")
                            else str(source.timestamp),
                        }
                    )
                except Exception as e:
                    log.warning("Could not read evidence file %s: %s", evidence_file_path, e)

    # 5. Build full payload
    run_timestamp = data.run_metadata.timestamp
    run_id = f"xray_run_{run_timestamp.strftime('%Y%m%dT%H%M%SZ')}_{data.domain.replace('.', '_')}"

    payload = {
        "run_id": run_id,
        "domain": data.domain,
        "company_name": data.company_name or data.domain.split(".")[0].capitalize(),
        "company_logo": None,
        "metadata": {
            "submitted_by": {
                "first_name": config.gtm_submitter_first_name,
                "last_name": config.gtm_submitter_last_name,
                "email": config.gtm_submitter_email,
            },
            "timestamp": run_timestamp.isoformat() if hasattr(run_timestamp, "isoformat") else str(run_timestamp),
            "tool_version": data.run_metadata.tool_version,
            "model_used": data.run_metadata.model_used,
        },
        "report": {
            "observed_gtm_motion": observed_gtm_motion_payload,
            "observed_stability_trajectory": observed_stability_trajectory_payload,
            "markdown_content": markdown_content,
        },
        "collectors_data": collectors_data,
        "sources": sources_payload,
    }
    if evidence_payload:
        payload["evidence"] = evidence_payload

    return payload


async def post_ingestion_payload(config: Config, payload: dict) -> bool:
    """Posts payload to gtmfoundations ingestion endpoint.

    Returns True if successful, False if failed.
    If gtm_ingest_strict is True, raises exception on failure.
    """
    if not config.gtm_ingest_enabled:
        log.info("GTM ingestion integration is disabled.")
        return False

    url = config.gtm_ingest_url
    if not url:
        msg = "GTM Ingestion integration enabled but GTM_INGEST_URL is not configured."
        log.error(msg)
        if config.gtm_ingest_strict:
            raise ValueError(msg)
        return False

    headers = {
        "Content-Type": "application/json",
    }
    if config.gtm_ingest_token:
        headers["Authorization"] = f"Bearer {config.gtm_ingest_token.get_secret_value()}"

    # Merge custom headers from configuration
    if config.gtm_ingest_headers:
        headers.update(config.gtm_ingest_headers)

    log.info("Posting completed X-Ray report payload to %s", url)

    attempts = 3
    timeout = 30.0

    async with httpx.AsyncClient() as client:
        for attempt in range(1, attempts + 1):
            try:
                response = await client.post(url, json=payload, headers=headers, timeout=timeout)
                if response.status_code in (200, 201):
                    log.info(
                        "Successfully posted X-Ray report to gtmfoundations on attempt %d: Status %d",
                        attempt,
                        response.status_code,
                    )
                    try:
                        resp_data = response.json()
                        log.info("GTM response: %s", resp_data)
                    except Exception:
                        pass
                    return True
                else:
                    log.warning(
                        "Attempt %d: Failed to post X-Ray report. Status: %d, Response: %r",
                        attempt,
                        response.status_code,
                        response.text[:200],
                    )
            except Exception as e:
                log.warning("Attempt %d: Error posting X-Ray report: %s", attempt, str(e))
                if attempt == attempts:
                    msg = f"Failed to post X-Ray report to gtmfoundations after {attempts} attempts."
                    log.error(msg)
                    if config.gtm_ingest_strict:
                        raise RuntimeError(msg) from e
                    return False
            # Wait with exponential backoff before next attempt
            if attempt < attempts:
                await asyncio.sleep(2**attempt)

    return False
