#!/usr/bin/env python3
"""
Knowledge Transfer Enhancements
================================
Implements Week 1 of the Knowledge Transfer Enhancement Plan:
1. Manual enrichment for top authors
2. Knowledge risk scoring
3. Risk assessment and reporting
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
from db_utils import get_db
from datetime import datetime, timedelta


def enrich_top_authors(db):
    """Add team/role information to top authors (manual enrichment)"""
    
    print("\n[Step 1] Enriching Top Authors with Team/Role Information...")
    
    author_col = db.collection('Author')
    
    # Top author enrichments (based on OR1200 project knowledge)
    enrichments = [
        {
            '_key': 'julius',
            'metadata.team': 'CPU Core',
            'metadata.role': 'Lead Engineer',
            'metadata.expertise_areas': ['ALU', 'Register File', 'Control Logic', 'Exception Handling', 'FPU']
        },
        {
            '_key': 'marcus_erlandsson',
            'metadata.team': 'Memory Systems',
            'metadata.role': 'Senior Engineer',
            'metadata.expertise_areas': ['Cache', 'Memory Interface', 'Bus Architecture']
        },
        {
            '_key': 'unneback',
            'metadata.team': 'CPU Core',
            'metadata.role': 'Senior Engineer',
            'metadata.expertise_areas': ['Pipeline', 'Instruction Decode', 'Branch Prediction']
        },
        {
            '_key': 'olof',
            'metadata.team': 'Verification',
            'metadata.role': 'Engineer',
            'metadata.expertise_areas': ['Testing', 'Debugging', 'Benchmarking']
        }
    ]
    
    enriched = 0
    for enrichment in enrichments:
        key = enrichment['_key']
        if author_col.has(key):
            # Get current document
            author = author_col.get(key)
            
            # Update metadata
            if 'metadata' not in author:
                author['metadata'] = {}
            
            author['metadata']['team'] = enrichment.get('metadata.team')
            author['metadata']['role'] = enrichment.get('metadata.role')
            author['metadata']['expertise_areas'] = enrichment.get('metadata.expertise_areas', [])
            
            # Save
            author_col.update({'_key': key, **author})
            enriched += 1
            print(f"  [ENRICHED] {author['name']}: {author['metadata']['role']}, {author['metadata']['team']}")
        else:
            print(f"  [SKIP] {key} not found")
    
    print(f"\n  Enriched {enriched} authors with team/role information")
    return enriched


def calculate_module_risk(db):
    """Calculate knowledge transfer risk for each module"""
    
    print("\n[Step 2] Calculating Knowledge Transfer Risk Scores...")
    
    query = """
    FOR module IN RTL_Module
      LET maintainers = (
        FOR author IN 1..1 INBOUND module MAINTAINS
          RETURN author
      )
      
      LET active_maintainers = (
        FOR m IN maintainers
          FILTER m.metadata.active == true
          RETURN m
      )
      
      LET maintainer_count = LENGTH(maintainers)
      LET active_count = LENGTH(active_maintainers)
      
      // Calculate risk score
      LET bus_factor_risk = (
        maintainer_count == 0 ? 100 :
        maintainer_count == 1 ? 70 :
        maintainer_count == 2 ? 30 : 0
      )
      
      LET activity_risk = (
        active_count == 0 ? 50 :
        active_count < maintainer_count ? 20 : 0
      )
      
      LET total_risk = bus_factor_risk + activity_risk
      
      LET risk_level = (
        total_risk >= 100 ? 'CRITICAL' :
        total_risk >= 70 ? 'HIGH' :
        total_risk >= 30 ? 'MEDIUM' : 'LOW'
      )
      
      RETURN {
        module: module.label,
        module_type: module.type,
        maintainer_count: maintainer_count,
        active_maintainers: active_count,
        maintainers: (FOR m IN maintainers RETURN {
          name: m.name,
          active: m.metadata.active,
          team: m.metadata.team
        }),
        risk_score: total_risk,
        risk_level: risk_level,
        bus_factor: maintainer_count
      }
    """
    
    results = list(db.aql.execute(query))
    
    # Group by risk level
    by_risk = {'CRITICAL': [], 'HIGH': [], 'MEDIUM': [], 'LOW': []}
    for result in results:
        by_risk[result['risk_level']].append(result)
    
    print(f"\n  Analyzed {len(results)} modules:")
    print(f"    CRITICAL: {len(by_risk['CRITICAL'])} modules")
    print(f"    HIGH:     {len(by_risk['HIGH'])} modules")
    print(f"    MEDIUM:   {len(by_risk['MEDIUM'])} modules")
    print(f"    LOW:      {len(by_risk['LOW'])} modules")
    
    return by_risk


def generate_knowledge_transfer_plans(db, high_risk_modules):
    """Generate knowledge transfer plans for high-risk modules"""
    
    print("\n[Step 3] Generating Knowledge Transfer Plans...")
    
    plans = []
    
    for module_data in high_risk_modules[:5]:  # Top 5 highest risk
        module = module_data['module']
        
        # Find potential backup maintainers
        query = """
        FOR module_doc IN RTL_Module
          FILTER module_doc.label == @module
          
          // Find current maintainers
          LET current_maintainers = (
            FOR a IN 1..1 INBOUND module_doc MAINTAINS
              RETURN a
          )
          
          // Find collaborators (work on similar modules)
          LET collaborators = (
            FOR current IN current_maintainers
              FOR other_module IN 1..1 OUTBOUND current MAINTAINS
                FOR collaborator IN 1..1 INBOUND other_module MAINTAINS
                  FILTER collaborator._id NOT IN current_maintainers[*]._id
                  COLLECT collab = collaborator WITH COUNT INTO shared
                  SORT shared DESC
                  LIMIT 3
                  RETURN {
                    name: collab.name,
                    email: collab.email,
                    shared_modules: shared,
                    team: collab.metadata.team,
                    role: collab.metadata.role
                  }
          )
          
          RETURN {
            module: module_doc.label,
            current_maintainers: current_maintainers,
            suggested_backups: collaborators
          }
        """
        
        result = list(db.aql.execute(query, bind_vars={'module': module}))
        if result:
            plan_data = result[0]
            
            # Generate plan
            plan = f"""
# Knowledge Transfer Plan: {module}

**Risk Level**: {module_data['risk_level']}
**Risk Score**: {module_data['risk_score']}/100

## Current State
- **Bus Factor**: {module_data['bus_factor']}
- **Maintainers**: {module_data['maintainer_count']} ({module_data['active_maintainers']} active)
- **Current Team**: {', '.join([m['name'] for m in module_data['maintainers']])}

## Recommended Actions

### Priority 1: Assign Backup Maintainer
"""
            
            if plan_data['suggested_backups']:
                for i, backup in enumerate(plan_data['suggested_backups'][:2], 1):
                    plan += f"""
**Candidate {i}**: {backup['name']} ({backup.get('team', 'Unknown team')})
- Role: {backup.get('role', 'Engineer')}
- Email: {backup['email']}
- Shared modules: {backup['shared_modules']}
- Reason: Strong collaboration history
"""
            else:
                plan += "\n- Identify engineer with bandwidth and relevant skills\n"
            
            plan += f"""
### Priority 2: Knowledge Capture
1. Schedule knowledge transfer session with current maintainer
2. Document critical design decisions
3. Create architecture overview
4. Record walkthrough video/demo

### Priority 3: Documentation Update
1. Update module README
2. Document key algorithms and data structures
3. Add inline comments for complex logic
4. Link to relevant specifications

### Priority 4: Verification
1. New maintainer completes hands-on tasks
2. Code review involvement
3. Bug fix assignment
4. Feature implementation

## Timeline
- Week 1-2: Knowledge capture and documentation
- Week 3-4: Backup maintainer onboarding
- Week 5-6: Verification and handoff

## Success Criteria
- [ ] Bus factor increased to ≥ 2
- [ ] New maintainer completes 3+ commits
- [ ] Documentation updated and reviewed
- [ ] Knowledge transfer session completed

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
            
            plans.append({
                'module': module,
                'risk_level': module_data['risk_level'],
                'plan': plan
            })
            
            print(f"  [PLAN] Generated for {module} ({module_data['risk_level']} risk)")
    
    return plans


def save_knowledge_transfer_plans(plans, output_dir='docs/knowledge-transfer/plans'):
    """Save knowledge transfer plans to files"""
    
    import os
    
    print(f"\n[Step 4] Saving Knowledge Transfer Plans to {output_dir}/...")
    
    # Create directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    for plan_data in plans:
        module = plan_data['module']
        filename = f"{output_dir}/{module}_transfer_plan.md"
        
        with open(filename, 'w') as f:
            f.write(plan_data['plan'])
        
        print(f"  [SAVED] {filename}")
    
    # Create index file
    index = f"""# Knowledge Transfer Plans

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

## High-Risk Modules Requiring Attention

"""
    
    for plan_data in plans:
        index += f"- [{plan_data['module']}](./{plan_data['module']}_transfer_plan.md) - {plan_data['risk_level']} risk\n"
    
    index_file = f"{output_dir}/README.md"
    with open(index_file, 'w') as f:
        f.write(index)
    
    print(f"  [INDEX] {index_file}")
    
    return len(plans)


def generate_risk_report(by_risk):
    """Generate executive summary risk report"""
    
    print("\n[Step 5] Generating Executive Risk Report...")
    
    report = f"""# Knowledge Transfer Risk Assessment

**Date**: {datetime.now().strftime('%Y-%m-%d')}
**Status**: Action Required

---

## Executive Summary

### Overall Health
- **Total Modules**: {sum(len(v) for v in by_risk.values())}
- **Critical Risk**: {len(by_risk['CRITICAL'])} modules
- **High Risk**: {len(by_risk['HIGH'])} modules
- **Medium Risk**: {len(by_risk['MEDIUM'])} modules
- **Low Risk**: {len(by_risk['LOW'])} modules

### Health Score: {(len(by_risk['LOW']) / sum(len(v) for v in by_risk.values()) * 100):.1f}%
(Percentage of modules with low knowledge transfer risk)

---

## Critical Risks [IMMEDIATE ACTION REQUIRED]

"""
    
    if by_risk['CRITICAL']:
        for module in by_risk['CRITICAL'][:10]:
            report += f"""
### {module['module']}
- **Risk Score**: {module['risk_score']}/100
- **Bus Factor**: {module['bus_factor']}
- **Active Maintainers**: {module['active_maintainers']}
- **Action**: Assign maintainer immediately
"""
    else:
        report += "\nNo critical risks identified.\n"
    
    report += """
---

## High Risks [ACTION WITHIN 2 WEEKS]

"""
    
    if by_risk['HIGH']:
        for module in by_risk['HIGH'][:10]:
            report += f"""
### {module['module']}
- **Risk Score**: {module['risk_score']}/100
- **Bus Factor**: {module['bus_factor']}
- **Maintainers**: {', '.join([m['name'] for m in module['maintainers']])}
- **Action**: Schedule knowledge transfer session
"""
    else:
        report += "\nNo high risks identified.\n"
    
    report += f"""
---

## Recommendations

### Immediate (This Week)
1. Address all CRITICAL risk modules (assign maintainers)
2. Review knowledge transfer plans for top 5 HIGH risk modules
3. Schedule knowledge transfer sessions

### Short-term (Next 2 Weeks)
1. Implement knowledge transfer plans for HIGH risk modules
2. Document critical design decisions
3. Assign backup maintainers

### Medium-term (Next Month)
1. Reduce CRITICAL + HIGH risk modules to < 10%
2. Establish knowledge transfer SLAs
3. Implement automated monitoring

---

## Metrics to Track

- **Bus Factor Distribution**: Target < 10% with bus factor = 1
- **Active Maintainer Coverage**: Target 100% modules with ≥ 1 active maintainer
- **Knowledge Concentration**: Target < 30% modules maintained by top 3 engineers

---

**Next Review**: {(datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')}
"""
    
    with open('docs/knowledge-transfer/KNOWLEDGE_TRANSFER_RISK_REPORT.md', 'w') as f:
        f.write(report)
    
    print("  [SAVED] docs/knowledge-transfer/KNOWLEDGE_TRANSFER_RISK_REPORT.md")
    
    return report


def main():
    print("="*70)
    print("Knowledge Transfer Enhancements - Week 1 Implementation")
    print("="*70)
    
    db = get_db()
    print(f"\nConnected to: {db.name}")
    
    # Step 1: Enrich top authors
    enrich_top_authors(db)
    
    # Step 2: Calculate risk scores
    by_risk = calculate_module_risk(db)
    
    # Step 3: Generate knowledge transfer plans for high-risk modules
    high_risk = by_risk['CRITICAL'] + by_risk['HIGH']
    plans = generate_knowledge_transfer_plans(db, high_risk)
    
    # Step 4: Save plans
    save_knowledge_transfer_plans(plans)
    
    # Step 5: Generate executive report
    generate_risk_report(by_risk)
    
    print("\n" + "="*70)
    print("Knowledge Transfer Enhancement Complete!")
    print("="*70)
    
    print(f"\nResults:")
    print(f"  - {len(plans)} knowledge transfer plans generated")
    print(f"  - {len(by_risk['CRITICAL'])} CRITICAL risk modules identified")
    print(f"  - {len(by_risk['HIGH'])} HIGH risk modules identified")
    print(f"  - 1 executive risk report created")
    
    print(f"\nNext Steps:")
    print(f"  1. Review: docs/knowledge-transfer/KNOWLEDGE_TRANSFER_RISK_REPORT.md")
    print(f"  2. Review plans: docs/knowledge-transfer/plans/")
    print(f"  3. Schedule knowledge transfer sessions for CRITICAL modules")
    print(f"  4. Assign backup maintainers for HIGH risk modules")
    
    return True


if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)

