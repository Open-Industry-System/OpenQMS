"""
QMS Core State Models - Pure Business Logic
==============================================

This module contains the core state machines and data models for the QMS system.
These are the parts worth keeping after the prototype validates the design.

The question this prototype answers:
  "Does the FMEA/8D state machine and knowledge graph model feel right when driven by hand?"

State Models:
- FMEADocument: lifecycle state machine for both DFMEA and PFMEA
- EightDReport: 8D workflow state machine
- KnowledgeGraph: node and edge model for FMEA relationships
- ProductLine: data isolation boundary
"""

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from uuid import uuid4


# =============================================================================
# FMEA State Machine
# =============================================================================

class FMEAState(Enum):
    """FMEA document lifecycle states."""
    DRAFT = auto()
    IN_REVIEW = auto()
    APPROVED = auto()
    REWORK = auto()      # Sent back for revision
    ARCHIVED = auto()    # Superseded by new version


class FMEAType(Enum):
    DFMEA = "DFMEA"
    PFMEA = "PFMEA"


# Valid state transitions - the rules that govern what can happen when
FMEA_TRANSITIONS: Dict[FMEAState, List[FMEAState]] = {
    FMEAState.DRAFT: [FMEAState.IN_REVIEW, FMEAState.ARCHIVED],
    FMEAState.IN_REVIEW: [FMEAState.APPROVED, FMEAState.REWORK],
    FMEAState.APPROVED: [FMEAState.REWORK, FMEAState.ARCHIVED],
    FMEAState.REWORK: [FMEAState.IN_REVIEW],
    FMEAState.ARCHIVED: [],  # Terminal state
}


@dataclass
class FMEADocument:
    """FMEA document - both DFMEA and PFMEA use the same model."""
    id: str = field(default_factory=lambda: str(uuid4()))
    document_no: str = ""
    title: str = ""
    fmea_type: FMEAType = FMEAType.PFMEA
    product_line_code: str = ""
    version: int = 1
    state: FMEAState = FMEAState.DRAFT
    severity: int = 0   # RPN S component
    occurrence: int = 0  # RPN O component
    detection: int = 0   # RPN D component

    @property
    def rpn(self) -> int:
        """Risk Priority Number = S × O × D"""
        return self.severity * self.occurrence * self.detection

    @property
    def ap(self) -> str:
        """Action Priority based on RPN thresholds."""
        if self.rpn >= 100:
            return "HIGH"
        elif self.rpn >= 50:
            return "MEDIUM"
        return "LOW"

    def can_transition_to(self, new_state: FMEAState) -> bool:
        """Check if transition is valid."""
        return new_state in FMEA_TRANSITIONS.get(self.state, [])

    def transition_to(self, new_state: FMEAState) -> bool:
        """Attempt state transition. Returns True if successful."""
        if self.can_transition_to(new_state):
            self.state = new_state
            return True
        return False


# =============================================================================
# 8D Report State Machine
# =============================================================================

class EightDState(Enum):
    """8D workflow states - each D is a stage."""
    D1_TEAM = auto()       # Team formation
    D2_DESCRIPTION = auto() # Problem description (5W2H)
    D3_INTERIM = auto()     # Interim containment
    D4_ROOT_CAUSE = auto() # Root cause analysis
    D5_CORRECTION = auto() # Permanent corrective action
    D6_VERIFICATION = auto() # Verification of effectiveness
    D7_PREVENTION = auto()  # Prevention (systemic)
    D8_CLOSURE = auto()    # Closure and recognition
    ARCHIVED = auto()


# Valid 8D transitions - strictly linear with rare backsteps
EIGHTD_TRANSITIONS: Dict[EightDState, List[EightDState]] = {
    EightDState.D1_TEAM: [EightDState.D2_DESCRIPTION],
    EightDState.D2_DESCRIPTION: [EightDState.D3_INTERIM, EightDState.D1_TEAM],
    EightDState.D3_INTERIM: [EightDState.D4_ROOT_CAUSE],
    EightDState.D4_ROOT_CAUSE: [EightDState.D5_CORRECTION, EightDState.D3_INTERIM],
    EightDState.D5_CORRECTION: [EightDState.D6_VERIFICATION],
    EightDState.D6_VERIFICATION: [EightDState.D7_PREVENTION, EightDState.D5_CORRECTION],
    EightDState.D7_PREVENTION: [EightDState.D8_CLOSURE],
    EightDState.D8_CLOSURE: [EightDState.ARCHIVED],
    EightDState.ARCHIVED: [],
}


@dataclass
class EightDReport:
    """8D report - the structured problem-solving methodology."""
    id: str = field(default_factory=lambda: str(uuid4()))
    document_no: str = ""
    title: str = ""
    product_line_code: str = ""
    state: EightDState = EightDState.D1_TEAM
    severity: str = "一般"  # 致命/严重/一般/轻微
    due_date: Optional[str] = None
    fmea_ref_id: Optional[str] = None

    # 8D stage data (simplified)
    d1_team: List[str] = field(default_factory=list)
    d2_description: str = ""
    d3_interim_action: str = ""
    d4_root_cause: str = ""
    d5_corrective_action: str = ""
    d6_verification: str = ""
    d7_prevention: str = ""
    d8_closure_notes: str = ""

    def can_transition_to(self, new_state: EightDState) -> bool:
        return new_state in EIGHTD_TRANSITIONS.get(self.state, [])

    def transition_to(self, new_state: EightDState) -> bool:
        if self.can_transition_to(new_state):
            self.state = new_state
            return True
        return False

    @property
    def current_d(self) -> str:
        """Current D stage for display."""
        return self.state.name.replace("_", " ")


# =============================================================================
# Knowledge Graph Model
# =============================================================================

class NodeType(Enum):
    """Types of nodes in the FMEA knowledge graph."""
    # Common
    FUNCTION = "Function"
    FAILURE_MODE = "FailureMode"
    FAILURE_CAUSE = "FailureCause"
    FAILURE_EFFECT = "FailureEffect"
    CONTROL_MEASURE = "ControlMeasure"
    # DFMEA specific
    SYSTEM_ITEM = "SystemItem"
    DESIGN_PARAMETER = "DesignParameter"
    INTERFACE = "Interface"
    # PFMEA specific
    PROCESS = "Process"
    PRODUCT = "Product"


class EdgeType(Enum):
    """Types of edges in the FMEA knowledge graph."""
    # Common relationships
    HAS_FAILURE_MODE = "HAS_FAILURE_MODE"
    HAS_CAUSE = "HAS_CAUSE"
    HAS_EFFECT = "HAS_EFFECT"
    CONTROLLED_BY = "CONTROLLED_BY"
    DETECTED_BY = "DETECTED_BY"
    # DFMEA specific
    PERFORMS_FUNCTION = "PERFORMS_FUNCTION"
    SPECIFIED_BY = "SPECIFIED_BY"
    CAUSED_BY_DESIGN = "CAUSED_BY_DESIGN"
    HAS_INTERFACE = "HAS_INTERFACE"
    HAS_INTERFACE_FAILURE = "HAS_INTERFACE_FAILURE"
    # PFMEA specific
    HAS_FUNCTION = "HAS_FUNCTION"
    BELONGS_TO = "BELONGS_TO"


@dataclass
class GraphNode:
    """A node in the knowledge graph."""
    id: str = field(default_factory=lambda: str(uuid4()))
    node_type: NodeType = NodeType.FUNCTION
    name: str = ""
    description: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)
    product_line_code: str = ""  # For isolation

    # RPN components (for failure nodes)
    severity: int = 0
    occurrence: int = 0
    detection: int = 0

    @property
    def rpn(self) -> int:
        return self.severity * self.occurrence * self.detection


@dataclass
class GraphEdge:
    """An edge (relationship) in the knowledge graph."""
    edge_type: EdgeType = EdgeType.HAS_FAILURE_MODE
    source_id: str = ""
    target_id: str = ""
    id: str = field(default_factory=lambda: str(uuid4()))
    properties: Dict[str, Any] = field(default_factory=dict)


class KnowledgeGraph:
    """
    In-memory knowledge graph for FMEA.

    This is the read-optimized view - actual data lives in PostgreSQL,
    synced to Neo4j for graph queries like:
    - "What design parameters caused this failure mode?"
    - "Show all failures related to this process"
    - "Impact analysis: what changes if we modify X?"
    """

    def __init__(self):
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: Dict[str, GraphEdge] = {}

    def add_node(self, node: GraphNode) -> bool:
        """Add a node. Returns True if added, False if already exists."""
        if node.id in self.nodes:
            return False
        self.nodes[node.id] = node
        return True

    def add_edge(self, edge: GraphEdge) -> bool:
        """Add an edge. Validates that source and target exist."""
        if edge.source_id not in self.nodes or edge.target_id not in self.nodes:
            return False
        if edge.id in self.edges:
            return False
        self.edges[edge.id] = edge
        return True

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        return self.nodes.get(node_id)

    def get_neighbors(self, node_id: str) -> List[GraphNode]:
        """Get all nodes connected to this node."""
        neighbor_ids = set()
        for edge in self.edges.values():
            if edge.source_id == node_id:
                neighbor_ids.add(edge.target_id)
            elif edge.target_id == node_id:
                neighbor_ids.add(edge.source_id)
        return [self.nodes[nid] for nid in neighbor_ids if nid in self.nodes]

    def find_by_type(self, node_type: NodeType) -> List[GraphNode]:
        """Find all nodes of a given type."""
        return [n for n in self.nodes.values() if n.node_type == node_type]

    def find_by_product_line(self, pl_code: str) -> List[GraphNode]:
        """Find all nodes belonging to a product line."""
        return [n for n in self.nodes.values() if n.product_line_code == pl_code]

    def query_path(self, start_id: str, depth: int = 2) -> List[str]:
        """Find all nodes within N hops of start node."""
        visited = set()
        queue = [(start_id, 0)]
        result = []

        while queue:
            node_id, d = queue.pop(0)
            if node_id in visited or d > depth:
                continue
            visited.add(node_id)
            result.append(node_id)

            if d < depth:
                for edge in self.edges.values():
                    if edge.source_id == node_id:
                        queue.append((edge.target_id, d + 1))
                    elif edge.target_id == node_id:
                        queue.append((edge.source_id, d + 1))

        return result


# =============================================================================
# Product Line (Data Isolation)
# =============================================================================

@dataclass
class ProductLine:
    """Product line - the core data isolation dimension in QMS."""
    code: str = ""
    name: str = ""
    category: str = ""  # 汽车电子/消费电子/工业/医疗
    status: str = "active"  # active/dormant/eol


class ProductLineStore:
    """In-memory product line registry."""

    def __init__(self):
        self.product_lines: Dict[str, ProductLine] = {}

    def add(self, pl: ProductLine) -> bool:
        if pl.code in self.product_lines:
            return False
        self.product_lines[pl.code] = pl
        return True

    def get(self, code: str) -> Optional[ProductLine]:
        return self.product_lines.get(code)

    def list_all(self) -> List[ProductLine]:
        return list(self.product_lines.values())


# =============================================================================
# QMS System State (Aggregate Root)
# =============================================================================

class QMSState:
    """
    The complete QMS state - this is what the TUI manipulates.

    In production, this would be distributed across PostgreSQL + Neo4j.
    Here we keep everything in-memory for prototype exploration.
    """

    def __init__(self):
        # Core entities
        self.fmeas: Dict[str, FMEADocument] = {}
        self.eightd_reports: Dict[str, EightDReport] = {}
        self.graph = KnowledgeGraph()
        self.product_lines = ProductLineStore()

        # Initialize with sample data for demo
        self._init_sample_data()

    def _init_sample_data(self):
        """Seed some sample data to make the prototype explorable."""
        # Sample product lines
        for pl_code, pl_name, pl_cat in [
            ("DC-DC-100", "DC-DC转换器", "汽车电子"),
            ("PCB-SMT-200", "PCB焊接组件", "消费电子"),
            ("IM-HG-300", "注塑外壳", "工业"),
        ]:
            self.product_lines.add(ProductLine(pl_code, pl_name, pl_cat))

        # Sample PFMEA
        pfmea = FMEADocument(
            document_no="PFMEA-001",
            title="SMT焊接工序PFMEA",
            fmea_type=FMEAType.PFMEA,
            product_line_code="PCB-SMT-200",
            state=FMEAState.DRAFT,
            severity=8,
            occurrence=5,
            detection=4
        )
        self.fmeas[pfmea.id] = pfmea

        # Sample DFMEA
        dfmea = FMEADocument(
            document_no="DFMEA-001",
            title="DC-DC转换器DFMEA",
            fmea_type=FMEAType.DFMEA,
            product_line_code="DC-DC-100",
            state=FMEAState.APPROVED,
            severity=9,
            occurrence=3,
            detection=6
        )
        self.fmeas[dfmea.id] = dfmea

        # Sample 8D
        eightd = EightDReport(
            document_no="8D-001",
            title="焊接不良客诉",
            product_line_code="PCB-SMT-200",
            state=EightDState.D3_INTERIM,
            severity="严重"
        )
        self.eightd_reports[eightd.id] = eightd

        # Sample knowledge graph - a small FMEA structure
        # Process -> Function -> FailureMode -> FailureCause -> ControlMeasure
        process_node = GraphNode(
            node_type=NodeType.PROCESS,
            name="SMT贴装",
            product_line_code="PCB-SMT-200"
        )
        func_node = GraphNode(
            node_type=NodeType.FUNCTION,
            name="元件贴装",
            product_line_code="PCB-SMT-200"
        )
        fm_node = GraphNode(
            node_type=NodeType.FAILURE_MODE,
            name="元件偏移",
            severity=7,
            occurrence=4,
            detection=3,
            product_line_code="PCB-SMT-200"
        )
        fc_node = GraphNode(
            node_type=NodeType.FAILURE_CAUSE,
            name="贴装压力不足",
            product_line_code="PCB-SMT-200"
        )
        cm_node = GraphNode(
            node_type=NodeType.CONTROL_MEASURE,
            name="定期校准贴片机",
            product_line_code="PCB-SMT-200"
        )

        self.graph.add_node(process_node)
        self.graph.add_node(func_node)
        self.graph.add_node(fm_node)
        self.graph.add_node(fc_node)
        self.graph.add_node(cm_node)

        # Edges
        self.graph.add_edge(GraphEdge(EdgeType.HAS_FUNCTION, process_node.id, func_node.id))
        self.graph.add_edge(GraphEdge(EdgeType.HAS_FAILURE_MODE, func_node.id, fm_node.id))
        self.graph.add_edge(GraphEdge(EdgeType.HAS_CAUSE, fm_node.id, fc_node.id))
        self.graph.add_edge(GraphEdge(EdgeType.CONTROLLED_BY, fc_node.id, cm_node.id))

    # --- FMEA Operations ---

    def create_fmea(self, fmea: FMEADocument) -> str:
        self.fmeas[fmea.id] = fmea
        return fmea.id

    def get_fmea(self, fmea_id: str) -> Optional[FMEADocument]:
        return self.fmeas.get(fmea_id)

    def list_fmeas(self, product_line: str = None, fmea_type: FMEAType = None) -> List[FMEADocument]:
        result = list(self.fmeas.values())
        if product_line:
            result = [f for f in result if f.product_line_code == product_line]
        if fmea_type:
            result = [f for f in result if f.fmea_type == fmea_type]
        return result

    # --- 8D Operations ---

    def create_eightd(self, report: EightDReport) -> str:
        self.eightd_reports[report.id] = report
        return report.id

    def get_eightd(self, report_id: str) -> Optional[EightDReport]:
        return self.eightd_reports.get(report_id)

    def list_eightds(self, product_line: str = None) -> List[EightDReport]:
        result = list(self.eightd_reports.values())
        if product_line:
            result = [e for e in result if e.product_line_code == product_line]
        return result

    # --- Graph Operations ---

    def add_graph_node(self, node: GraphNode) -> bool:
        return self.graph.add_node(node)

    def get_graph_node(self, node_id: str) -> Optional[GraphNode]:
        return self.graph.get_node(node_id)

    def list_graph_nodes(self, node_type: NodeType = None) -> List[GraphNode]:
        if node_type:
            return self.graph.find_by_type(node_type)
        return list(self.graph.nodes.values())

    def get_node_neighbors(self, node_id: str) -> List[GraphNode]:
        return self.graph.get_neighbors(node_id)