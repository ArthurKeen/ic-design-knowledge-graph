from db_utils import get_db

def fix_and_deep_audit():
    db = get_db()
    
    # 1. Fix MODIFIED
    print("Fixing MODIFIED dangling edges...")
    q_mod = """
    FOR e IN MODIFIED
    FILTER DOCUMENT(e._to) == null
    REMOVE e IN MODIFIED
    RETURN e._id
    """
    removed = list(db.aql.execute(q_mod))
    print(f"Removed {len(removed)} dangling edges from MODIFIED.")
    
    # 2. Deep Audit across ALL edge collections
    print("\nDeep Audit (Meta-Scan)...")
    edge_cols = [c['name'] for c in db.collections() if c['type'] == 'edge' and not c['name'].startswith('_')]
    
    total_dangling = 0
    for col in edge_cols:
        q = f"""
        FOR e IN {col}
        LET f = DOCUMENT(e._from)
        LET t = DOCUMENT(e._to)
        FILTER f == null OR t == null
        RETURN {{id: e._id, f_null: f==null, t_null: t==null, from_id: e._from, to_id: e._to}}
        """
        results = list(db.aql.execute(q))
        if results:
            print(f"[FAIL] {col}: {len(results)} dangling edges.")
            total_dangling += len(results)
            for r in results[:5]:
                reason = "Both null" if r['f_null'] and r['t_null'] else ("From null" if r['f_null'] else "To null")
                print(f"  {r['id']} ({reason}): {r['from_id']} -> {r['to_id']}")
                
            # AUTO-FIX
            ids = [r['id'] for r in results]
            print(f"  Deleting {len(ids)} edges from {col}...")
            db.aql.execute(f"FOR id IN @ids REMOVE id IN {col}", bind_vars={'ids': ids})
        else:
            print(f"[PASS] {col} is clean.")
            
    print(f"\nDeep Audit Complete. Fixed {total_dangling} dangling edges.")

if __name__ == "__main__":
    fix_and_deep_audit()
