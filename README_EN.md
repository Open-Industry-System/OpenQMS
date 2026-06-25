# OpenQMS

> OpenQMS is a full-stack quality management platform for manufacturing, covering FMEA (AIAG-VDA 7-step), 8D/CAPA, SPC, MSA, IQC, supplier management, and more — built for IATF 16949 compliance.

An out-of-the-box quality management system platform for manufacturing, covering core modules including AIAG-VDA PFMEA/DFMEA, 8D/CAPA, SPC, MSA, IQC, and supplier management, empowering IATF 16949 compliance.

**[中文文档 →](README.md)**

---

## Feature Overview

| Module | Description |
|--------|-------------|
| **FMEA** | AIAG-VDA 7-step PFMEA/DFMEA, graph model editing, 7-step generation wizard, automatic RPN/AP calculation, approval workflow |
| **8D / CAPA** | D1–D8 step progression, team formation, FMEA linking, approval closure |
| **Control Plan** | One-click generation from PFMEA, bidirectional sync, version management |
| **Special Characteristics** | CC/SC identification, coverage matrix, FMEA→CP linkage, traceability view |
| **SPC** | X̄-R / I-MR / P/NP/C/U control charts, 8 out-of-control rules, Cp/Cpk calculation |
| **MSA** | GR&R, bias, linearity, stability, attribute Kappa analysis |
| **IQC** | AQL sampling plans, inspection lot management, AQL optimization configuration |
| **Supplier Management** | Supplier profiles, performance evaluation, supplier risk configuration |
| **SCAR** | Supplier Corrective Action Request, 5-state lifecycle |
| **Customer Complaint / RMA** | Customer complaint intake, RMA returns, CAPA/FMEA linkage |
| **APQP** | Five-phase gate management, Gantt chart, deliverable checklists |
| **PPAP** | AIAG 18 elements, 5-state lifecycle, Level 1–5 required-field mapping |
| **Management Review** | ISO 9001 §9.3 data package auto-summary, action tracking closure |
| **Internal Audit** | System/process/product audits, checklists, finding tracking |
| **Customer Audit** | Audit scheduling, finding tracking, corrective closure |
| **Quality Objectives** | Three-level objective tree, approval workflow, dashboard KPI |
| **ERP / MES / PLM** | External system integration dashboards and data sync |
| **Knowledge Graph** | FMEA/CP knowledge association and visualization |
| **Group Management** | Multi-plant dashboards, plant comparison, group-level suppliers and audits |
| **Product Type Master Data** | Shared cross-factory product classification, product-line attribution and semantic-search filtering |

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.11 / FastAPI 0.115 (async) / SQLAlchemy 2.0 (async) / PostgreSQL 15 / Redis 7 |
| Frontend | React 18 / TypeScript 5.6 / Vite 5.4 / Ant Design 5.21 |
| Infrastructure | Docker Compose / Alembic (migrations) / Neo4j 5 (knowledge graph) / Ollama (AI recommendations) |

---

## Quick Start

### Prerequisites

- [Docker](https://www.docker.com/get-started) with Docker Compose
- 4 GB+ available memory (Neo4j + Ollama each use 256–512 MB)

### 1. Start Services

```bash
git clone https://github.com/your-org/OpenQMS.git
cd OpenQMS
docker compose up -d
```

Wait for all containers to become healthy (about 30 seconds):

```bash
docker compose ps   # Confirm db/redis/neo4j are healthy, backend/frontend are running
```

### 2. Initialize the Database

```bash
docker compose exec backend alembic upgrade head
```

### 3. Import Demo Data

```bash
docker compose exec backend python -m app.seed
```

Output `Seed data created successfully!` indicates success.

### 4. Access the System

Open **http://localhost:5173** in your browser and log in with one of the following accounts:

| Username | Password | Role | Description |
|----------|----------|------|-------------|
| `admin` | `Admin@2026` | System Administrator | Full permissions, can manage users and permissions |
| `engineer` | `Engineer@2026` | Quality Engineer | FMEA/SPC/MSA editing, CAPA editing |
| `manager` | `Manager@2026` | Quality Manager | Approval permissions, can close CAPA |
| `viewer` | `Viewer@2026` | Read-only User | Read-only access to all modules |
| `groupadmin` | `GroupAdmin@2026` | System Administrator (Group) | Multi-plant management permissions |

> ⚠️ Demo passwords are for development environments only — be sure to change them in production.

### 5. API Documentation

- Swagger UI: **http://localhost:8000/docs**
- ReDoc: **http://localhost:8000/redoc**

---

## Module Support Status

| Status | Description |
|--------|-------------|
| ✅ Complete | Full front-end and back-end functionality, including demo data |
| 🔧 In Development | Backend API ready, partial front-end functionality implemented |
| 📋 Planned | Design documentation only, not yet developed |

| Module | Status | Description |
|--------|:------:|-------------|
| FMEA | ✅ | PFMEA/DFMEA editor, 7-step generation wizard, approval workflow |
| 8D / CAPA | ✅ | D1–D8 step progression, FMEA linking |
| Control Plan | ✅ | One-click generation from PFMEA, version management |
| Special Characteristics | ✅ | CC/SC identification, coverage matrix, traceability |
| SPC | ✅ | Control charts + out-of-control rules + process capability |
| MSA | ✅ | GR&R / bias / linearity / stability / Kappa |
| IQC | ✅ | AQL sampling, inspection lots, AQL optimization |
| Supplier | ✅ | Profiles + performance + risk configuration |
| SCAR | ✅ | 5-state lifecycle |
| Customer Complaint / RMA | ✅ | Complaints + returns + CAPA linkage |
| APQP | ✅ | Five-phase gates + Gantt chart |
| PPAP | ✅ | 18 elements, Level 1–5 |
| Management Review | ✅ | Data package summary + action tracking |
| Internal Audit | ✅ | Three audit types + findings |
| Customer Audit | ✅ | Audit scheduling + corrective closure |
| Quality Objectives | ✅ | Three-level objective tree + KPI |
| Supplier Risk | ✅ | Risk rule configuration + risk dashboard |
| Supply Chain Risk Map | ✅ | Multi-dimensional risk heatmap |
| Group Management | ✅ | Multi-plant dashboard + comparison + group suppliers |
| Product Type Master Data | ✅ | Cross-factory product-line classification + semantic-search filtering |
| ERP Integration | ✅ | Dashboard + connection configuration + data sync |
| MES Integration | ✅ | Dashboard + connection configuration + production/scrap data |
| PLM Integration | ✅ | Parts/BOM/change orders + mock connector |
| Knowledge Graph | ✅ | Neo4j visualization + FMEA/CP association |
| Change Impact | ✅ | Impact analysis + risk scoring |

---

## Documentation Directory

| Document | Description |
|----------|-------------|
| [Deployment Guide](docs/en/deployment.md) | Docker / local development environment setup |
| [Architecture Overview](docs/en/architecture.md) | Front-end and back-end architecture, permission model, data flow |
| [User Guide](docs/en/user-guide.md) | Login, navigation, common operations |
| [Admin Guide](docs/en/admin-guide.md) | User management, permission configuration, plant assignment |
| [Permissions Reference](docs/en/permissions.md) | Full permission matrix |
| [Development Guide](docs/en/development.md) | Development conventions, adding new modules |
| [Roadmap](docs/ROADMAP.md) | Development plan and progress |

### Module Manuals

| Manual | Modules Covered |
|--------|----------------|
| [Planning & FMEA](docs/en/modules/planning.md) | FMEA, Control Plan, APQP, PPAP, Special Characteristics |
| [CAPA / 8D](docs/en/modules/capa.md) | 8D step progression, approval workflow |
| [IQC & Suppliers](docs/en/modules/iqc-supplier.md) | Incoming inspection, supplier management, supplier risk, supply chain risk map |
| [SPC & MSA](docs/en/modules/spc-msa.md) | Statistical Process Control, Measurement System Analysis |
| [Customer Quality](docs/en/modules/customer-quality.md) | Customer complaints, RMA, customer audits, SCAR |
| [Management Review & Quality Objectives](docs/en/modules/management-review.md) | Management review, quality objectives, dashboards |
| [ERP / MES / PLM](docs/en/modules/erp-mes-plm.md) | External system integration |
| [Knowledge Graph & Change Impact](docs/en/modules/knowledge-graph.md) | Knowledge graph visualization, change impact analysis |
| [Group Management](docs/en/modules/group.md) | Multi-plant, group suppliers, group audits |

---

## License

MIT License — see [LICENSE](LICENSE) for details.