"""Frozen account searches with transactional baselines and idempotent notifications."""
import json

from . import storage
from .domain import evaluate_property
from .sale_scope import rental_listing


def searches(conn, user_id):
    result = []
    for row in conn.execute("SELECT * FROM saved_searches WHERE user_id=? ORDER BY id DESC", (user_id,)):
        item = dict(row)
        item['profile'] = json.loads(item['profile'])
        item['enabled'] = bool(item['enabled'])
        item['match_count'] = conn.execute("SELECT COUNT(*) FROM saved_search_matches WHERE search_id=?", (item['id'],)).fetchone()[0]
        result.append(item)
    return result


def reconcile(conn, user_id, search_id=None, baseline=False):
    """Caller owns BEGIN IMMEDIATE, so ingestion and baseline cannot race."""
    active = [s for s in searches(conn, user_id) if s['enabled'] and (search_id is None or s['id'] == search_id)]
    if not active:
        return 0
    items = [storage.load_property(r) for r in conn.execute("SELECT * FROM properties WHERE user_id=? ORDER BY id", (user_id,))]
    count = 0
    for search in active:
        for item in items:
            if rental_listing(item) or item.get('status') in ('inactive', 'unavailable', 'sold'):
                continue
            if search['construction'] != 'all' and item['construction_status'] != search['construction']:
                continue
            if search['q'] and search['q'].casefold() not in ' '.join(str(item.get(k) or '') for k in ('title', 'address', 'neighborhood', 'city', 'source')).casefold():
                continue
            if not evaluate_property(item, [], search['profile'])['eligible']:
                continue
            # Keep identity even if the source later enriches an address/canonical key.
            if conn.execute('SELECT 1 FROM saved_search_matches WHERE search_id=? AND property_id=?', (search['id'], item['id'])).fetchone():
                continue
            added = conn.execute('INSERT OR IGNORE INTO saved_search_matches VALUES(?,?,?,?)', (search['id'], item['canonical_key'], item['id'], storage.now_iso())).rowcount
            if not added:
                continue
            count += 1
            if not baseline:
                conn.execute('''INSERT OR IGNORE INTO alerts(user_id,property_id,kind,title,body,created_at,dedupe_key,saved_search_id)
                    VALUES(?,?,?,?,?,?,?,?)''', (user_id, item['id'], 'saved_search_match', 'Novo imóvel: ' + search['name'],
                    item.get('title') or item.get('address') or item['source'], storage.now_iso(),
                    f"search:{search['id']}:{item['canonical_key']}", search['id']))
    return count


def create(conn, user_id, payload):
    timestamp = storage.now_iso()
    sid = conn.execute('''INSERT INTO saved_searches(user_id,name,profile,q,construction,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?)''', (user_id, payload['name'], storage.dumps(payload['profile']), payload['q'].strip(), payload['construction'], timestamp, timestamp)).lastrowid
    baseline = reconcile(conn, user_id, sid, baseline=True)
    return {**next(s for s in searches(conn, user_id) if s['id'] == sid), 'baseline_count': baseline}


def notifications(conn, user_id, page=1, page_size=50, unread_only=False):
    where = 'a.user_id=? AND a.saved_search_id IS NOT NULL'
    unread = conn.execute('SELECT COUNT(*) FROM alerts a WHERE ' + where + ' AND a.read=0', (user_id,)).fetchone()[0]
    if unread_only:
        where += ' AND a.read=0'
    total = conn.execute('SELECT COUNT(*) FROM alerts a WHERE ' + where, (user_id,)).fetchone()[0]
    rows = conn.execute('''SELECT a.id,a.property_id,a.kind,a.title,a.body,a.created_at,a.read,a.saved_search_id,
        s.name AS search_name,p.data AS property_data FROM alerts a
        JOIN saved_searches s ON s.id=a.saved_search_id AND s.user_id=a.user_id
        LEFT JOIN properties p ON p.id=a.property_id AND p.user_id=a.user_id WHERE ''' + where +
        ' ORDER BY a.id DESC LIMIT ? OFFSET ?', (user_id, page_size, (page-1)*page_size))
    items = []
    for row in rows:
        item = dict(row)
        data = json.loads(item.pop('property_data') or '{}')
        item['property_url'] = data.get('url')
        items.append(item)
    return dict(items=items, total=total, unread=unread, page=page, page_size=page_size, has_more=page*page_size < total)
