from db_utils import get_db

def audit_all_edges():
    db = get_db()
    
    print('Comprehensive Edge Audit:')
    print('=' * 80)
    
    for col_info in db.collections():
        if col_info['type'] != 'edge':
            continue
            
        col_name = col_info['name']
        if col_name.startswith('_'): # Skip system collections
            continue
            
        print(f'Checking {col_name}...')
        q = f"""
        FOR e IN {col_name}
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
                print(f'[FAIL] {col_name}: {len(dangling)} dangling edges found.')
                for d in dangling[:3]:
                    print(f"  {d['id']}: {d['f']} ({d['fe']}) -> {d['t']} ({d['te']})")
                
                # Automatically delete if identified
                # ids_to_delete = [d['id'] for d in dangling]
                # print(f"  Deleting {len(ids_to_delete)} edges...")
                # db.aql.execute(f"FOR id IN @ids REMOVE id IN {col_name}", bind_vars={'ids': ids_to_delete})
            else:
                print(f'[PASS] {col_name} is clean.')
        except Exception as e:
            print(f'[ERROR] {col_name}: {e}')

if __name__ == "__main__":
    audit_all_edges()
