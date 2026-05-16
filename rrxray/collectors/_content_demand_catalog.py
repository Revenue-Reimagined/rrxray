"""Content-category and lead-magnet / podcast / newsletter detection catalogs.

Hardcoded keyword lists for deterministic categorization. Order matters: more
specific patterns appear first so they beat generic ones (e.g., SEO listicles
match before generic thought leadership).

Adding a content category keyword: append a dict to CONTENT_KEYWORDS at the
appropriate priority position.

Adding a podcast platform: append a dict to PODCAST_PATTERNS with platform +
url_pattern (regex).
"""
from __future__ import annotations

CONTENT_CATEGORIES: list[str] = [
    "thought_leadership",
    "seo_listicle",
    "case_study",
    "product_announcement",
    "founder_essay",
    "tutorial",
    "news_pr",
    "other",
]


# Order matters: more specific titles checked first
CONTENT_KEYWORDS: list[dict] = [
    # SEO listicles - very specific patterns. The numeric prefixes are checked
    # via a dedicated regex in addition to these substrings, since "5 ways to"
    # and "10 ways to" should both match without enumerating every integer.
    {"category": "seo_listicle", "keywords": [
        "top 10", "top 5", "top 7", "best 10", "best of",
        "the ultimate guide to", "the complete guide to",
        " ways to ", " tips for ", " mistakes to avoid",
    ]},

    # Case studies - distinct framing
    {"category": "case_study", "keywords": [
        "case study", "customer story", "how we helped",
        "customer spotlight", "success story", "results with",
    ]},

    # Product announcements
    {"category": "product_announcement", "keywords": [
        "introducing", "announcing", "now available", "new feature",
        "we shipped", "release notes", "what's new in",
        "product update", "general availability", "ga release",
    ]},

    # Tutorials
    {"category": "tutorial", "keywords": [
        "how to ", "step by step", "step-by-step", "tutorial",
        "getting started with", "quickstart", "the basics of",
        "walkthrough", "in 5 minutes", "in 10 minutes",
    ]},

    # News / PR
    {"category": "news_pr", "keywords": [
        "raises ", "raised ", "series a", "series b", "series c",
        "named to", "wins ", "award", "named a", "recognized as",
        "partnership with", "acquired", "acquires",
    ]},

    # Founder essay (single-author opinion pieces)
    {"category": "founder_essay", "keywords": [
        "why i ", "what i ", "the case for ", "the case against ",
        "lessons learned", "from the ceo", "from the founder",
        "my take on", "an open letter to",
    ]},

    # Thought leadership (catch-all for long-form expert content)
    {"category": "thought_leadership", "keywords": [
        "the future of", "the state of", "rethinking ", "the new ",
        "framework", "playbook", "deep dive into",
        "what we learned", "research:", "data on",
    ]},
]


# Lead magnet detection: CTA-text patterns paired with asset-type inference
LEAD_MAGNET_CTA_PATTERNS: list[dict] = [
    {"asset_type": "ebook",       "patterns": ["download the ebook", "free ebook", "the ebook"]},
    {"asset_type": "whitepaper",  "patterns": ["download the whitepaper", "white paper", "whitepaper"]},
    {"asset_type": "guide",       "patterns": ["the guide", "free guide", "download the guide", "complete guide"]},
    {"asset_type": "template",    "patterns": ["free template", "the template", "download template"]},
    {"asset_type": "calculator",  "patterns": ["calculator", "roi calculator", "cost calculator"]},
    {"asset_type": "report",      "patterns": ["the report", "free report", "download the report", "state of"]},
    {"asset_type": "webinar",     "patterns": ["register for", "watch the webinar", "on-demand webinar", "live webinar"]},
]


# Podcast detection patterns
PODCAST_PATTERNS: list[dict[str, str]] = [
    {"platform": "apple_podcasts", "url_pattern": r"podcasts\.apple\.com/[a-z]+/podcast/[^\s\"']+"},
    {"platform": "spotify",        "url_pattern": r"open\.spotify\.com/show/[a-zA-Z0-9]+"},
]


# Newsletter detection
SUBSTACK_PATTERN = r"([a-z0-9-]+)\.substack\.com"
