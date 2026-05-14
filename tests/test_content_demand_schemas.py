"""ContentDemandData / BlogPost / LeadMagnet schema round-trip + validation."""
import json

import pytest
from pydantic import ValidationError

from rrxray.schemas.content_demand import (  # noqa: F401
    BlogPost,
    ContentCategory,
    ContentDemandData,
    LeadMagnet,
    LeadMagnetAssetType,
)


def test_blog_post_minimal():
    p = BlogPost(title="The Future of B2B Sales", category="thought_leadership")
    assert p.title == "The Future of B2B Sales"
    assert p.category == "thought_leadership"
    assert p.url is None
    assert p.author is None
    assert p.published_date is None
    assert p.matched_keyword is None


def test_blog_post_rejects_invalid_category():
    with pytest.raises(ValidationError):
        BlogPost(title="x", category="not_a_category")  # type: ignore[arg-type]


def test_lead_magnet_minimal():
    lm = LeadMagnet(title="The 2026 Sales Playbook", asset_type="ebook", source_page="homepage")
    assert lm.title == "The 2026 Sales Playbook"
    assert lm.asset_type == "ebook"
    assert lm.source_page == "homepage"
    assert lm.has_form_gate is False
    assert lm.url is None


def test_lead_magnet_rejects_invalid_asset_type():
    with pytest.raises(ValidationError):
        LeadMagnet(title="x", asset_type="not_a_type", source_page="homepage")  # type: ignore[arg-type]


def test_content_demand_data_defaults_empty():
    d = ContentDemandData()
    assert d.blog_index_url is None
    assert d.blog_posts == []
    assert d.post_counts_by_category == {}
    assert d.most_recent_post_date is None
    assert d.lead_magnets == []
    assert d.podcast_platform is None
    assert d.podcast_name is None
    assert d.newsletter_platform is None
    assert d.newsletter_archive_url is None
    assert d.findings == []
    assert d.gaps == []
    assert d.discovery_questions == []
    assert d.sources == []


def test_content_demand_data_round_trips():
    d = ContentDemandData(
        blog_index_url="https://example.com/blog",
        blog_posts=[
            BlogPost(title="Why I Built X", category="founder_essay"),
            BlogPost(title="10 ways to close more deals", category="seo_listicle"),
        ],
        post_counts_by_category={"founder_essay": 1, "seo_listicle": 1},
        most_recent_post_date="2026-04-15",
        lead_magnets=[
            LeadMagnet(title="The Playbook", asset_type="ebook", source_page="homepage", has_form_gate=True),
        ],
        podcast_platform="apple_podcasts",
        podcast_name="The Revenue Show",
        newsletter_platform="substack",
        newsletter_archive_url="https://example.substack.com",
    )
    serialized = d.model_dump_json()
    restored = ContentDemandData.model_validate(json.loads(serialized))
    assert restored.blog_index_url == "https://example.com/blog"
    assert len(restored.blog_posts) == 2
    assert restored.lead_magnets[0].has_form_gate is True
    assert restored.podcast_platform == "apple_podcasts"
    assert restored.newsletter_platform == "substack"
