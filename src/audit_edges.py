from db_utils import get_db

def audit_edges():
    db = get_db()
    graph_edges = [
        'CONTAINS', 'HAS_PORT', 'HAS_SIGNAL', 'MODIFIED', 
        'RESOLVED_TO', 'REFERENCES', 'WIRED_TO', 
        'CONSOLIDATES', 'OR1200_Golden_Relations', 'OR1200_Relations'
    ]
    
    print('Auditing Edge Integrity:')
    print('=' * 80)
    
    for col in graph_edges:
        if not db.has_collection(col):
            print(f'[SKIP] {col} (Collection missing)')
            continue
            
        q = f"""
        FOR e IN {col}
        LET fromExists = (DOCUMENT(e._from) != null)
        LET toExists = (DOCUMENT(e._to) != null)
        FILTER !fromExists OR !toExists
        RETURN {{
            id: e._id,
            f: e._from,
            fe: fromExists,
            t: e._to,
            te: toExists
        }}
        """
        
        try:
            dangling = list(db.aql.execute(q))
            if dangling:
                print(f'[FAIL] {col}: {len(dangling)} dangling edges found.')
                for d in dangling[:5]:
                    print(f"  {d['id']}: {d['f']} ({d['fe']}) -> {d['t']} ({d['te']})")
                
                # Cleanup option
                print(f"  Action: Run 'db.collection(\"{col}\").remove_match({{\"_id\": d[\"id\"]}})' for all matches.")
            else:
                print(f'[PASS] {col} is clean.')
        except Exception as e:
            print(f'[ERROR] {col}: {e}')

if __name__ == "__main__":
    audit_edges()
