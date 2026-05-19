#!/usr/bin/env python3
"""
QMS State Models - Interactive TUI Prototype
=============================================

A throwaway terminal app to explore the QMS core state models by hand.
Follows prototype/LOGIC.md branch.

Run: python3 tui.py

Controls:
  [1-4] Switch view (Dashboard/FMEA/8D/Graph)
  [f]   Create FMEA
  [t]   Transition FMEA state
  [d]   Delete FMEA
  [n]   Create 8D report
  [w]   Advance 8D workflow
  [g]   Add graph node
  [e]   Add graph edge
  [v]   View node neighbors (graph traversal)
  [q]   Quit
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import (
    QMSState, FMEADocument, FMEAType, FMEAState,
    EightDReport, EightDState,
    GraphNode, GraphEdge, NodeType, EdgeType,
    ProductLine
)


class TUI:
    """Terminal UI for QMS state exploration."""

    def __init__(self):
        self.state = QMSState()
        self.current_view = "dashboard"  # dashboard, fmea, eightd, graph
        self.selected_fmea_id = None
        self.selected_eightd_id = None
        self.selected_node_id = None
        self.message = "Welcome to QMS Prototype - Press a key to start"

    def clear(self):
        """Clear screen and move cursor home."""
        print("\033[2J\033[H", end="")

    def bold(self, text: str) -> str:
        return f"\033[1m{text}\033[0m"

    def dim(self, text: str) -> str:
        return f"\033[2m{text}\033[0m"

    def red(self, text: str) -> str:
        return f"\033[91m{text}\033[0m"

    def green(self, text: str) -> str:
        return f"\033[92m{text}\033[0m"

    def yellow(self, text: str) -> str:
        return f"\033[93m{text}\033[0m"

    def cyan(self, text: str) -> str:
        return f"\033[96m{text}\033[0m"

    def render_dashboard(self):
        """Render the dashboard view."""
        lines = []
        lines.append(self.bold("═══ QMS Dashboard ═══"))
        lines.append("")

        # Product lines summary
        lines.append(self.bold("Product Lines:"))
        for pl in self.state.product_lines.list_all():
            status_icon = "✓" if pl.status == "active" else "○"
            lines.append(f"  {status_icon} {pl.code}: {pl.name} ({pl.category})")
        lines.append("")

        # FMEA summary
        fmeas = self.state.list_fmeas()
        lines.append(self.bold(f"FMEA Documents: {len(fmeas)}"))
        draft_count = sum(1 for f in fmeas if f.state == FMEAState.DRAFT)
        approved_count = sum(1 for f in fmeas if f.state == FMEAState.APPROVED)
        lines.append(f"  Draft: {draft_count}  |  Approved: {approved_count}")
        for f in fmeas[:5]:
            state_icon = "🟢" if f.state == FMEAState.APPROVED else "🟡" if f.state == FMEAState.DRAFT else "🟠"
            lines.append(f"    {state_icon} {f.document_no} ({f.fmea_type.value}) - RPN: {f.rpn}, AP: {f.ap}")
        lines.append("")

        # 8D summary
        eightds = self.state.list_eightds()
        lines.append(self.bold(f"8D Reports: {len(eightds)}"))
        open_count = sum(1 for e in eightds if e.state != EightDState.ARCHIVED)
        lines.append(f"  Open: {open_count}")
        for e in eightds[:5]:
            lines.append(f"    {e.document_no}: {e.current_d} - {e.title}")
        lines.append("")

        # Graph summary
        lines.append(self.bold("Knowledge Graph:"))
        lines.append(f"  Nodes: {len(self.state.graph.nodes)}")
        lines.append(f"  Edges: {len(self.state.graph.edges)}")
        lines.append("")

        return "\n".join(lines)

    def render_fmea_view(self):
        """Render the FMEA management view."""
        lines = []
        lines.append(self.bold("═══ FMEA Management ═══"))
        lines.append("")

        fmeas = self.state.list_fmeas()
        if not fmeas:
            lines.append(self.dim("  No FMEA documents yet. Press [f] to create one."))
        else:
            for i, f in enumerate(fmeas):
                selected = "► " if f.id == self.selected_fmea_id else "  "
                state_color = self.green if f.state == FMEAState.APPROVED else self.yellow if f.state == FMEAState.DRAFT else self.red
                lines.append(f"{selected}{i+1}. {self.bold(f.document_no)} ({f.fmea_type.value})")
                lines.append(f"     Title: {f.title}")
                lines.append(f"     Product Line: {f.product_line_code}")
                lines.append(f"     State: {state_color(f.state.name)} | Version: {f.version}")
                lines.append(f"     RPN: {f.rpn} (S:{f.severity}×O:{f.occurrence}×D:{f.detection}) | AP: {self.cyan(f.ap)}")

                # Show valid transitions
                valid = FMEAState.__members__.get(f.state.name)
                transitions = []
                for next_state in FMEAState:
                    if f.can_transition_to(next_state):
                        transitions.append(next_state.name)
                if transitions:
                    lines.append(f"     Valid transitions: {self.dim(', '.join(transitions))}")
                lines.append("")

        if self.selected_fmea_id:
            f = self.state.get_fmea(self.selected_fmea_id)
            if f:
                lines.append(self.bold("Actions:"))
                lines.append(f"  [t] Transition state")
                lines.append(f"  [d] Delete this FMEA")

        lines.append("")
        lines.append(self.bold("Actions:"))
        lines.append(f"  [f] Create new FMEA")
        lines.append(f"  [1-{len(fmeas)}] Select FMEA")
        lines.append(f"  [←] Back to dashboard")

        return "\n".join(lines)

    def render_eightd_view(self):
        """Render the 8D report view."""
        lines = []
        lines.append(self.bold("═══ 8D Report Management ═══"))
        lines.append("")

        eightds = self.state.list_eightds()
        if not eightds:
            lines.append(self.dim("  No 8D reports yet. Press [n] to create one."))
        else:
            for i, e in enumerate(eightds):
                selected = "► " if e.id == self.selected_eightd_id else "  "
                lines.append(f"{selected}{i+1}. {self.bold(e.document_no)}")
                lines.append(f"     Title: {e.title}")
                lines.append(f"     Product Line: {e.product_line_code}")
                lines.append(f"     State: {self.cyan(e.current_d)} | Severity: {e.severity}")
                lines.append(f"     Due: {e.due_date or 'Not set'}")
                lines.append("")

        if self.selected_eightd_id:
            e = self.state.get_eightd(self.selected_eightd_id)
            if e:
                lines.append(self.bold("Current Stage Data:"))
                if e.state == EightDState.D1_TEAM:
                    lines.append(f"  Team: {', '.join(e.d1_team) or 'None yet'}")
                elif e.state == EightDState.D2_DESCRIPTION:
                    lines.append(f"  Description: {e.d2_description or 'Not set'}")
                elif e.state == EightDState.D3_INTERIM:
                    lines.append(f"  Interim Action: {e.d3_interim_action or 'Not set'}")
                elif e.state == EightDState.D4_ROOT_CAUSE:
                    lines.append(f"  Root Cause: {e.d4_root_cause or 'Not set'}")
                elif e.state == EightDState.D5_CORRECTION:
                    lines.append(f"  Corrective Action: {e.d5_corrective_action or 'Not set'}")

                lines.append("")
                lines.append(self.bold("Actions:"))
                lines.append(f"  [w] Advance to next D stage")

        lines.append("")
        lines.append(self.bold("Actions:"))
        lines.append(f"  [n] Create new 8D report")
        lines.append(f"  [1-{len(eightds)}] Select report")
        lines.append(f"  [←] Back to dashboard")

        return "\n".join(lines)

    def render_graph_view(self):
        """Render the knowledge graph view."""
        lines = []
        lines.append(self.bold("═══ Knowledge Graph ═══"))
        lines.append("")

        nodes = self.state.list_graph_nodes()
        if not nodes:
            lines.append(self.dim("  No nodes yet. Press [g] to add one."))
        else:
            # Group by type
            by_type = {}
            for n in nodes:
                type_name = n.node_type.value
                if type_name not in by_type:
                    by_type[type_name] = []
                by_type[type_name].append(n)

            for type_name, type_nodes in sorted(by_type.items()):
                lines.append(self.bold(f"{type_name} ({len(type_nodes)}):"))
                for n in type_nodes[:5]:
                    selected = "► " if n.id == self.selected_node_id else "  "
                    rpn_str = f" | RPN: {n.rpn}" if n.rpn > 0 else ""
                    lines.append(f"  {selected}{n.name}{rpn_str}")
                if len(type_nodes) > 5:
                    lines.append(f"  ... and {len(type_nodes) - 5} more")
                lines.append("")

        if self.selected_node_id:
            node = self.state.get_graph_node(self.selected_node_id)
            if node:
                neighbors = self.state.get_node_neighbors(node.id)
                lines.append(self.bold(f"Neighbors of '{node.name}':"))
                if neighbors:
                    for n in neighbors:
                        lines.append(f"  → {n.name} ({n.node_type.value})")
                else:
                    lines.append(self.dim("  No connections yet"))
                lines.append("")
                lines.append(self.bold("Actions:"))
                lines.append(f"  [v] View neighbors")
                lines.append(f"  [e] Connect to another node")

        lines.append("")
        lines.append(self.bold("Actions:"))
        lines.append(f"  [g] Add new node")
        lines.append(f"  [e] Add edge between nodes")
        lines.append(f"  [1-{len(nodes)}] Select node")
        lines.append(f"  [←] Back to dashboard")

        return "\n".join(lines)

    def render_message_area(self):
        """Render the message/status area."""
        return self.dim(self.message)

    def render_shortcuts(self):
        """Render keyboard shortcuts."""
        lines = []
        lines.append("")
        lines.append(self.bold("Shortcuts:"))
        lines.append("  [1] Dashboard  [2] FMEA  [3] 8D  [4] Graph  [q] Quit")
        return "\n".join(lines)

    def render(self):
        """Render the full frame."""
        self.clear()

        # Header
        print(self.bold("=" * 60))
        print(self.bold("  QMS State Model Prototype"))
        print(self.bold("=" * 60))
        print("")

        # Current view
        if self.current_view == "dashboard":
            print(self.render_dashboard())
        elif self.current_view == "fmea":
            print(self.render_fmea_view())
        elif self.current_view == "eightd":
            print(self.render_eightd_view())
        elif self.current_view == "graph":
            print(self.render_graph_view())

        # Message area
        print("")
        print("-" * 60)
        print(self.render_message_area())

        # Shortcuts
        print(self.render_shortcuts())

    def input_prompt(self, prompt: str) -> str:
        """Get user input with a prompt."""
        print("\033[K", end="")  # Clear to end of line
        try:
            return input(prompt).strip()
        except EOFError:
            return "q"

    def handle_dashboard_input(self, key: str):
        if key == "1":
            self.message = "Already on dashboard"
        elif key == "2":
            self.current_view = "fmea"
            self.message = "Switched to FMEA view"
        elif key == "3":
            self.current_view = "eightd"
            self.message = "Switched to 8D view"
        elif key == "4":
            self.current_view = "graph"
            self.message = "Switched to Graph view"
        elif key == "q":
            return False
        else:
            self.message = f"Unknown key: {key}"
        return True

    def handle_fmea_input(self, key: str):
        fmeas = self.state.list_fmeas()

        if key == "1":
            self.current_view = "dashboard"
            self.message = "Back to dashboard"
        elif key == "f":
            # Create new FMEA
            doc_no = self.input_prompt("Document No: ") or f"PFMEA-{len(fmeas)+1:03d}"
            title = self.input_prompt("Title: ") or "New FMEA"
            fmea_type = FMEAType.PFMEA
            pl_code = self.input_prompt("Product Line (DC-DC-100/PCB-SMT-200/IM-HG-300): ") or "PCB-SMT-200"

            fmea = FMEADocument(
                document_no=doc_no,
                title=title,
                fmea_type=fmea_type,
                product_line_code=pl_code
            )
            self.state.create_fmea(fmea)
            self.message = f"Created FMEA: {doc_no}"

        elif key == "t" and self.selected_fmea_id:
            f = self.state.get_fmea(self.selected_fmea_id)
            if f:
                # Show valid transitions
                print("\033[2J\033[H", end="")
                print(f"Current state: {f.state.name}")
                print("Valid transitions:")
                valid = []
                for next_state in FMEAState:
                    if f.can_transition_to(next_state):
                        valid.append(next_state)
                        print(f"  [{len(valid)}] {next_state.name}")

                choice = self.input_prompt("Select transition (or [c] cancel): ")
                if choice.isdigit() and 1 <= int(choice) <= len(valid):
                    new_state = valid[int(choice) - 1]
                    if f.transition_to(new_state):
                        self.message = f"Transitioned to {new_state.name}"
                    else:
                        self.message = "Transition failed"
                else:
                    self.message = "Cancelled"

        elif key == "d" and self.selected_fmea_id:
            del self.state.fmeas[self.selected_fmea_id]
            self.selected_fmea_id = None
            self.message = "FMEA deleted"

        elif key.isdigit() and 1 <= int(key) <= len(fmeas):
            self.selected_fmea_id = fmeas[int(key) - 1].id
            self.message = f"Selected {fmeas[int(key) - 1].document_no}"

        else:
            self.message = f"Unknown key: {key}"

        return True

    def handle_eightd_input(self, key: str):
        eightds = self.state.list_eightds()

        if key == "1":
            self.current_view = "dashboard"
            self.message = "Back to dashboard"
        elif key == "n":
            # Create new 8D
            doc_no = self.input_prompt("Document No: ") or f"8D-{len(eightds)+1:03d}"
            title = self.input_prompt("Title: ") or "New 8D Report"
            pl_code = self.input_prompt("Product Line: ") or "PCB-SMT-200"
            severity = self.input_prompt("Severity (致命/严重/一般/轻微): ") or "一般"

            report = EightDReport(
                document_no=doc_no,
                title=title,
                product_line_code=pl_code,
                severity=severity
            )
            self.state.create_eightd(report)
            self.message = f"Created 8D: {doc_no}"

        elif key == "w" and self.selected_eightd_id:
            e = self.state.get_eightd(self.selected_eightd_id)
            if e:
                # Find next valid state
                next_states = EIGHTD_TRANSITIONS.get(e.state, [])
                if next_states:
                    next_state = next_states[0]  # Linear progression
                    confirm = self.input_prompt(f"Advance to {next_state.name}? (y/n): ")
                    if confirm.lower() == "y":
                        if e.transition_to(next_state):
                            self.message = f"Advanced to {next_state.name}"
                        else:
                            self.message = "Transition failed"
                    else:
                        self.message = "Cancelled"
                else:
                    self.message = "No valid transitions (already at end state)"

        elif key.isdigit() and 1 <= int(key) <= len(eightds):
            self.selected_eightd_id = eightds[int(key) - 1].id
            self.message = f"Selected {eightds[int(key) - 1].document_no}"

        else:
            self.message = f"Unknown key: {key}"

        return True

    def handle_graph_input(self, key: str):
        nodes = self.state.list_graph_nodes()

        if key == "1":
            self.current_view = "dashboard"
            self.message = "Back to dashboard"
        elif key == "g":
            # Add new node
            print("\033[2J\033[H", end="")
            print("Node types:")
            for i, nt in enumerate(NodeType):
                print(f"  [{i+1}] {nt.value}")

            choice = self.input_prompt("Select type: ")
            if choice.isdigit() and 1 <= int(choice) <= len(NodeType):
                node_type = list(NodeType)[int(choice) - 1]
                name = self.input_prompt("Node name: ") or "Unnamed"
                pl_code = self.input_prompt("Product Line: ") or "PCB-SMT-200"

                node = GraphNode(
                    node_type=node_type,
                    name=name,
                    product_line_code=pl_code
                )
                if self.state.add_graph_node(node):
                    self.message = f"Added node: {name}"
                else:
                    self.message = "Failed to add node"

        elif key == "e" and self.selected_node_id:
            # Add edge
            print("\033[2J\033[H", end="")
            print("Select target node:")
            nodes = self.state.list_graph_nodes()
            for i, n in enumerate(nodes):
                if n.id != self.selected_node_id:
                    print(f"  [{i+1}] {n.name} ({n.node_type.value})")

            choice = self.input_prompt("Target node: ")
            if choice.isdigit() and 1 <= int(choice) <= len(nodes):
                target_node = nodes[int(choice) - 1]

                print("\nEdge types:")
                edge_types = list(EdgeType)
                for i, et in enumerate(edge_types[:10]):
                    print(f"  [{i+1}] {et.value}")

                edge_choice = self.input_prompt("Edge type: ")
                if edge_choice.isdigit() and 1 <= int(edge_choice) <= len(edge_types):
                    edge_type = edge_types[int(edge_choice) - 1]

                    edge = GraphEdge(
                        edge_type=edge_type,
                        source_id=self.selected_node_id,
                        target_id=target_node.id
                    )
                    if self.state.graph.add_edge(edge):
                        self.message = f"Added edge: {edge_type.value}"
                    else:
                        self.message = "Failed to add edge"

        elif key == "v" and self.selected_node_id:
            neighbors = self.state.get_node_neighbors(self.selected_node_id)
            self.message = f"Node has {len(neighbors)} neighbors"

        elif key.isdigit() and 1 <= int(key) <= len(nodes):
            self.selected_node_id = nodes[int(key) - 1].id
            self.message = f"Selected {nodes[int(key) - 1].name}"

        else:
            self.message = f"Unknown key: {key}"

        return True

    def run(self):
        """Main loop."""
        running = True

        while running:
            self.render()

            key = self.input_prompt("> ").lower()

            if self.current_view == "dashboard":
                running = self.handle_dashboard_input(key)
            elif self.current_view == "fmea":
                running = self.handle_fmea_input(key)
            elif self.current_view == "eightd":
                running = self.handle_eightd_input(key)
            elif self.current_view == "graph":
                running = self.handle_graph_input(key)

        print("\nGoodbye!")


if __name__ == "__main__":
    TUI().run()
