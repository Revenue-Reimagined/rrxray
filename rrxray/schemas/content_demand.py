"""Schemas specific to the content_demand collector."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from rrxray.schemas._shared import Finding, SourceCitation

ContentCategory = Literal[
    "thought_leadership",
    "seo_listicle",
    "case_study",
    "product_announcement",
    "founder_essay",
    "tutorial",
    "news_pr",
    "other",
]

LeadMagnetAssetType = Literal[
    "ebook", "whitepaper", "guide", "template", "calculator",
    "report", "webinar",
]


class BlogPost(BaseModel):
    title: str
    url: str | None = None
    author: str | None = None
    published_date: str | None = None     # ISO string; not all blogs surface a date
    category: ContentCategory
    matched_keyword: str | None = None


class LeadMagnet(BaseModel):
    title: str
    asset_type: LeadMagnetAssetType
    url: str | None = None
    has_form_gate: bool = False           # detected form near the CTA = email capture
    source_page: str                      # where on the site we saw it (homepage, blog index)


class ContentDemandData(BaseModel):
    blog_index_url: str | None = None
    blog_posts: list[BlogPost] = []
    post_counts_by_category: dict[str, int] = {}
    most_recent_post_date: str | None = None
    lead_magnets: list[LeadMagnet] = []
    podcast_platform: Literal["apple_podcasts", "spotify", "rss_only"] | None = None
    podcast_name: str | None = None
    newsletter_platform: Literal["substack", "embedded_form"] | None = None
    newsletter_archive_url: str | None = None
    findings: list[Finding] = []
    gaps: list[str] = []
    discovery_questions: list[str] = []
    sources: list[SourceCitation] = []
