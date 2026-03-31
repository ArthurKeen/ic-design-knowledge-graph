from db_utils import get_db


_DANGLING_AQL = """
FOR e IN @@col
  LET fromExists = (DOCUMENT(e._from) != null)
  LET toExists = (DOCUMENT(e._to) != null)
  FILTER !fromExists OR !toExists
  RETURN { id: e._id, f: e._from, fe: fromExists, t: e._to, te: toExists }
"""


def find_dangling_edges(db, collection_name: str) -> list:
    """Return dangling edges (missing _from or _to targets) in a collection."""
    return list(db.aql.execute(_DANGLING_AQL, bind_vars={"@col": collection_name}))


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

        try:
            dangling = find_dangling_edges(db, col)
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
