#!/usr/bin/env python3
"""
Install FSM (Finite State Machine) Analysis Queries and Canvas Actions
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from db_utils import get_db, get_system_db

def install_fsm_queries():
    """Install FSM-related saved queries and canvas actions"""
    db = get_db()
    
    print("="*60)
    print("Installing FSM Analysis Queries & Actions")
    print("="*60)
    

    
    # Get viewpoint ID
    viewpoints = db.collection('_viewpoints')
    vp_docs = list(viewpoints.all())
    if not vp_docs:
        print("ERROR: No viewpoint found. Please open graph visualizer first.")
        return
    
    viewpoint_id = vp_docs[0]['_id']
    graph_id = vp_docs[0].get('graphId', 'IC_Knowledge_Graph')
    # =============================================================
    # SAVED QUERIES
    # =============================================================
    
    sys_db = get_system_db()
    
    # Ensure collections exist in _system
    if not sys_db.has_collection('_editor_saved_queries'):
        try:
            sys_db.create_collection('_editor_saved_queries')
        except: pass

    if not sys_db.has_collection('_canvasActions'):
        try:
           sys_db.create_collection('_canvasActions')
        except: pass
        
    queries_col = sys_db.collection('_editor_saved_queries')
    actions_col = sys_db.collection('_canvasActions')
    
    saved_queries = [
        {
            "name": "FSM: All State Machines",
            "title": "FSM: All State Machines",
            "queryText": """
FOR fsm IN FSM_StateMachine
  SORT fsm.name
  LET module = DOCUMENT('RTL_Module', fsm.parent_module)
  LET states = (
    FOR s IN FSM_State
      FILTER s.fsm_id == fsm._key
      RETURN 1
  )
  RETURN {
    fsm: fsm.name,
    module: module.name,
    state_register: fsm.state_register,
    state_count: LENGTH(states),
    encoding: fsm.metadata.encoding_type
  }
            """,
            "description": "Lists all detected state machines with their module and state count"
        },
        {
            "name": "FSM: State Machine Detail",
            "title": "FSM: State Machine Detail",
            "queryText": """
LET fsm_name = "or1200_dc_fsm_state"

FOR fsm IN FSM_StateMachine
  FILTER fsm.name == fsm_name
  LET states = (
    FOR s IN FSM_State
      FILTER s.fsm_id == fsm._key
      SORT s.name
      RETURN {
        name: s.name,
        encoding: s.encoding,
        is_reset: s.metadata.is_reset_state
      }
  )
  LET transitions = (
    FOR s IN FSM_State
      FILTER s.fsm_id == fsm._key
      FOR v, e IN 1..1 OUTBOUND s._id TRANSITIONS_TO
        RETURN {
          from: s.name,
          to: v.name,
          condition: e.condition
        }
  )
  RETURN {
    fsm: fsm.name,
    module: fsm.parent_module,
    state_register: fsm.state_register,
    states: states,
    transitions: transitions
  }
            """,
            "description": "Detailed view of a specific FSM including all states and transitions"
        },
        {
            "name": "FSM: State Transition Matrix",
            "title": "FSM: State Transition Matrix",
            "queryText": """
LET fsm_name = "or1200_dc_fsm_state"

FOR fsm IN FSM_StateMachine
  FILTER fsm.name == fsm_name
  LET states = (
    FOR s IN FSM_State
      FILTER s.fsm_id == fsm._key
      SORT s.name
      RETURN s.name
  )
  LET transitions = (
    FOR s IN FSM_State
      FILTER s.fsm_id == fsm._key
      FOR v, e IN 1..1 OUTBOUND s._id TRANSITIONS_TO
        RETURN {
          from: s.name,
          to: v.name,
          condition: e.condition
        }
  )
  RETURN {
    fsm: fsm.name,
    states: states,
    matrix: transitions
  }
            """,
            "description": "Shows the state transition matrix for analysis"
        },
        {
            "name": "FSM: Find Unreachable States",
            "title": "FSM: Find Unreachable States",
            "queryText": """
FOR fsm IN FSM_StateMachine
  LET all_states = (
    FOR s IN FSM_State
      FILTER s.fsm_id == fsm._key
      RETURN s
  )
  LET reachable_states = (
    FOR s IN FSM_State
      FILTER s.fsm_id == fsm._key
      FILTER s.metadata.is_reset_state == true
      FOR v, e, p IN 1..10 OUTBOUND s._id TRANSITIONS_TO
        RETURN DISTINCT v._key
  )
  LET unreachable = (
    FOR s IN all_states
      FILTER s._key NOT IN reachable_states
      FILTER s.metadata.is_reset_state != true
      RETURN s.name
  )
  FILTER LENGTH(unreachable) > 0
  RETURN {
    fsm: fsm.name,
    module: fsm.parent_module,
    unreachable_states: unreachable
  }
            """,
            "description": "Identifies states that cannot be reached from reset state"
        },
        {
            "name": "FSM: Find Dead-End States",
            "title": "FSM: Find Dead-End States",
            "queryText": """
FOR fsm IN FSM_StateMachine
  LET states = (
    FOR s IN FSM_State
      FILTER s.fsm_id == fsm._key
      RETURN s
  )
  LET dead_ends = (
    FOR s IN states
      LET outgoing = (
        FOR v IN 1..1 OUTBOUND s._id TRANSITIONS_TO
          RETURN 1
      )
      FILTER LENGTH(outgoing) == 0
      RETURN s.name
  )
  FILTER LENGTH(dead_ends) > 0
  RETURN {
    fsm: fsm.name,
    module: fsm.parent_module,
    dead_end_states: dead_ends,
    note: "States with no outgoing transitions"
  }
            """,
            "description": "Finds states with no outgoing transitions (potential bugs)"
        },
        {
            "name": "FSM: State Complexity Analysis",
            "title": "FSM: State Complexity Analysis",
            "queryText": """
FOR fsm IN FSM_StateMachine
  LET states = (
    FOR s IN FSM_State
      FILTER s.fsm_id == fsm._key
      RETURN s
  )
  LET transitions = (
    FOR s IN states
      FOR v, e IN 1..1 OUTBOUND s._id TRANSITIONS_TO
        RETURN 1
  )
  LET avg_transitions = LENGTH(transitions) / LENGTH(states)
  RETURN {
    fsm: fsm.name,
    module: fsm.parent_module,
    state_count: LENGTH(states),
    transition_count: LENGTH(transitions),
    avg_transitions_per_state: ROUND(avg_transitions * 100) / 100,
    complexity: (
      LENGTH(states) < 5 ? "Simple" :
      LENGTH(states) < 10 ? "Moderate" :
      "Complex"
    )
  }
            """,
            "description": "Analyzes FSM complexity metrics"
        },
        {
            "name": "FSM: Module with FSMs",
            "title": "FSM: Module with FSMs",
            "queryText": """
FOR m IN RTL_Module
  LET fsms = (
    FOR f IN 1..1 OUTBOUND m._id HAS_FSM
      RETURN f
  )
  FILTER LENGTH(fsms) > 0
  RETURN {
    module: m.name,
    fsm_count: LENGTH(fsms),
    fsms: fsms[*].name
  }
            """,
            "description": "Lists modules that contain state machines"
        },
        {
            "name": "FSM: State Register Signals",
            "title": "FSM: State Register Signals",
            "queryText": """
FOR fsm IN FSM_StateMachine
  LET signal = (
    FOR s IN 1..1 OUTBOUND fsm._id STATE_REGISTER
      RETURN {
        name: s.name,
        width: s.width,
        direction: s.direction
      }
  )[0]
  RETURN {
    fsm: fsm.name,
    state_register: fsm.state_register,
    signal_details: signal
  }
            """,
            "description": "Shows the connection between FSMs and their state register signals"
        }
    ]
    
    # =============================================================
    # CANVAS ACTIONS
    # =============================================================
    
    canvas_actions = [
        {
            "name": "Show FSM States",
            "title": "Show FSM States",
            "queryText": """
FOR node IN @nodes
  FILTER IS_SAME_COLLECTION('FSM_StateMachine', node)
  FOR state IN 1..1 OUTBOUND node HAS_STATE
    RETURN {nodes: [node, state], edges: []}
            """,
            "graphId": graph_id,
            "bindVariables": {"nodes": []},
            "description": "Expand FSM to show all its states"
        },
        {
            "name": "Show State Transitions",
            "title": "Show State Transitions",
            "queryText": """
FOR node IN @nodes
  FILTER IS_SAME_COLLECTION('FSM_State', node)
  FOR v, e IN 1..1 OUTBOUND node TRANSITIONS_TO
    RETURN {nodes: [node, v], edges: [e]}
            """,
            "graphId": graph_id,
            "bindVariables": {"nodes": []},
            "description": "Show outgoing transitions from selected state"
        },
        {
            "name": "Show Full FSM Diagram",
            "title": "Show Full FSM Diagram",
            "queryText": """
FOR node IN @nodes
  FILTER IS_SAME_COLLECTION('FSM_StateMachine', node)
  LET states = (
    FOR s IN 1..1 OUTBOUND node HAS_STATE
      RETURN s
  )
  LET transitions = (
    FOR s IN states
      FOR v, e IN 1..1 OUTBOUND s TRANSITIONS_TO
        RETURN {from: s, to: v, edge: e}
  )
  LET all_nodes = APPEND([node], states)
  LET all_edges = transitions[*].edge
  RETURN {nodes: all_nodes, edges: all_edges}
            """,
            "graphId": graph_id,
            "bindVariables": {"nodes": []},
            "description": "Show complete FSM with all states and transitions"
        },
        {
            "name": "Show FSM in Module Context",
            "title": "Show FSM in Module Context",
            "queryText": """
FOR node IN @nodes
  FILTER IS_SAME_COLLECTION('FSM_StateMachine', node)
  LET module = (
    FOR m IN 1..1 INBOUND node HAS_FSM
      RETURN m
  )[0]
  LET state_signal = (
    FOR s IN 1..1 OUTBOUND node STATE_REGISTER
      RETURN s
  )[0]
  RETURN {
    nodes: [node, module, state_signal],
    edges: []
  }
            """,
            "graphId": graph_id,
            "bindVariables": {"nodes": []},
            "description": "Show FSM with its parent module and state register"
        },
        {
            "name": "Trace State Path",
            "title": "Trace State Path",
            "queryText": """
FOR node IN @nodes
  FILTER IS_SAME_COLLECTION('FSM_State', node)
  FOR v, e, p IN 1..5 OUTBOUND node TRANSITIONS_TO
    RETURN {
      nodes: APPEND([node], p.vertices),
      edges: p.edges
    }
            """,
            "graphId": graph_id,
            "bindVariables": {"nodes": []},
            "description": "Trace possible execution paths from selected state (up to 5 hops)"
        }
    ]
    
    # Install saved queries
    print("\nInstalling Saved Queries...")
    for query in saved_queries:
        query_key = query['name'].replace(' ', '_').replace(':', '')
        
        # Check if exists
        if queries_col.has(query_key):
            queries_col.update(query_key, query)
            print(f"  ✓ Updated: {query['name']}")
        else:
            query['_key'] = query_key
            queries_col.insert(query)
            print(f"  ✓ Created: {query['name']}")
    
    # Install canvas actions
    print("\nInstalling Canvas Actions...")
    for action in canvas_actions:
        action_key = action['name'].replace(' ', '_')
        
        # Check if exists
        if actions_col.has(action_key):
            actions_col.update(action_key, action)
            action_id = f"_canvasActions/{action_key}"
            print(f"  ✓ Updated: {action['name']}")
        else:
            action['_key'] = action_key
            actions_col.insert(action)
            action_id = f"_canvasActions/{action_key}"
            print(f"  ✓ Created: {action['name']}")
        
        # Link to viewpoint
        edge_key = f"vp_to_{action_key}"
        edge_doc = {
            '_key': edge_key,
            '_from': viewpoint_id,
            '_to': action_id
        }
        
        if viewpoint_actions_col.has(edge_key):
            viewpoint_actions_col.update(edge_key, edge_doc)
        else:
            viewpoint_actions_col.insert(edge_doc)
    
    print(f"\n{'='*60}")
    print(f"✓ Installed {len(saved_queries)} queries and {len(canvas_actions)} actions")
    print(f"{'='*60}")
    print("\nUsage:")
    print("  1. Open Graph Visualizer")
    print("  2. Saved Queries: Use query dropdown")
    print("  3. Canvas Actions: Right-click on FSM/State nodes")
    print()

if __name__ == "__main__":
    install_fsm_queries()

