"""Temporary mock data for the Email Analyzer module.
This will be replaced by real database queries in future phases."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Dict, Any

MOCK_USERS: List[Dict[str, Any]] = [
    {"id": "ops@evenai.io", "email": "ops@evenai.io", "display_name": "Ops", "mailbox_count": 128},
    {"id": "sales@evenai.io", "email": "sales@evenai.io", "display_name": "Sales", "mailbox_count": 94},
    {"id": "support@evenai.io", "email": "support@evenai.io", "display_name": "Support", "mailbox_count": 210},
]

MOCK_LABELS: List[Dict[str, Any]] = [
    {"label": "priority", "count": 87},
    {"label": "escalation", "count": 42},
    {"label": "vip", "count": 25},
    {"label": "product", "count": 133},
]

_NOW = datetime.utcnow()

MOCK_EMAILS: List[Dict[str, Any]] = [
    {
        "id": "eml-1001",
        "email_id": "eml-1001",
        "thread_id": "thr-445",
        "subject": "GPU coordinator downtime notice",
        "from_addr": "ops@evenai.io",
        "to_addrs": ["cto@customer.com"],
        "labels": ["priority", "ops"],
        "date": (_NOW - timedelta(hours=4)).isoformat() + "Z",
        "text": "Heads up, GPU coordinator recycled at 02:00 UTC. Expect 2m pause per inference job.",
        "participants": ["ops@evenai.io", "cto@customer.com"],
    },
    {
        "id": "eml-1002",
        "email_id": "eml-1002",
        "thread_id": "thr-889",
        "subject": "Customer sentiment weekly rollup",
        "from_addr": "insights@evenai.io",
        "to_addrs": ["sales@evenai.io"],
        "labels": ["report", "product"],
        "date": (_NOW - timedelta(days=1, hours=2)).isoformat() + "Z",
        "text": "Top drivers: onboarding friction and dashboard latency. Attached csv highlights top accounts.",
        "participants": ["insights@evenai.io", "sales@evenai.io"],
    },
    {
        "id": "eml-1003",
        "email_id": "eml-1003",
        "thread_id": "thr-889",
        "subject": "Re: Customer sentiment weekly rollup",
        "from_addr": "sales@evenai.io",
        "to_addrs": ["insights@evenai.io"],
        "labels": ["followup", "vip"],
        "date": (_NOW - timedelta(hours=18)).isoformat() + "Z",
        "text": "Need a call-out on ACME Group – exec escalated. Can we highlight risk score > 80?",
        "participants": ["sales@evenai.io", "insights@evenai.io"],
    },
]

MOCK_SNIPPETS = [
    {
        "context_before": [
            {"speaker": "insights", "text": "Latency is spiking in APAC cluster."}
        ],
        "context_after": [
            {"speaker": "sales", "text": "Customer expects RCA by tomorrow."}
        ],
    }
]

__all__ = ["MOCK_USERS", "MOCK_LABELS", "MOCK_EMAILS", "MOCK_SNIPPETS"]
