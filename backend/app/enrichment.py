from ipaddress import ip_address


OFFLINE_IP_INTEL = {
    "203.0.113.42": {"reputation": "malicious-simulated", "asn": "AS64500", "country": "ZZ"},
    "198.51.100.23": {"reputation": "suspicious-simulated", "asn": "AS64501", "country": "ZZ"},
}
OFFLINE_DOMAINS = {
    "login-example.invalid": {"category": "newly-registered-simulated", "first_seen": "2026-09-29"},
}


def enrich(source_ip: str | None, domain: str | None, username: str | None, asset: str | None) -> dict:
    ip_context = None
    if source_ip:
        try:
            parsed_ip = ip_address(source_ip)
            ip_context = OFFLINE_IP_INTEL.get(str(parsed_ip), {"reputation": "unknown", "scope": "synthetic-lab"})
        except ValueError:
            ip_context = {"reputation": "invalid-address"}
    return {
        "ip": ip_context,
        "domain": OFFLINE_DOMAINS.get((domain or "").lower(), {"category": "unknown"}),
        "user": {"name": username, "department": "engineering-simulated" if username else None},
        "asset": {"name": asset, "criticality": "high-simulated" if asset and "prod" in asset.lower() else "standard"},
    }