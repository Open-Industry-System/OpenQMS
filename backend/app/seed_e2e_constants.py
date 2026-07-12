"""Single source of truth for E2E seed values. Mirrored by /api/e2e/seed-state."""

E2E_FACTORY_DC100 = {"code": "DC-FACT-E2E", "name": "E2E 默认工厂", "location": "Shanghai"}
E2E_FACTORY_SH = {"code": "SH-FACT-E2E", "name": "E2E 上海分厂", "location": "Shanghai-Pudong"}
E2E_PRODUCT_LINE = {"code": "DC-DC-100-E2E", "name": "E2E DC-DC 100", "product_type_code": None}
E2E_PRODUCT_LINE_DEFAULT = {"code": "DC-DC-100", "name": "E2E Default Product Line", "product_type_code": None}

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

# D3 E2E source data constants (shared by seed_e2e.py and tests)
D3_E2E_PRODUCT_LINE = "DC-DC-100-E2E"
D3_E2E_MATERIAL_CODE = "D3-MAT-E2E-001"
D3_E2E_LOT_NO = "D3-LOT-E2E-001"
D3_E2E_CUSTOMER_CODE = "D3-CUST-E2E-001"
D3_E2E_CUSTOMER_SEGMENT = "key"
D3_E2E_SUPPLIER_NO = "D3-SUP-E2E-001"
D3_E2E_ERP_CONNECTION_NAME = "D3 ERP Mock E2E"
D3_E2E_SHIPMENT_ARRIVAL_STATUSES = ("in_transit", "signed")

# 7 independent CAPA document numbers for D3 P1-4 status-change tests
D3_E2E_CAPA_DOC_NO = "8D-E2E-D3-001"
D3_E2E_CAPA_DOC_NO_UNIMPORTED = "8D-E2E-D3-002"
D3_E2E_CAPA_DOC_NO_REPORTED = "8D-E2E-D3-003"
D3_E2E_CAPA_DOC_NO_EXEC_FORM = "8D-E2E-D3-004"
D3_E2E_CAPA_DOC_NO_VIEWER = "8D-E2E-D3-005"
D3_E2E_CAPA_DOC_NO_NOCREDS = "8D-E2E-D3-006"
D3_E2E_CAPA_DOC_NO_CROSSFACTORY = "8D-E2E-D3-007"
