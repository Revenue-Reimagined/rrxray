"""Tool-detection signatures for the tech_stack collector.

Each entry is a dict with:
- tool: display name (e.g., "HubSpot")
- category: one of CATEGORIES below
- id: stable identifier for audit (e.g., "hubspot:strict_js")
- pattern: Python regex; matched case-insensitively against scraped HTML
- confidence: "high" (specific signature, near-zero false-positive rate) or "low"
              (loose heuristic that may catch installations missed by strict patterns)

Adding a tool: append a dict to SIGNATURES. Tests will catch regex errors,
duplicate ids, and invalid categories at import-time.
"""
from __future__ import annotations

CATEGORIES: list[str] = [
    "analytics",
    "tag_manager",
    "marketing_automation",
    "chat",
    "product_analytics",
    "crm",
    "cdp",
    "ab_testing",
    "attribution",
]


SIGNATURES: list[dict[str, str]] = [
    # ---- analytics ----
    {"tool": "Google Analytics 4", "category": "analytics", "id": "ga4:strict_gtag",
     "pattern": r"\bgtag\s*\(\s*['\"]config['\"]\s*,\s*['\"]G-[A-Z0-9]+['\"]",
     "confidence": "high"},
    {"tool": "Google Analytics 4", "category": "analytics", "id": "ga4:loose_id",
     "pattern": r"\bG-[A-Z0-9]{6,12}\b", "confidence": "low"},
    {"tool": "Mixpanel", "category": "analytics", "id": "mixpanel:strict_lib",
     "pattern": r"cdn\.mxpnl\.com/libs/mixpanel-[0-9.]+\.min\.js", "confidence": "high"},
    {"tool": "Amplitude", "category": "analytics", "id": "amplitude:strict_lib",
     "pattern": r"cdn\.amplitude\.com/(?:libs/)?amplitude(?:-analytics)?[-./0-9a-z]*\.js",
     "confidence": "high"},
    {"tool": "Plausible", "category": "analytics", "id": "plausible:strict_script",
     "pattern": r"plausible\.io/js/(?:plausible|script)\.[a-z0-9.-]+\.js", "confidence": "high"},
    {"tool": "Fathom", "category": "analytics", "id": "fathom:strict_script",
     "pattern": r"cdn\.usefathom\.com/script\.js", "confidence": "high"},

    # ---- tag_manager ----
    {"tool": "Google Tag Manager", "category": "tag_manager", "id": "gtm:strict_dataLayer",
     "pattern": r"googletagmanager\.com/gtm\.js\?id=GTM-[A-Z0-9]+", "confidence": "high"},
    {"tool": "Google Tag Manager", "category": "tag_manager", "id": "gtm:loose_id",
     "pattern": r"\bGTM-[A-Z0-9]{6,8}\b", "confidence": "low"},
    {"tool": "Tealium", "category": "tag_manager", "id": "tealium:strict_lib",
     "pattern": r"tags\.tiqcdn\.com/utag/[a-z0-9_-]+/[a-z0-9_-]+/[a-z0-9_-]+/utag\.js",
     "confidence": "high"},

    # ---- marketing_automation ----
    {"tool": "HubSpot", "category": "marketing_automation", "id": "hubspot:strict_js",
     "pattern": r"js\.hs-scripts\.com/\d+\.js", "confidence": "high"},
    {"tool": "HubSpot", "category": "marketing_automation", "id": "hubspot:loose_form",
     "pattern": r"hsforms\.net|hsforms\.com|hubspot\.com/forms", "confidence": "low"},
    {"tool": "Marketo", "category": "marketing_automation", "id": "marketo:strict_munchkin",
     "pattern": r"munchkin\.marketo\.net/munchkin\.js", "confidence": "high"},
    {"tool": "Marketo", "category": "marketing_automation", "id": "marketo:loose_form",
     "pattern": r"\bMktoForms2\b", "confidence": "low"},
    {"tool": "Pardot", "category": "marketing_automation", "id": "pardot:strict_pi",
     "pattern": r"pi\.pardot\.com/pd\.js|go\.pardot\.com", "confidence": "high"},
    {"tool": "ActiveCampaign", "category": "marketing_automation", "id": "activecampaign:strict",
     "pattern": r"trackcmp\.net/visit\?actid=", "confidence": "high"},

    # ---- chat ----
    {"tool": "Intercom", "category": "chat", "id": "intercom:strict_widget",
     "pattern": r"widget\.intercom\.io/widget/[a-z0-9]+", "confidence": "high"},
    {"tool": "Intercom", "category": "chat", "id": "intercom:loose_settings",
     "pattern": r"\bintercomSettings\b", "confidence": "low"},
    {"tool": "Drift", "category": "chat", "id": "drift:strict_js",
     "pattern": r"js\.driftt?\.com/include/[A-Za-z0-9_]+/[a-z0-9]+\.js", "confidence": "high"},
    {"tool": "Drift", "category": "chat", "id": "drift:loose_global",
     "pattern": r"\bwindow\.drift\b|drift\.load\(", "confidence": "low"},
    {"tool": "Zendesk Chat", "category": "chat", "id": "zendesk_chat:strict_widget",
     "pattern": r"static\.zdassets\.com/ekr/snippet\.js", "confidence": "high"},
    {"tool": "Crisp", "category": "chat", "id": "crisp:strict_lib",
     "pattern": r"client\.crisp\.chat/l\.js", "confidence": "high"},

    # ---- product_analytics ----
    {"tool": "Pendo", "category": "product_analytics", "id": "pendo:strict_agent",
     "pattern": r"cdn\.pendo\.io/agent/static/[a-f0-9-]+/pendo\.js", "confidence": "high"},
    {"tool": "Pendo", "category": "product_analytics", "id": "pendo:loose_init",
     "pattern": r"\bpendo\.initialize\(", "confidence": "low"},
    {"tool": "Heap", "category": "product_analytics", "id": "heap:strict_lib",
     "pattern": r"cdn\.heapanalytics\.com/js/heap-\d+\.js", "confidence": "high"},
    {"tool": "FullStory", "category": "product_analytics", "id": "fullstory:strict_lib",
     "pattern": r"edge\.fullstory\.com/s/fs\.js", "confidence": "high"},
    {"tool": "LogRocket", "category": "product_analytics", "id": "logrocket:strict_lib",
     "pattern": r"cdn\.lr-(?:in|ingest)\.com/LogRocket\.min\.js|cdn\.logrocket\.io",
     "confidence": "high"},

    # ---- crm ----
    {"tool": "Salesforce Web-to-Lead", "category": "crm", "id": "sfdc:strict_w2l",
     "pattern": r"webto\.salesforce\.com/servlet/servlet\.WebToLead",
     "confidence": "high"},
    {"tool": "HubSpot CRM", "category": "crm", "id": "hubspot_crm:loose_meetings",
     "pattern": r"meetings\.hubspot\.com|app\.hubspot\.com/meetings", "confidence": "low"},

    # ---- cdp ----
    {"tool": "Segment", "category": "cdp", "id": "segment:strict_analytics",
     "pattern": r"cdn\.segment\.com/analytics\.js/v1/[A-Za-z0-9]+/analytics\.min\.js",
     "confidence": "high"},
    {"tool": "Segment", "category": "cdp", "id": "segment:loose_global",
     "pattern": r"\banalytics\.load\(\s*['\"][A-Za-z0-9]+['\"]", "confidence": "low"},
    {"tool": "Rudderstack", "category": "cdp", "id": "rudderstack:strict_lib",
     "pattern": r"cdn\.rudderlabs\.com/v1\.\d+/rudder-analytics\.min\.js",
     "confidence": "high"},

    # ---- ab_testing ----
    {"tool": "Optimizely", "category": "ab_testing", "id": "optimizely:strict_lib",
     "pattern": r"cdn\.optimizely\.com/js/\d+\.js", "confidence": "high"},
    {"tool": "VWO", "category": "ab_testing", "id": "vwo:strict_lib",
     "pattern": r"dev\.visualwebsiteoptimizer\.com/lib/\d+\.js", "confidence": "high"},
    {"tool": "LaunchDarkly", "category": "ab_testing", "id": "launchdarkly:strict_lib",
     "pattern": r"app\.launchdarkly\.com/snippet/ldclient", "confidence": "high"},

    # ---- attribution ----
    {"tool": "Demandbase", "category": "attribution", "id": "demandbase:strict_lib",
     "pattern": r"tag\.demandbase\.com/[A-Za-z0-9_]+\.min\.js", "confidence": "high"},
    {"tool": "6sense", "category": "attribution", "id": "sixsense:strict_lib",
     "pattern": r"j\.6sc\.co/[A-Za-z0-9_]+\.js", "confidence": "high"},
    {"tool": "Bizible", "category": "attribution", "id": "bizible:strict_lib",
     "pattern": r"cdn\.bizible\.com/scripts/bizible\.js", "confidence": "high"},
    {"tool": "Clearbit Reveal", "category": "attribution", "id": "clearbit:strict_reveal",
     "pattern": r"x\.clearbitjs\.com/v\d+/clearbit\.js", "confidence": "high"},
]
