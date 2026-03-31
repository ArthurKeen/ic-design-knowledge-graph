from db_utils import get_db
from audit_edges import find_dangling_edges


def audit_all_edges():
    db = get_db()
    
    print('Comprehensive Edge Audit:')
    print('=' * 80)
    
    for col_info in db.collections():
        if col_info['type'] != 'edge':
            continue
            
        col_name = col_info['name']
        if col_name.startswith('_'):
            continue
            
        print(f'Checking {col_name}...')

        try:
            dangling = find_dangling_edges(db, col_name)
            if dangling:
                print(f'[FAIL] {col_name}: {len(dangling)} dangling edges found.')
                for d in dangling[:3]:
                    print(f"  {d['id']}: {d['f']} ({d['fe']}) -> {d['t']} ({d['te']})")
            else:
                print(f'[PASS] {col_name} is clean.')
        except Exception as e:
            print(f'[ERROR] {col_name}: {e}')

if __name__ == "__main__":
    audit_all_edges()
