# Knowledge Graph & Change Impact Analysis Module — User Manual

> Last updated: 2026-06-13 | Applicable version: OpenQMS v1.0

---

## 1. Feature Overview

The Knowledge Graph & Change Impact Analysis module builds a cross-document knowledge association network based on FMEA graph data, providing quality engineers with the following capabilities:

| Sub-module | Route | Functional Scope |
|-----------|-------|------------------|
| Knowledge Graph | `/knowledge-graph` | Cross-FMEA risk overview, keyword/semantic search for similar nodes, global knowledge base statistics |
| Change Impact Analysis | `/change-impact` | View change impact analysis history, impact report details, locate affected nodes in the graph |

The two sub-modules are tightly integrated through the FMEA editor: change impact analysis can be initiated directly from the FMEA graph editor (requires FMEA EDIT permission), and analysis results can link back to the graph for viewing.

---

## 2. Applicable Roles and Permissions

### 2.1 Knowledge Graph (`knowledge_graph`)

The knowledge graph module uses independent ModuleKey permission control:

| Role | PermissionLevel | Description |
|------|:---------------:|-------------|
| admin | 1 (VIEW) | Can view cross-product-line global statistics (masked) |
| manager | 1 (VIEW) | Can view statistics and similar node searches for their product line |
| quality_engineer | No permission row | No access by default (requires admin to assign permissions) |
| field_qe / planning_qe / supplier_qe / customer_qe | No permission row | No access by default |
| viewer | No permission row | No access by default |

> **Permission Note:** The `knowledge_graph` module currently only grants VIEW permission to admin and manager. Other roles that need access must have an admin add a `knowledge_graph` module permission row for their role in role permission management. The frontend route `/knowledge-graph` does not check module permissions — it only checks login status — but the API layer filters data based on role permissions (e.g., the `global-stats` endpoint requires ADMIN permission, and the `similar-nodes` endpoint automatically downgrades search scope when there is no global permission).

**API Permission Reference:**

| API Endpoint | Minimum Permission | Description |
|-------------|-------------------|-------------|
| `GET /api/graph/stats` | Login only | Cross-FMEA aggregated statistics (by product line) |
| `GET /api/graph/global-stats` | ADMIN | Cross-product-line global statistics (data masked) |
| `GET /api/graph/similar` | Login only | Keyword search for similar nodes (by product line) |
| `POST /api/graph/similar-nodes` | Login only (auto-downgrades scope when no KNOWLEDGE_GRAPH VIEW) | Semantic similarity search |
| `GET /api/graph/fmea/{id}/impact/{node}` | Login only | Downstream impact chain |
| `GET /api/graph/fmea/{id}/cause/{node}` | Login only | Upstream cause chain |
| `POST /api/graph/rebuild` | ADMIN | Trigger Neo4j full rebuild |

### 2.2 Change Impact Analysis (`change-impact`)

The change impact analysis module does not use an independent ModuleKey permission; it reuses FMEA module permissions:

| Action | Minimum Permission | Description |
|--------|-------------------|-------------|
| Initiate change impact analysis | FMEA EDIT (3) | Requires FMEA edit permission |
| View analysis history | FMEA VIEW (1) | Requires FMEA view permission |
| View analysis details | FMEA VIEW (1) | Requires FMEA view permission |

> **Note:** The frontend route `/change-impact` does not check module permissions — it only checks login status. The API layer controls access via FMEA module permissions. Additionally, factory scope (factory scope) also applies to change impact analysis: users can only see data from their assigned factories.

---

## 3. Knowledge Graph

### 3.1 Page Entry and Layout

Click **"Knowledge Graph"** in the sidebar to navigate to `/knowledge-graph`. The top of the page has a product line selector, and the main body is divided into three tabs:

| Tab | Icon | Description |
|-----|------|-------------|
| Overview / Risk Map | BarChartOutlined | Cross-FMEA aggregated statistics panel |
| Keyword Search | SearchOutlined | Search by node type and keyword |
| Semantic Search | RobotOutlined | Intelligent search based on similarity scores |

> If no product line is selected, the page displays a "Please select a product line" empty state.

### 3.2 Overview / Risk Map

After selecting a product line, the system calls `GET /api/graph/stats?product_line_code=xxx` to get aggregated statistics for all approved FMEAs under that product line.

**Displayed Content:**

| Metric | Description |
|--------|-------------|
| Total FMEAs | Number of approved FMEA documents under the product line |
| Total Nodes | Total number of nodes in all FMEA graph data |
| High-Priority Failure Modes (AP=H) | Number of failure modes with Action Priority "H" (High), highlighted with a red flame icon |
| Average RPN | Average Risk Priority Number of all failure modes (using the highest RPN row) |

**AP Distribution Card:** Displays AP level distribution as Tags:
- Red Tag: High (H) — Number of high-priority failure modes
- Orange Tag: Medium (M) — Number of medium-priority failure modes
- Green Tag: Low (L) — Number of low-priority failure modes

**High-Priority Failure Modes Top 10 Table:** Lists failure modes with AP=H, including the following columns:

| Column | Description |
|--------|-------------|
| Failure Mode | Node name |
| RPN | Risk Priority Number |
| Source FMEA | Associated FMEA document number; click to navigate to that FMEA's graph tab and highlight this node |
| Action | "View Graph" button, navigate to the corresponding FMEA graph |

**Node Type Distribution Card:** Displays the count of each node type as a tag list, e.g. `ProcessStep: 15`, `FailureMode: 8`, etc.

### 3.3 Keyword Search

In the "Keyword Search" tab, users can search FMEA nodes within the current product line by node type and keyword.

**Steps:**

1. Select a node type from the dropdown:
   - Failure Mode (`FailureMode`)
   - Failure Cause (`FailureCause`)
   - Failure Effect (`FailureEffect`)
   - Function (`Function`)
2. Enter a keyword in the search box
3. Click search or press Enter

The system calls `GET /api/graph/similar?node_type=xxx&name_keyword=xxx&product_line_code=xxx` for keyword matching search.

**Search Results Table:**

| Column | Description |
|--------|-------------|
| Name | Matched node name |
| Type | Node type |
| Source FMEA | Associated FMEA document number; click to navigate |
| Action | "View" button, navigate to the FMEA graph and highlight the node |

### 3.4 Semantic Search

The Semantic Search tab (`SemanticSearchTab` component) provides intelligent search based on similarity scores, calling the `POST /api/graph/similar-nodes` endpoint.

**Search Scope:**

- **Current Product Line (`current_product_line`):** Search only approved FMEA nodes within the user's assigned product line
- **Global (`global`):** Search approved FMEA nodes across all product lines. If the user lacks `knowledge_graph` VIEW permission, the system automatically downgrades global requests to `current_product_line`

**Similarity Mechanism:** The system calculates a similarity score (0.0–1.0) between the query text and node names via the `compute_similarity()` function. Results below `min_similarity` (default 0.3) are filtered out.

**Return Fields:**

| Field | Description |
|-------|-------------|
| node_id | Node ID |
| name | Node name (masked for cross-product-line nodes when user lacks global permission) |
| type | Node type |
| fmea_id | Source FMEA ID |
| document_no | Source FMEA document number |
| product_line_code | Product line code |
| product_line_name | Product line name |
| similarity_score | Similarity score (0–1) |
| match_reason | Match reason description |

> **Data Masking:** When a user lacks `knowledge_graph` global permission, node names in cross-product-line search results are masked (keeping the first 2 characters, replacing the rest with `***`) to prevent information leakage.

### 3.5 Global Statistics (Admin Only)

Admin role can access the `GET /api/graph/global-stats` endpoint to view aggregated statistics across all product lines. This endpoint:

- Does not accept a `product_line_code` parameter (passing one returns a 400 error)
- Returns data that has been rebuilt from a whitelist with name masking (via the `mask_name()` function)
- Masking rule: Keep the first 2 characters of names, replace the rest with `***`; names with length ≤ 2 keep only the first character + `***`

### 3.6 Graph Rebuild

Admin role can trigger a Neo4j full rebuild via the `POST /api/graph/rebuild` endpoint. This operation:

- Executes as an async background task, returning a success response immediately
- Clears all existing data in Neo4j
- Recreates constraints and indexes
- Iterates through all FMEA documents in PostgreSQL, projecting each into Neo4j
- Suitable for Neo4j data inconsistency or large-scale data repair scenarios

---

## 4. Change Impact Analysis

### 4.1 Feature Description

Change impact analysis evaluates the potential impact scope and risk level changes on associated nodes when a single node in an FMEA graph undergoes a change. Typical scenarios include:

- **Attribute Change:** Modifying the severity (S), occurrence (O), or detection (D) of a failure mode
- **Structural Change:** Adding, deleting, or moving nodes and connections in the graph

### 4.2 Initiating Analysis

Change impact analysis has two entry points:

**Entry Point 1: Within the FMEA Editor**

In the FMEA graph editor (`/fmea/:id?tab=graph`), select a node to initiate change impact analysis. The system auto-fills parameters such as `fmea_id`, `node_id`, `node_type`, `node_name`. The user only needs to select the change type and fill in the change field.

**Entry Point 2: Change Impact Analysis Page**

On the `/change-impact` page, you can view historical analysis records, but cannot initiate new analyses from this page.

### 4.3 API Call

```
POST /api/change-impact/analyze
```

**Request Parameters (`ChangeImpactAnalyzeRequest`):**

| Parameter | Type | Required | Description |
|-----------|------|:--------:|-------------|
| fmea_id | UUID | Yes | Associated FMEA document ID |
| node_id | string | Yes | Changed node ID |
| node_type | string | Yes | Node type (e.g. `FailureMode`, `FailureCause`) |
| node_name | string | Yes | Node name |
| change_type | string | Yes | Change type: `attribute` (attribute change) or `structural` (structural change) |
| field_name | string | No | Changed field name (e.g. `severity`, `occurrence`, `detection`) |
| new_value | string | No | New value after change |

**Permission Requirement:** FMEA module EDIT permission (Level 3+).

### 4.4 Analysis Logic

The system selects different traversal strategies based on the change type and field:

#### Change Type: Attribute Change (`attribute`)

| Changed Field | Traversal Direction | Description |
|--------------|--------------------|-------------|
| `name` / `description` | No traversal | Name and description changes do not affect other nodes' risk levels |
| `severity` / `occurrence` / `detection` | Bidirectional (downstream + upstream) | S/O/D changes affect both downstream failure effects and controls, as well as upstream failure causes |
| Other fields | Downstream | Default tracks downstream impact chain |

#### Change Type: Structural Change (`structural`)

Only tracks downstream direction.

#### Edge Type Filtering

**Edge types used for downstream traversal:**

| Edge Type | Description |
|-----------|-------------|
| `HAS_FUNCTION` | Process step / work element → Function |
| `FUNCTION_MAPPED_TO` | Function → Failure mode |
| `HAS_FAILURE_MODE` | Structure node → Failure mode |
| `EFFECT_OF` | Failure mode → Failure effect |
| `HAS_PROCESS_STEP` | Process item → Process step |
| `HAS_CHILD` | Parent node → Child node |

**Edge types used for upstream traversal:**

| Edge Type | Description |
|-----------|-------------|
| `CAUSE_OF` | Failure cause → Failure mode |
| `PREVENTED_BY` | Prevention control → Failure cause |
| `DETECTED_BY` | Detection control → Failure cause / Failure mode |
| `OPTIMIZED_BY` | Optimization measure → Failure mode |

> Maximum BFS traversal depth is 5 hops.

### 4.5 Risk Change Calculation

The system calculates risk level changes for affected FailureMode and FailureCause nodes:

**Scenario 1: FailureMode's own S/O/D change**

Recalculate RPN and AP (Action Priority), comparing AP levels before and after the change.

**Scenario 2: FailureCause's O/D change affecting associated FailureMode**

Find the FailureMode associated with the Cause, recalculate O/D/AP for the maximum RPN row, comparing before and after the change.

**Scenario 3: Component/ProcessStep design_parameter change**

Mark associated FailureModes as `needs_reassessment: true`, indicating manual reassessment is required.

### 4.6 Impact Score Algorithm

The impact score is calculated by the Service layer (0–10 scale):

```
score = failure_modes_affected × 2 + ap_upgraded_count × 3 + (max_hop_distance > 2 ? 2 : 0)
score = min(score, 10)  // Capped at 10
```

| Factor | Weight | Description |
|--------|--------|-------------|
| Affected failure modes | 2 points each | Number of directly affected FailureModes |
| AP upgrades | 3 points each | Number of AP level upgrades (L→M, M→H, etc.) |
| Long-distance impact | +2 points | Extra points when maximum hop count > 2 |

**Score Level Color Mapping:**

| Score | Level | Color |
|:-----:|-------|-------|
| 0–3 | Low | Green |
| 4–6 | Medium | Orange |
| 7–10 | High | Red |

### 4.7 Analysis Results Page

Visit the `/change-impact` page. The left side shows the analysis history table, and the right side shows the details panel for the selected record.

**Analysis History Table (`ChangeHistoryTable`):**

| Column | Description |
|--------|-------------|
| Time | Analysis creation time |
| Node Name | Changed node name |
| Change Type | "Attribute" or "Structural" |
| Impact Score | Impact score Tag (color-coded) |
| Affected Node Count | summary.total_affected |

**Analysis Details Panel (`ImpactReportPanel`):**

1. **Change Information Card:** Displays node name, type, change type (Attribute/Structural Tag), field name, new value
2. **Statistics Card Row:**
   - Impact Score (ImpactScoreTag)
   - Affected node count
   - FailureMode count
   - AP upgrade count
3. **Affected Node List (`AffectedNodeList`):** Expandable list, each node shows:
   - Node name and type
   - Impact type Tag (upstream/downstream/direct)
   - Hop distance (hop_distance)
   - Path visualization
   - Risk change details (old_ap → new_ap)
4. **"View in Graph" button:** Navigates to `/fmea/{fmea_id}?tab=graph&highlightNode={node_id}`

### 4.8 API Query Endpoints

| Endpoint | Method | Description | Permission |
|----------|--------|-------------|------------|
| `/api/change-impact/analyze` | POST | Initiate change impact analysis | FMEA EDIT |
| `/api/change-impact` | GET | Query all analysis records (supports product_line_code pagination filtering) | FMEA VIEW |
| `/api/change-impact/fmea/{fmea_id}` | GET | Query analysis records for a specific FMEA | FMEA VIEW |
| `/api/change-impact/{analysis_id}` | GET | Get a single analysis detail | FMEA VIEW |

**List Query Parameters:**

| Parameter | Description |
|-----------|-------------|
| `product_line_code` | Optional, filter by product line |
| `page` | Page number, default 1 |
| `page_size` | Items per page, default 20, max 1000 |

---

## 5. Technical Architecture

### 5.1 Dual Backend Storage Architecture

The knowledge graph module uses a **Repository pattern**, providing two switchable graph storage backends:

| Backend | Class | Use Case | Configuration |
|---------|-------|----------|---------------|
| PostgreSQL JSONB | `JSONBRepository` | Development/testing environments, or fallback when Neo4j is unavailable | `GRAPH_REPOSITORY=jsonb` (default) |
| Neo4j | `Neo4jRepository` | Production environments, requires cross-document graph traversal and complex queries | `GRAPH_REPOSITORY=neo4j` |

Selection logic in `app/graph/deps.py` automatically injects the corresponding Repository implementation based on `settings.GRAPH_REPOSITORY` configuration.

### 5.2 Neo4j Data Projection

FMEA graph data is stored in PostgreSQL's `graph_data` JSONB column and asynchronously projected to Neo4j via the Outbox pattern:

```
FMEA create/update/status change
        ↓
  GraphSyncOutbox enqueue (event_type: fmea.created / fmea.updated / fmea.status_changed)
        ↓
  GraphSyncWorker poll (5s interval, FOR UPDATE SKIP LOCKED)
        ↓
  GraphProjectionService generates Cypher statements (DELETE + CREATE idempotent projection)
        ↓
  Neo4j write transaction execution
```

**Node Projection Properties:**

| Property | Source |
|----------|--------|
| `node_id` | Graph node `id` |
| `name` | Graph node `name` |
| `type` | Graph node `type` |
| `process_number` / `classification` / `requirement` / `specification` | Node business attributes |
| `severity` / `occurrence` / `detection` / `ap` / `rpn` | Risk parameters |

**Edge Projection:** Only edge types in the whitelist (`ALLOWED_EDGE_TYPES`) are projected, preventing user input from injecting Cypher queries.

**Node Label Mapping:** `PreventionControl` and `DetectionControl` are mapped to the `Control` label in Neo4j.

### 5.3 Outbox Reliability Guarantees

The `GraphSyncOutbox` table implements asynchronous reliable projection:

| Field | Description |
|-------|-------------|
| `status` | `pending` → `processing` → `completed` / `dead` |
| `attempt_count` | Retry count, max 5 attempts |
| `next_attempt_at` | Next retry time (exponential backoff: 10s → 30s → 90s → 270s) |
| `last_error` | Most recent failure message |

**Worker Mechanism:**

- Polling interval: 5 seconds
- Batch size: 10 records
- Concurrency control: PostgreSQL `FOR UPDATE SKIP LOCKED` atomic claiming
- Zombie recovery: On startup, cleans up `processing` status tasks older than 10 minutes
- Deduplication: Only the latest event for the same `aggregate_id` (i.e. FMEA ID) is kept

### 5.4 Data Model

#### Knowledge Graph Core Entities

```
FMEADocument (PostgreSQL)
  ├── fmea_id: UUID (PK)
  ├── document_no: str (e.g. PFMEA-2026-001)
  ├── product_line_code: str
  ├── status: str (draft/submitted/approved/rejected)
  ├── graph_data: JSONB        ← Primary graph data storage
  │     ├── nodes: [{id, name, type, severity, occurrence, detection, ap, ...}]
  │     └── edges: [{source, target, type}]
  └── ...
```

#### Neo4j Projection Structure

```
(:FMEDocument {fmea_id, document_no, product_line_code})
(:GraphNode {node_id, name, type, severity, occurrence, detection, ap, rpn, ...})
(:Control {node_id, name, type, ...})  ← Unified label for PreventionControl / DetectionControl

(:FMEDocument)-[:HAS_NODE]->(:GraphNode)
(:GraphNode)-[:HAS_PROCESS_STEP]->(:GraphNode)
(:GraphNode)-[:HAS_FAILURE_MODE]->(:GraphNode)
(:GraphNode)-[:EFFECT_OF]->(:GraphNode)
(:GraphNode)-[:CAUSE_OF]->(:GraphNode)
(:GraphNode)-[:PREVENTED_BY]->(:Control)
(:GraphNode)-[:DETECTED_BY]->(:Control)
...
```

#### Change Impact Analysis Entity

```
ChangeImpactAnalysis (PostgreSQL)
  ├── id: UUID (PK)
  ├── fmea_id: UUID (FK → fmea_documents)
  ├── product_line_code: str
  ├── factory_id: UUID (FK → factories)
  ├── node_id: str           ← Changed node ID
  ├── node_type: str         ← Changed node type
  ├── node_name: str         ← Changed node name
  ├── change_type: str       ← "attribute" or "structural"
  ├── field_name: str?       ← Changed field name
  ├── old_value: str?        ← Value before change
  ├── new_value: str?        ← Value after change
  ├── scope: str             ← Analysis scope (currently "single_fmea")
  ├── status: str            ← Analysis status ("completed")
  ├── impact_score: int      ← Impact score (0-10)
  ├── impact_result: JSONB   ← Full ChangeImpactResult
  ├── created_by: UUID (FK → users)
  └── created_at: datetime
```

### 5.5 Docker Deployment

`docker-compose.yml` includes the following services:

| Service | Description | Port |
|---------|-------------|------|
| `neo4j` | Neo4j 5 Community | 7474 (HTTP), 7687 (Bolt) |
| `graph-worker` | GraphSyncWorker process | No external port |

**Neo4j Configuration:**

| Environment Variable | Default Value | Description |
|---------------------|---------------|-------------|
| `NEO4J_URI` | `bolt://localhost:7687` | Bolt protocol connection address |
| `NEO4J_USER` | `neo4j` | Username |
| `NEO4J_PASSWORD` | `openqms2026` | Password |
| `NEO4J_DATABASE` | `neo4j` | Database name |
| `GRAPH_REPOSITORY` | `jsonb` | Graph storage backend selection |

**Manual Full Rebuild Command:**

```bash
# In Docker environment
docker compose exec backend python -m app.cli.graph_rebuild

# With failed task reset
docker compose exec backend python -m app.cli.graph_rebuild --retry-failed
```

---

## 6. Frequently Asked Questions

### Q1: The knowledge graph page shows "Please select a product line"

The knowledge graph's statistics and search features all depend on a product line context. Please select a product line from the selector at the top of the page before proceeding.

### Q2: Can non-admin/manager roles access the knowledge graph?

The frontend route `/knowledge-graph` only checks login status, not module permissions, so all logged-in users can access the page. However, the API layer has permission controls:

- The `global-stats` endpoint requires ADMIN permission
- The `similar-nodes` endpoint automatically downgrades requests from users without `knowledge_graph` VIEW permission to current product line scope search
- Cross-product-line node names are masked

For full access permissions, ask an admin to add `knowledge_graph` module VIEW permission for the corresponding role in role permission management.

### Q3: No records appear on the change impact analysis page

Change impact analysis does not execute automatically; it must be manually triggered from within the FMEA graph editor. First, navigate to a FMEA document's graph tab, select a node, and then initiate an analysis.

### Q4: Does an impact score of 0 mean no impact?

The score formula `failure_modes_affected × 2 + ap_upgraded_count × 3 + (max_hop_distance > 2 ? 2 : 0)` can be 0, but the affected nodes list may not be empty. A score of 0 only indicates that there are no affected FailureModes, no AP upgrades, and the maximum hop count is ≤ 2. You should still review the contents of the affected nodes list.

### Q5: What is the difference between Neo4j and JSONB backends?

| Feature | JSONB | Neo4j |
|---------|-------|-------|
| Deployment dependency | No additional dependencies | Requires Neo4j service |
| Cross-document queries | Iterates through all FMEA JSONB | Cypher graph queries |
| Real-time data | Reads latest PostgreSQL data | Depends on Outbox async sync (~5 second delay) |
| Performance | Slower with many documents | Better graph traversal performance |
| Use case | Development, testing, small deployments | Production, large-scale data |

Production environments are recommended to use the Neo4j backend. When `GRAPH_REPOSITORY=jsonb`, all graph queries are calculated directly from PostgreSQL JSONB fields without needing Neo4j or the Worker.

### Q6: What is the GraphSyncWorker retry strategy?

The Worker uses exponential backoff retry: 10 seconds after the 1st failure, 30 seconds after the 2nd, 90 seconds after the 3rd, 270 seconds after the 4th, and marks as `dead` after the 5th failure with no further retries. You can reset dead tasks via `python -m app.cli.graph_rebuild --retry-failed`.

### Q7: Is the data in global statistics secure?

The `global-stats` endpoint is only accessible to admin, and returned data is rebuilt from a whitelist with name masking. Node names only keep the first 2 characters, replacing the rest with `***`, preventing cross-product-line sensitive information leakage. The `similar-nodes` endpoint also applies the same masking to cross-product-line nodes for users without global permission.

### Q8: What is the difference between "attribute change" and "structural change" in change impact analysis?

- **Attribute Change (`attribute`):** Modifying field values of existing nodes, such as changing S/O/D values of a failure mode. The system determines traversal direction based on the type of field changed — S/O/D changes traverse bidirectionally, while name/description changes do not traverse.
- **Structural Change (`structural`):** Adding, deleting, or moving nodes and connections in the graph. The system only tracks the downstream impact chain.

### Q9: How do FMEA graph nodes relate to the knowledge graph?

All nodes in an FMEA document's `graph_data` JSONB field (via Neo4j projection or direct JSONB queries) form the node set of the knowledge graph. The graph's edges (`edges`) define the association relationships between nodes. The knowledge graph's search and statistics features are based on cross-document aggregation of these nodes and edges.