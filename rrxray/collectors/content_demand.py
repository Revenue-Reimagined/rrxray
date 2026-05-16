"""content_demand collector: blog cadence + post mix + lead magnets + podcast + newsletter."""
from __future__ import annotations

import json
import logging
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

from rrxray.collectors._content_demand_catalog import (
    CONTENT_KEYWORDS,
    LEAD_MAGNET_CTA_PATTERNS,
    PODCAST_PATTERNS,
    SUBSTACK_PATTERN,
)
from rrxray.schemas._shared import Finding, SourceCitation
from rrxray.schemas.content_demand import BlogPost, ContentDemandData, LeadMagnet

if TYPE_CHECKING:
    from rrxray.context import CollectorContext

NAME = "content_demand"
log = logging.getLogger(f"rrxray.collectors.{NAME}")

CANDIDATE_BLOG_PATHS = ["/blog", "/insights", "/resources", "/news", "/articles", "/learn"]


async def _discover_blog_url(ctx: "CollectorContext"):  # noqa: UP037
    """Try standard blog paths. Return (url, ScrapedPage) or (None, None)."""
    from rrxray.services.firecrawl_client import FirecrawlError
    base = f"https://{ctx.domain}"
    for path in CANDIDATE_BLOG_PATHS:
        url = base + path
        try:
            page = await ctx.firecrawl.scrape_url(url, only_main_content=False)
            html = page.html or ""
            if html.strip() and len(html) > 200:
                return url, page
        except FirecrawlError as e:
            log.debug("blog discover: %s not reachable: %s", url, e)
            continue
    return None, None


_BLOG_LINK_RE = re.compile(
    r'<a[^>]*\bhref=["\']([^"\']+)["\'][^>]*>([^<]+)</a>',
    re.IGNORECASE,
)


def _is_blog_post_href(href: str, base_url: str) -> bool:
    """Return True if href looks like a blog post (sub-path of blog index, not nav)."""
    if not href or href.startswith("#"):
        return False
    full = urljoin(base_url, href)
    parsed = urlparse(full)
    base_parsed = urlparse(base_url)
    if parsed.netloc != base_parsed.netloc:
        return False
    base_path = base_parsed.path.rstrip("/")
    link_path = parsed.path.rstrip("/")
    return link_path != base_path and link_path.startswith(base_path + "/")


# Match <time datetime="2026-04-15"> or <time datetime="2026-04-15T10:00:00Z">
_TIME_DATETIME_RE = re.compile(
    r'<time[^>]*\bdatetime=["\'](\d{4}-\d{2}-\d{2})[^"\']*["\']',
    re.IGNORECASE,
)

# Fallback: match "Month DD, YYYY" or "YYYY-MM-DD" in nearby text
_DATE_TEXT_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2})|"
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}",
    re.IGNORECASE,
)

_AUTHOR_RE = re.compile(
    r'(?:class=["\'][^"\']*author[^"\']*["\']|>By\s+)([^<]+)',
    re.IGNORECASE,
)


def _parse_blog_posts(html: str, base_url: str) -> list[BlogPost]:
    """Extract up to 15 blog posts from HTML.

    Anchor tags are the primary signal. Dates come from a nearby <time
    datetime=...> attribute (preferred) or any "YYYY-MM-DD" / "Month DD, YYYY"
    substring within the surrounding chunk. Author extraction is best-effort.

    Returns first 15 in document order.
    """
    if not html:
        return []

    posts: list[BlogPost] = []
    seen_titles: set[str] = set()

    # Split into rough per-post chunks by anchor positions so we can correlate
    # nearby <time> / author tags with the link above them.
    matches = list(_BLOG_LINK_RE.finditer(html))
    for i, m in enumerate(matches):
        href = m.group(1).strip()
        title = m.group(2).strip()
        if not title or len(title) > 250:
            continue
        if not _is_blog_post_href(href, base_url):
            continue
        if title in seen_titles:
            continue
        seen_titles.add(title)

        # Chunk: from this anchor to the next one (or end of html), used to
        # find date / author near this post.
        chunk_start = m.end()
        chunk_end = matches[i + 1].start() if i + 1 < len(matches) else min(len(html), chunk_start + 1000)
        chunk = html[chunk_start:chunk_end]

        # Date: prefer <time datetime="..."> attribute
        published_date: str | None = None
        time_m = _TIME_DATETIME_RE.search(chunk)
        if time_m:
            published_date = time_m.group(1)
        else:
            date_m = _DATE_TEXT_RE.search(chunk)
            if date_m:
                if date_m.group(1):
                    # Already ISO: "YYYY-MM-DD"
                    published_date = date_m.group(1)
                else:
                    # Textual: "Month DD, YYYY" or "Month DD YYYY" — normalize to ISO
                    raw = date_m.group(0).replace(",", "")
                    try:  # noqa: SIM105 — explicit pass keeps intent obvious
                        published_date = datetime.strptime(raw, "%B %d %Y").strftime("%Y-%m-%d")
                    except ValueError:
                        pass  # Unparseable; leave published_date as None

        # Author: best-effort
        author: str | None = None
        author_m = _AUTHOR_RE.search(chunk)
        if author_m:
            author = author_m.group(1).strip()
            if author.lower().startswith("by "):
                author = author[3:].strip()
            if len(author) > 80:
                author = None

        full_url = urljoin(base_url, href) if href and not href.startswith("#") else None
        posts.append(BlogPost(
            title=title,
            url=full_url,
            author=author,
            published_date=published_date,
            category="other",  # categorization happens later via _categorize_post
            matched_keyword=None,
        ))

        if len(posts) >= 15:
            break

    return posts


# Numeric-prefix SEO listicle pattern: "5 ways", "12 tips", "7 mistakes", etc.
_SEO_NUMERIC_RE = re.compile(
    r"^\s*\d{1,3}\s+(ways|tips|mistakes|reasons|things|tools|strategies|tactics|examples|signs|lessons)\b",
    re.IGNORECASE,
)


def _categorize_post(title: str) -> tuple[str, str | None]:
    """Categorize a post via the keyword catalog.

    Order-by-specificity: CONTENT_KEYWORDS is pre-ordered (SEO listicles
    first, thought leadership last as catch-all). First-match wins.

    A dedicated SEO-listicle numeric-prefix regex runs before the keyword
    catalog so "5 ways to...", "12 tips for..." etc. categorize even when the
    exact substring isn't in the catalog.

    Returns (category, matched_keyword). Falls back to ("other", None).
    """
    haystack = title.lower()

    # SEO listicle numeric-prefix short-circuit
    if _SEO_NUMERIC_RE.search(title):
        return "seo_listicle", "<numeric-prefix>"

    for entry in CONTENT_KEYWORDS:
        for kw in entry["keywords"]:
            if kw.lower() in haystack:
                return entry["category"], kw
    return "other", None


_FORM_NEARBY_RE = re.compile(
    r'<form[^>]*>[\s\S]{0,500}<input[^>]*type=["\']email["\']',
    re.IGNORECASE,
)


def _detect_lead_magnets(html: str, source_page: str) -> list[LeadMagnet]:
    """Scan HTML for lead-magnet CTAs.

    For each CTA-text pattern from LEAD_MAGNET_CTA_PATTERNS, capture the
    surrounding anchor's href + title, infer asset_type from the matched
    pattern, and run a proximity check for a <form> with an email input in
    the same chunk to set has_form_gate.

    Cap: 10 results per call. Dedupe by URL (or title if URL is missing).
    """
    if not html:
        return []

    magnets: list[LeadMagnet] = []
    seen_keys: set[str] = set()

    for entry in LEAD_MAGNET_CTA_PATTERNS:
        asset_type = entry["asset_type"]
        for pattern in entry["patterns"]:
            for m in re.finditer(re.escape(pattern), html, re.IGNORECASE):
                # Capture the anchor surrounding (or just-after) this match
                start = max(0, m.start() - 400)
                end = min(len(html), m.end() + 400)
                window = html[start:end]

                # Prefer an anchor whose text contains the match (so a CTA
                # like "Try the calculator" wins over an unrelated earlier
                # anchor in the same window). Fall back to the first anchor
                # in the window otherwise.
                anchor_re = re.compile(
                    r'<a[^>]*\bhref=["\']([^"\']+)["\'][^>]*>([^<]+)</a>',
                    re.IGNORECASE,
                )
                anchor_m = None
                for cand in anchor_re.finditer(window):
                    if pattern.lower() in cand.group(2).lower():
                        anchor_m = cand
                        break
                if anchor_m is None:
                    anchor_m = anchor_re.search(window)
                if anchor_m:
                    url = anchor_m.group(1).strip()
                    title = anchor_m.group(2).strip()
                else:
                    url = ""
                    # Fall back to nearest <h*> text above the match
                    heading_m = re.search(
                        r"<h[1-6][^>]*>([^<]+)</h[1-6]>", window, re.IGNORECASE,
                    )
                    title = heading_m.group(1).strip() if heading_m else pattern

                if not title or len(title) > 200:
                    continue

                key = url or title.lower()
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                # Form-gate proximity: look forward from the match for a
                # <form> with an email input, but stop at the next section
                # boundary (next <h1-6> or </section>) so we don't bleed
                # into the following lead-magnet's form.
                forward = html[m.end():m.end() + 600]
                boundary_m = re.search(
                    r"</section\s*>|<h[1-6]\b", forward, re.IGNORECASE,
                )
                forward_clipped = (
                    forward[: boundary_m.start()] if boundary_m else forward
                )
                has_form_gate = bool(_FORM_NEARBY_RE.search(forward_clipped))

                magnets.append(LeadMagnet(
                    title=title,
                    asset_type=asset_type,  # type: ignore[arg-type]
                    url=url or None,
                    has_form_gate=has_form_gate,
                    source_page=source_page,
                ))

                if len(magnets) >= 10:
                    return magnets

    return magnets


_RSS_LINK_RE = re.compile(
    r'<link[^>]*\brel=["\']alternate["\'][^>]*\btype=["\']application/rss\+xml["\'][^>]*>',
    re.IGNORECASE,
)

_RSS_TITLE_RE = re.compile(
    r'\btitle=["\']([^"\']+)["\']',
    re.IGNORECASE,
)


def _detect_podcast(homepage_html: str) -> tuple[str | None, str | None]:
    """Detect podcast presence.

    Priority: Apple Podcasts / Spotify URLs (concrete platforms) before
    rss_only. The RSS <link> title attribute provides the podcast name when
    present.

    Returns (platform, name) or (None, None).
    """
    if not homepage_html:
        return None, None

    # Parse the RSS title once (used to enrich any platform match).
    name: str | None = None
    rss_m = _RSS_LINK_RE.search(homepage_html)
    if rss_m:
        title_m = _RSS_TITLE_RE.search(rss_m.group(0))
        if title_m:
            name = title_m.group(1).strip() or None

    for entry in PODCAST_PATTERNS:
        if re.search(entry["url_pattern"], homepage_html, re.IGNORECASE):
            return entry["platform"], name

    if rss_m:
        return "rss_only", name

    return None, None


_NEWSLETTER_BUTTON_RE = re.compile(
    r"<button[^>]*>([^<]*)</button>",
    re.IGNORECASE,
)

_NEWSLETTER_SUBMIT_RE = re.compile(
    r'<input[^>]*\btype=["\']submit["\'][^>]*\bvalue=["\']([^"\']+)["\']'
    r'|<input[^>]*\bvalue=["\']([^"\']+)["\'][^>]*\btype=["\']submit["\']',
    re.IGNORECASE,
)

_NEWSLETTER_KEYWORDS = ("subscribe", "newsletter", "sign up", "sign-up", "signup")


def _detect_newsletter(homepage_html: str) -> tuple[str | None, str | None]:
    """Detect newsletter posture.

    Substack first (concrete platform + archive URL). Otherwise an embedded
    <form> with an email input AND a nearby button whose text contains
    'subscribe', 'newsletter', or 'sign up' counts as embedded_form.

    Returns (platform, archive_url) or (None, None).
    """
    if not homepage_html:
        return None, None

    substack_m = re.search(SUBSTACK_PATTERN, homepage_html, re.IGNORECASE)
    if substack_m:
        subdomain = substack_m.group(1)
        return "substack", f"https://{subdomain}.substack.com"

    # Embedded form heuristic: <form> with <input type="email"> AND a nearby
    # button whose text contains a newsletter keyword.
    for form_m in re.finditer(
        r'<form[\s\S]{0,2000}?</form>', homepage_html, re.IGNORECASE,
    ):
        block = form_m.group(0)
        if not re.search(r'<input[^>]*\btype=["\']email["\']', block, re.IGNORECASE):
            continue
        for btn_m in _NEWSLETTER_BUTTON_RE.finditer(block):
            btn_text = btn_m.group(1).lower()
            if any(kw in btn_text for kw in _NEWSLETTER_KEYWORDS):
                return "embedded_form", None
        for submit_m in _NEWSLETTER_SUBMIT_RE.finditer(block):
            submit_val = (submit_m.group(1) or submit_m.group(2) or "").lower()
            if any(kw in submit_val for kw in _NEWSLETTER_KEYWORDS):
                return "embedded_form", None
        # Heading near the form: check 200 chars before the form for a newsletter cue
        before = homepage_html[max(0, form_m.start() - 200):form_m.start()].lower()
        if any(kw in before for kw in _NEWSLETTER_KEYWORDS):
            return "embedded_form", None

    return None, None


def _compute_post_counts(
    blog_posts: list[BlogPost],
) -> tuple[dict[str, int], str | None]:
    """Aggregate counts per category and derive the most recent ISO date.

    Dates that don't parse as YYYY-MM-DD are ignored when computing
    most_recent_post_date (but the original string remains on the BlogPost).
    """
    counts: dict[str, int] = {}
    for p in blog_posts:
        counts[p.category] = counts.get(p.category, 0) + 1

    iso_dates: list[date] = []
    for p in blog_posts:
        if not p.published_date:
            continue
        try:
            iso_dates.append(date.fromisoformat(p.published_date))
        except ValueError:
            continue

    most_recent = max(iso_dates).isoformat() if iso_dates else None
    return counts, most_recent


def _emit_findings(
    domain: str,
    blog_index_url: str | None,
    blog_posts: list[BlogPost],
    post_counts: dict[str, int],
    most_recent_date: str | None,
    lead_magnets: list[LeadMagnet],
    podcast: tuple[str | None, str | None],
    newsletter: tuple[str | None, str | None],
) -> tuple[list[Finding], list[str], list[str]]:
    """Rule-based findings/gaps/questions for content posture. No LLM."""
    now = datetime.now(UTC)
    source_url = blog_index_url or f"https://{domain}"
    findings: list[Finding] = []
    gaps: list[str] = []
    questions: list[str] = []

    # No detectable content anywhere
    if (
        not blog_posts
        and not lead_magnets
        and podcast[0] is None
        and newsletter[0] is None
    ):
        findings.append(Finding(
            text=(
                f"No blog, lead magnets, podcast, or newsletter detected on {domain}. "
                f"Pipeline does not appear to run through content channels; the GTM "
                f"motion looks relationship-led or outbound-only."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))
        questions.append(
            "We did not detect a public content surface (blog, lead magnets, podcast, "
            "or newsletter). How does your GTM generate top-of-funnel demand today: "
            "outbound, referral, paid, or events?"
        )
        return findings, gaps, questions

    total_posts = len(blog_posts)
    podcast_platform, podcast_name = podcast
    newsletter_platform, _newsletter_archive = newsletter

    # Stale / dormant blog (most recent post > 90 days old)
    if most_recent_date:
        try:
            recent = date.fromisoformat(most_recent_date)
            # Both sides are naive date objects; tz-agnostic comparison is intentional
            days_since = (now.date() - recent).days
            if days_since > 90:
                findings.append(Finding(
                    text=(
                        f"Most recent blog post is from {most_recent_date} "
                        f"({days_since} days ago). Content function appears "
                        f"de-prioritized; check whether the team pivoted off "
                        f"content as a channel or simply defunded it."
                    ),
                    source=SourceCitation(url=source_url, timestamp=now),
                ))
                questions.append(
                    f"Your most recent blog post is from {most_recent_date}. "
                    "Was content de-prioritized intentionally, or did the function "
                    "shift to a different surface (newsletter, podcast, social)?"
                )
        except ValueError:
            pass

    # SEO-dominant content mix
    if total_posts > 0:
        seo_count = post_counts.get("seo_listicle", 0)
        if seo_count / total_posts >= 0.5 and seo_count >= 5:
            findings.append(Finding(
                text=(
                    f"Content mix is SEO-dominant ({seo_count} of {total_posts} "
                    f"posts are listicles). This pattern matches a top-of-funnel "
                    f"content shop or outsourced SEO supplement, often paired "
                    f"with paid acquisition rather than sales-led pipeline."
                ),
                source=SourceCitation(url=source_url, timestamp=now),
            ))

    # Thought leadership dominant
    if total_posts > 0:
        tl_count = post_counts.get("thought_leadership", 0)
        if tl_count / total_posts >= 0.5 and tl_count >= 3:
            findings.append(Finding(
                text=(
                    f"Content mix skews to thought leadership "
                    f"({tl_count} of {total_posts}). Signals enterprise positioning "
                    f"and sales-led brand-building, not a paid-acquisition motion."
                ),
                source=SourceCitation(url=source_url, timestamp=now),
            ))

    # Founder essay dominant
    if total_posts > 0:
        fe_count = post_counts.get("founder_essay", 0)
        if fe_count / total_posts >= 0.4 and fe_count >= 3:
            findings.append(Finding(
                text=(
                    f"{fe_count} of {total_posts} posts are founder essays. "
                    f"Personal-brand distribution rather than corporate content "
                    f"funnel; common in early-stage / niche-positioning plays."
                ),
                source=SourceCitation(url=source_url, timestamp=now),
            ))

    # Lead-magnet posture
    if blog_posts and not lead_magnets:
        gaps.append(
            "Blog publishing without any visible lead magnets. Content is "
            "trust-building only; conversion either happens via sales channels "
            "or pipeline does not run through email capture."
        )
        questions.append(
            "Your blog is active but we did not find any gated lead magnets. "
            "Is content meant to drive pipeline, or is it positioning-only?"
        )
    elif len(lead_magnets) >= 5:
        findings.append(Finding(
            text=(
                f"{len(lead_magnets)} lead magnets visible. Funnel-driven "
                f"email-capture motion; typically pairs with marketing-automation "
                f"in the tech stack (HubSpot / Marketo / Pardot)."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))

    # Podcast signal
    if podcast_platform:
        findings.append(Finding(
            text=(
                f"Podcast detected ({podcast_platform}"
                f"{f', {podcast_name}' if podcast_name else ''}). "
                f"Often signals brand-category investment and ABM-adjacent "
                f"positioning; pairs with thought leadership when both are present."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))

    # Newsletter signal
    if newsletter_platform == "substack":
        findings.append(Finding(
            text=(
                "Substack newsletter detected. Founder-direct distribution "
                "model rather than corporate funnel; usually a personal-brand "
                "or niche-positioning play."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))
    elif newsletter_platform == "embedded_form":
        findings.append(Finding(
            text=(
                "Embedded newsletter signup detected. Corporate-newsletter shape "
                "(captures email for ongoing nurture), typical of marketing-automation "
                "funnel rather than founder-direct distribution."
            ),
            source=SourceCitation(url=source_url, timestamp=now),
        ))

    return findings, gaps, questions


def _write_evidence(
    evidence_dir: Path,
    homepage_html: str,
    blog_html: str | None,
    lead_magnets: list[LeadMagnet],
    podcast: tuple[str | None, str | None],
    newsletter: tuple[str | None, str | None],
    blog_posts: list[BlogPost],
    post_counts: dict[str, int],
    most_recent_date: str | None,
) -> None:
    """Write raw HTML + structured summary to the evidence dir."""
    evidence_dir.mkdir(parents=True, exist_ok=True)
    # Clean stale evidence from prior runs
    for stale in evidence_dir.glob("*.html"):
        stale.unlink()
    for stale in evidence_dir.glob("*.json"):
        stale.unlink()

    if homepage_html:
        (evidence_dir / "homepage.html").write_text(homepage_html, encoding="utf-8")
    if blog_html:
        (evidence_dir / "blog.html").write_text(blog_html, encoding="utf-8")
    (evidence_dir / "lead_magnets.json").write_text(
        json.dumps([m.model_dump() for m in lead_magnets], indent=2),
        encoding="utf-8",
    )
    summary = {
        "blog_posts": [p.model_dump() for p in blog_posts],
        "post_counts_by_category": post_counts,
        "most_recent_post_date": most_recent_date,
        "podcast_platform": podcast[0],
        "podcast_name": podcast[1],
        "newsletter_platform": newsletter[0],
        "newsletter_archive_url": newsletter[1],
    }
    (evidence_dir / "content_demand_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8",
    )


async def collect(ctx) -> ContentDemandData:
    """Scrape homepage + blog, run categorization + detection, emit findings."""
    from rrxray.services.firecrawl_client import FirecrawlError

    now = datetime.now(UTC)
    homepage_url = f"https://{ctx.domain}"

    # Homepage scrape (best-effort; needed for podcast/newsletter detection)
    homepage_html = ""
    try:
        homepage_page = await ctx.firecrawl.scrape_url(homepage_url, only_main_content=False)
        homepage_html = (homepage_page.html or "") if homepage_page else ""
    except FirecrawlError as e:
        log.warning("homepage scrape failed for %s: %s", homepage_url, e)

    # Blog discovery + scrape (best-effort)
    blog_url, blog_page = await _discover_blog_url(ctx)
    blog_html = (blog_page.html if blog_page else "") or ""

    # Parse + categorize blog posts
    blog_posts: list[BlogPost] = []
    if blog_html:
        parsed = _parse_blog_posts(blog_html, base_url=blog_url or homepage_url)
        for p in parsed:
            category, matched = _categorize_post(p.title)
            blog_posts.append(BlogPost(
                title=p.title,
                url=p.url,
                author=p.author,
                published_date=p.published_date,
                category=category,  # type: ignore[arg-type]
                matched_keyword=matched,
            ))

    # Lead magnet detection (homepage + blog index combined; capped to 10)
    homepage_magnets = _detect_lead_magnets(homepage_html, source_page="homepage")
    blog_magnets = _detect_lead_magnets(blog_html, source_page="blog_index")
    lead_magnets: list[LeadMagnet] = []
    seen_keys: set[str] = set()
    for lm in homepage_magnets + blog_magnets:
        key = lm.url or lm.title.lower()
        if key in seen_keys:
            continue
        seen_keys.add(key)
        lead_magnets.append(lm)
        if len(lead_magnets) >= 10:
            break

    # Podcast + newsletter (homepage only)
    podcast = _detect_podcast(homepage_html)
    newsletter = _detect_newsletter(homepage_html)

    # Aggregate
    post_counts, most_recent_date = _compute_post_counts(blog_posts)

    # Findings
    findings, gaps, questions = _emit_findings(
        domain=ctx.domain,
        blog_index_url=blog_url,
        blog_posts=blog_posts,
        post_counts=post_counts,
        most_recent_date=most_recent_date,
        lead_magnets=lead_magnets,
        podcast=podcast,
        newsletter=newsletter,
    )

    # Evidence
    _write_evidence(
        ctx.evidence_dir / NAME,
        homepage_html,
        blog_html if blog_html else None,
        lead_magnets,
        podcast,
        newsletter,
        blog_posts,
        post_counts,
        most_recent_date,
    )

    # Source citations
    sources = []
    if blog_url:
        sources.append(SourceCitation(
            url=blog_url, timestamp=now,
            evidence_path=str(
                (ctx.evidence_dir / NAME / "blog.html").relative_to(ctx.evidence_dir)
            ) if blog_html else None,
        ))
    if homepage_html:
        sources.append(SourceCitation(
            url=homepage_url, timestamp=now,
            evidence_path=str(
                (ctx.evidence_dir / NAME / "homepage.html").relative_to(ctx.evidence_dir)
            ),
        ))

    return ContentDemandData(
        blog_index_url=blog_url,
        blog_posts=blog_posts,
        post_counts_by_category=post_counts,
        most_recent_post_date=most_recent_date,
        lead_magnets=lead_magnets,
        podcast_platform=podcast[0],  # type: ignore[arg-type]
        podcast_name=podcast[1],
        newsletter_platform=newsletter[0],  # type: ignore[arg-type]
        newsletter_archive_url=newsletter[1],
        findings=findings,
        gaps=gaps,
        discovery_questions=questions,
        sources=sources,
    )
