"""Single source of truth for E2E seed values. Mirrored by /api/e2e/seed-state."""

E2E_FACTORY_DC100 = {"code": "DC-FACT-E2E", "name": "E2E 默认工厂", "location": "Shanghai"}
E2E_FACTORY_SH = {"code": "SH-FACT-E2E", "name": "E2E 上海分厂", "location": "Shanghai-Pudong"}
E2E_PRODUCT_LINE = {"code": "DC-DC-100-E2E", "name": "E2E DC-DC 100", "product_type_code": None}

# (username, password, role_key, factory_codes) — factory_codes [] = group user (multi-factory)
E2E_ACCOUNTS = [
    ("admin", "Admin@2026", "admin", [E2E_FACTORY_DC100["code"]]),
    ("engineer", "Engineer@2026", "field_qe", [E2E_FACTORY_DC100["code"]]),
    ("manager", "Manager@2026", "manager", [E2E_FACTORY_DC100["code"]]),
    ("viewer", "Viewer@2026", "viewer", [E2E_FACTORY_DC100["code"]]),
    ("groupadmin", "GroupAdmin@2026", "admin", [E2E_FACTORY_DC100["code"], E2E_FACTORY_SH["code"]]),
]

# Known seed doc numbers (use -E2E- infix). Write flows must NOT reuse these.
E2E_KNOWN_DOCS = {
    "pfmea": ["PFMEA-E2E-001"],
    "capa": ["8D-E2E-001"],
}
