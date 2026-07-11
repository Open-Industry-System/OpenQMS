"""D3 Containment Risk Mappings Registry (US-E2E-01.1 Task 2)

Risk mapping from CAPA severity to risk level for D3 containment analysis.
Each version defines a mapping: {capa_severity} -> {risk_level}

Version history:
- v1: Initial version with critical/fatal -> high, serious -> medium, general -> low
"""

RISK_MAPPINGS: dict[str, dict[str, str]] = {
    "v1": {
        "critical": "high",
        "fatal": "high",
        "serious": "medium",
        "general": "low",
    }
}

CURRENT_RISK_MAPPING_VERSION = "v1"


def get_risk_mapping(version: str) -> dict[str, str] | None:
    """Get risk mapping for a specific version.

    Returns None if version is unknown.
    """
    return RISK_MAPPINGS.get(version)


def get_risk_floor(severity: str, version: str = CURRENT_RISK_MAPPING_VERSION) -> tuple[str | None, str | None]:
    """Get risk floor for a CAPA severity.

    Returns (risk_floor, error_code) where:
    - risk_floor is the mapped risk level, or None if version unknown
    - error_code is None on success, or "unknown_risk_mapping_version" on failure
    """
    mapping = get_risk_mapping(version)
    if mapping is None:
        return None, "unknown_risk_mapping_version"

    risk_floor = mapping.get(severity)
    # If severity not in mapping, return None without error (valid case)
    return risk_floor, None