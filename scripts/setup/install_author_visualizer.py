#!/usr/bin/env python3
"""
Knowledge Transfer & Author Expertise - Graph Visualizer Setup

This script installs saved queries and canvas actions focused on
knowledge transfer, expertise mapping, and collaboration analysis.
"""

import sys
import os
import argparse

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

DEFAULT_GRAPH_NAME = "IC_Knowledge_Graph"
from typing import Optional


def _get_target_db(db_name: str = None):
    if db_name:
        os.environ["ARANGO_DATABASE"] = db_name
        os.environ["LOCAL_ARANGO_DATABASE"] = db_name
    from db_utils import get_db
    return get_db()


def _get_metadata_db(use_system: bool, db_name: str = None):
    from db_utils import get_system_db
    if use_system:
        return get_system_db()
    return _get_target_db(db_name)

def install_author_queries(db, metadata_db, database_name: Optional[str]):
    """Install saved queries for author expertise and knowledge transfer"""
    # Metadata may be stored in _system or in the target DB depending on deployment
    sys_db = metadata_db
    
    # Ensure collection exists
    if not sys_db.has_collection('_editor_saved_queries'):
        try:
            sys_db.create_collection('_editor_saved_queries')
        except Exception:
            pass
        
    queries_col = sys_db.collection('_editor_saved_queries')
    
    queries = [
        {
            "_key": "author_top_maintainers",
            "name": "Author: Top Maintainers by Module Count",
            "title": "Author: Top Maintainers by Module Count",
            "queryText": """// Find authors who maintain the most modules
FOR author IN Author
  LET module_count = LENGTH(
    FOR m IN 1..1 OUTBOUND author MAINTAINS
      RETURN 1
  )
  FILTER module_count > 0
  SORT module_count DESC
  LIMIT 10
  RETURN {
    author: author.name,
    email: author.email,
    modules_maintained: module_count,
    total_commits: author.metadata.total_commits,
    active: author.metadata.active,
    first_seen: author.metadata.first_seen,
    last_seen: author.metadata.last_seen
  }""",
            "bindVariables": {}
        },
        {
            "_key": "author_module_experts",
            "name": "Author: Find Experts for a Module",
            "title": "Author: Find Experts for a Module",
            "queryText": """// Find who maintains a specific module
FOR module IN RTL_Module
  FILTER module.label == @module_name
  FOR author IN 1..1 INBOUND module MAINTAINS
    LET edge = (
      FOR e IN MAINTAINS
        FILTER e._from == author._id AND e._to == module._id
        RETURN e
    )[0]
    SORT edge.commit_count DESC
    RETURN {
      author: author.name,
      email: author.email,
      commits_to_module: edge.commit_count,
      maintenance_score: edge.maintenance_score,
      first_commit: edge.first_commit,
      last_commit: edge.last_commit,
      total_commits: author.metadata.total_commits,
      active: author.metadata.active
    }""",
            "bindVariables": {
                "module_name": "or1200_alu"
            }
        },
        {
            "_key": "author_bus_factor",
            "name": "Author: Bus Factor Analysis (High Risk Modules)",
            "title": "Author: Bus Factor Analysis (High Risk Modules)",
            "queryText": """// Find modules with only one maintainer (bus factor = 1)
FOR module IN RTL_Module
  LET maintainers = (
    FOR author IN 1..1 INBOUND module MAINTAINS
      RETURN author
  )
  FILTER LENGTH(maintainers) == 1
  LET sole_maintainer = maintainers[0]
  RETURN {
    module: module.label,
    module_type: module.type,
    sole_maintainer: sole_maintainer.name,
    maintainer_email: sole_maintainer.email,
    maintainer_active: sole_maintainer.metadata.active,
    maintainer_total_commits: sole_maintainer.metadata.total_commits,
    risk_level: "HIGH",
    recommendation: "Cross-train additional engineers"
  }""",
            "bindVariables": {}
        },
        {
            "_key": "author_collaboration_network",
            "name": "Author: Collaboration Network for Engineer",
            "title": "Author: Collaboration Network for Engineer",
            "queryText": """// Find who collaborates with a specific author
FOR author1 IN Author
  FILTER author1.name == @author_name
  FOR module IN 1..1 OUTBOUND author1 MAINTAINS
    FOR author2 IN 1..1 INBOUND module MAINTAINS
      FILTER author1._id != author2._id
      COLLECT collaborator = author2.name, 
              collab_email = author2.email,
              collab_active = author2.metadata.active
        WITH COUNT INTO shared_modules
      SORT shared_modules DESC
      RETURN {
        collaborates_with: collaborator,
        email: collab_email,
        shared_modules: shared_modules,
        active: collab_active,
        relationship_strength: shared_modules > 20 ? "Strong" : 
                              shared_modules > 10 ? "Medium" : "Weak"
      }""",
            "bindVariables": {
                "author_name": "julius"
            }
        },
        {
            "_key": "author_knowledge_impact",
            "name": "Author: Knowledge Impact (Author → Specs)",
            "title": "Author: Knowledge Impact (Author → Specs)",
            "queryText": """// Trace from author to specifications they've impacted
FOR author IN Author
  FILTER author.name == @author_name
  FOR commit IN 1..1 OUTBOUND author AUTHORED
    FOR module IN 1..1 OUTBOUND commit MODIFIED
      FOR entity IN 1..1 OUTBOUND module RESOLVED_TO
        COLLECT 
          entity_name = entity.entity_name,
          entity_type = entity.entity_type,
          entity_desc = entity.description
          WITH COUNT INTO touch_count
        SORT touch_count DESC
        LIMIT 20
        RETURN {
          specification: entity_name,
          type: entity_type,
          description: entity_desc,
          commits_affecting: touch_count,
          impact: "Author's work affects this specification"
        }""",
            "bindVariables": {
                "author_name": "julius"
            }
        },
        {
            "_key": "author_expertise_areas",
            "name": "Author: Expertise Areas by Module Type",
            "title": "Author: Expertise Areas by Module Type",
            "queryText": """// Show what types of modules an author specializes in
FOR author IN Author
  FILTER author.name == @author_name
  FOR module IN 1..1 OUTBOUND author MAINTAINS
    COLLECT module_type = module.type WITH COUNT INTO module_count
    SORT module_count DESC
    RETURN {
      expertise_area: module_type,
      modules_in_area: module_count,
      specialization_level: module_count > 10 ? "Expert" :
                           module_count > 5 ? "Proficient" : "Familiar"
    }""",
            "bindVariables": {
                "author_name": "julius"
            }
        },
        {
            "_key": "author_knowledge_gaps",
            "name": "Author: Knowledge Gaps (Modules Without Experts)",
            "title": "Author: Knowledge Gaps (Modules Without Experts)",
            "queryText": """// Find modules with no recent maintainer activity
FOR module IN RTL_Module
  LET maintainers = (
    FOR author IN 1..1 INBOUND module MAINTAINS
      FILTER author.metadata.active == true
      RETURN author
  )
  FILTER LENGTH(maintainers) == 0
  RETURN {
    module: module.label,
    module_type: module.type,
    status: "No active maintainers",
    risk_level: "CRITICAL",
    action_required: "Assign new maintainer or document for knowledge transfer"
  }""",
            "bindVariables": {}
        },
        {
            "_key": "author_succession_planning",
            "name": "Author: Succession Planning (Inactive Authors)",
            "title": "Author: Succession Planning (Inactive Authors)",
            "queryText": """// Find modules maintained by inactive authors
FOR author IN Author
  FILTER author.metadata.active == false
  LET modules = (
    FOR module IN 1..1 OUTBOUND author MAINTAINS
      RETURN module.label
  )
  FILTER LENGTH(modules) > 0
  RETURN {
    inactive_author: author.name,
    last_seen: author.metadata.last_seen,
    modules_at_risk: modules,
    module_count: LENGTH(modules),
    priority: LENGTH(modules) > 10 ? "HIGH" : 
             LENGTH(modules) > 5 ? "MEDIUM" : "LOW",
    recommendation: "Identify successors and schedule knowledge transfer"
  }""",
            "bindVariables": {}
        },
        {
            "_key": "author_team_coverage",
            "name": "Author: Team Coverage Matrix",
            "title": "Author: Team Coverage Matrix",
            "queryText": """// Show how many authors know each module
FOR module IN RTL_Module
  LET maintainer_count = LENGTH(
    FOR author IN 1..1 INBOUND module MAINTAINS
      RETURN 1
  )
  LET maintainers = (
    FOR author IN 1..1 INBOUND module MAINTAINS
      RETURN author.name
  )
  RETURN {
    module: module.label,
    maintainer_count: maintainer_count,
    maintainers: maintainers,
    bus_factor: maintainer_count,
    status: maintainer_count == 0 ? "ABANDONED" :
            maintainer_count == 1 ? "HIGH_RISK" :
            maintainer_count == 2 ? "MEDIUM_RISK" : "WELL_COVERED",
    recommendation: maintainer_count < 2 ? "Add backup maintainer" : "Adequate coverage"
  }""",
            "bindVariables": {}
        },
        {
            "_key": "author_commit_history",
            "name": "Author: Commit History Timeline",
            "title": "Author: Commit History Timeline",
            "queryText": """// Show an author's commit history over time
FOR author IN Author
  FILTER author.name == @author_name
  FOR commit IN 1..1 OUTBOUND author AUTHORED
    SORT commit.metadata.timestamp DESC
    LIMIT 50
    RETURN {
      date: commit.metadata.timestamp,
      commit_hash: commit.hash,
      message: commit.metadata.message,
      author: commit.metadata.author,
      modules_modified: LENGTH(
        FOR m IN 1..1 OUTBOUND commit MODIFIED
          RETURN 1
      )
    }""",
            "bindVariables": {
                "author_name": "julius"
            }
        }
    ]

    if database_name:
        for q in queries:
            q["databaseName"] = database_name
    
    print("\nInstalling Author Expertise Saved Queries...")
    installed = 0
    updated = 0
    
    for query in queries:
        try:
            if queries_col.has(query['_key']):
                queries_col.update(query)
                updated += 1
                print(f"  [UPDATED] {query['name']}")
            else:
                queries_col.insert(query)
                installed += 1
                print(f"  [NEW] {query['name']}")
        except Exception as e:
            print(f"  [ERROR] {query['name']}: {e}")
    
    print(f"\nSaved Queries: {installed} new, {updated} updated")
    return len(queries)


def install_author_canvas_actions(db, metadata_db, graph_name: str):
    """Install canvas actions for author expertise"""
    sys_db = metadata_db
    
    # _canvasActions is a Visualizer metadata collection created by the UI.
    if not sys_db.has_collection('_canvasActions'):
        print("[PREREQ] Collection _canvasActions not found in this database.")
        print("Action: Open Graph Visualizer for this DB (Graphs → IC_Knowledge_Graph) once, then rerun this script.")
        return 0
        
    actions_col = sys_db.collection('_canvasActions')
    # _viewpointActions is also Visualizer metadata; do not attempt to create it programmatically.
    if not db.has_collection('_viewpointActions'):
        print("[PREREQ] Collection _viewpointActions not found in this database.")
        print("Action: Open Graph Visualizer for this DB (Graphs → IC_Knowledge_Graph) once, then rerun this script.")
        return 0
    viewpoint_actions_col = db.collection('_viewpointActions')
    
    # Get the viewpoint ID
    if not db.has_collection('_viewpoints'):
        print("[ERROR] _viewpoints collection not found. Open the graph once in the Visualizer, then rerun.")
        return 0

    viewpoints = list(db.collection('_viewpoints').all())
    if not viewpoints:
        print("[ERROR] No viewpoints found. Create a graph view first.")
        return 0

    # Prefer viewpoint matching the target graph
    target_graph = graph_name or DEFAULT_GRAPH_NAME
    viewpoint = None
    for vp in viewpoints:
        if vp.get("graphId") == target_graph:
            viewpoint = vp
            break
    if viewpoint is None:
        viewpoint = viewpoints[0]
    viewpoint_id = viewpoint['_id']
    
    actions = [
        {
            "_key": "show_author_expertise",
            "name": "Show Author's Expertise",
            "title": "Show Author's Expertise",
            "queryText": """// Show all modules this author maintains
FOR author_id IN @nodes
  FOR module IN 1..1 OUTBOUND author_id MAINTAINS
    RETURN DISTINCT module""",
            "graphId": target_graph,
            "bindVariables": {
                "nodes": []
            }
        },
        {
            "_key": "show_author_commits",
            "name": "Show Author's Commits",
            "title": "Show Author's Commits",
            "queryText": """// Show all commits by this author
FOR author_id IN @nodes
  FOR commit IN 1..1 OUTBOUND author_id AUTHORED
    RETURN DISTINCT commit""",
            "graphId": target_graph,
            "bindVariables": {
                "nodes": []
            }
        },
        {
            "_key": "show_module_maintainers",
            "name": "Show Module Maintainers",
            "title": "Show Module Maintainers",
            "queryText": """// Show who maintains this module
FOR module_id IN @nodes
  FOR author IN 1..1 INBOUND module_id MAINTAINS
    RETURN DISTINCT author""",
            "graphId": target_graph,
            "bindVariables": {
                "nodes": []
            }
        },
        {
            "_key": "show_author_collaborators",
            "name": "Show Collaborators",
            "title": "Show Collaborators",
            "queryText": """// Show who this author collaborates with
FOR author_id IN @nodes
  FOR module IN 1..1 OUTBOUND author_id MAINTAINS
    FOR collaborator IN 1..1 INBOUND module MAINTAINS
      FILTER collaborator._id != author_id
      RETURN DISTINCT collaborator""",
            "graphId": target_graph,
            "bindVariables": {
                "nodes": []
            }
        },
        {
            "_key": "show_author_impact",
            "name": "Show Author's Specification Impact",
            "title": "Show Author's Specification Impact",
            "queryText": """// Trace author's work to affected specifications
FOR author_id IN @nodes
  FOR commit IN 1..1 OUTBOUND author_id AUTHORED
    FOR module IN 1..1 OUTBOUND commit MODIFIED
      FOR entity IN 1..1 OUTBOUND module RESOLVED_TO
        RETURN DISTINCT entity""",
            "graphId": target_graph,
            "bindVariables": {
                "nodes": []
            }
        },
        {
            "_key": "show_commit_context",
            "name": "Show Commit Context (Author + Modules)",
            "title": "Show Commit Context (Author + Modules)",
            "queryText": """// Show commit's author and affected modules
FOR commit_id IN @nodes
  LET author = FIRST(
    FOR a IN 1..1 INBOUND commit_id AUTHORED
      RETURN a
  )
  LET modules = (
    FOR m IN 1..1 OUTBOUND commit_id MODIFIED
      RETURN m
  )
  RETURN UNION(
    author ? [author] : [],
    modules
  )""",
            "graphId": target_graph,
            "bindVariables": {
                "nodes": []
            }
        }
    ]
    
    print("\nInstalling Author Expertise Canvas Actions...")
    installed = 0
    updated = 0
    
    for action in actions:
        try:
            # Insert or update action
            if actions_col.has(action['_key']):
                actions_col.update(action)
                updated += 1
                status = "UPDATED"
            else:
                actions_col.insert(action)
                installed += 1
                status = "NEW"
            
            # Link to viewpoint if not already linked
            edge_key = f"{viewpoint_id.split('/')[1]}_{action['_key']}"
            link = {
                '_key': edge_key,
                '_from': viewpoint_id,
                '_to': f"_canvasActions/{action['_key']}"
            }
            
            if not viewpoint_actions_col.has(edge_key):
                viewpoint_actions_col.insert(link)
            
            print(f"  [{status}] {action['name']}")
            
        except Exception as e:
            print(f"  [ERROR] {action['name']}: {e}")
    
    print(f"\nCanvas Actions: {installed} new, {updated} updated")
    return len(actions)


def main():
    parser = argparse.ArgumentParser(description="Install author expertise saved queries and canvas actions")
    parser.add_argument("--db", help="Target database name (e.g., ic-knowledge-graph-1)")
    parser.add_argument("--graph", default=DEFAULT_GRAPH_NAME, help="Target graph name (default: IC_Knowledge_Graph)")
    parser.add_argument(
        "--use-system-metadata",
        action="store_true",
        help="Install _editor_saved_queries and _canvasActions into _system instead of the target DB",
    )
    args = parser.parse_args()

    print("="*70)
    print("Knowledge Transfer & Author Expertise - Visualizer Setup")
    print("="*70)

    db = _get_target_db(args.db)
    metadata_db = _get_metadata_db(args.use_system_metadata, args.db)
    print(f"\nConnected to: {db.name}")
    
    # Install queries
    query_count = install_author_queries(db, metadata_db=metadata_db, database_name=args.db)
    
    # Install canvas actions
    action_count = install_author_canvas_actions(db, metadata_db=metadata_db, graph_name=args.graph)
    
    print("\n" + "="*70)
    print("Installation Complete!")
    print("="*70)
    print(f"\nInstalled:")
    print(f"  - {query_count} Saved Queries")
    print(f"  - {action_count} Canvas Actions")
    
    print("\nUsage:")
    print("  1. Open ArangoDB web interface")
    print("  2. Navigate to Graphs → IC_Knowledge_Graph")
    print("  3. Select 'hardware-design' theme from Legend")
    print("  4. Use saved queries from the Queries panel")
    print("  5. Select Author nodes and use canvas actions")
    
    print("\nKey Queries:")
    print("  - 'Author: Top Maintainers' - See who maintains the most")
    print("  - 'Author: Bus Factor Analysis' - Find high-risk modules")
    print("  - 'Author: Collaboration Network' - See who works together")
    print("  - 'Author: Knowledge Gaps' - Find modules without experts")
    
    print("\nKey Canvas Actions:")
    print("  - Select Author → 'Show Author's Expertise'")
    print("  - Select Module → 'Show Module Maintainers'")
    print("  - Select Author → 'Show Collaborators'")
    print("  - Select Author → 'Show Author's Specification Impact'")
    
    return True


if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)

