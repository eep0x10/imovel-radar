"""Bounded public OSM walking routes; no distance-derived travel time."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import time

import httpx
from . import storage

SOURCE = 'OpenStreetMap / FOSSGIS OSRM'
TTL = 30 * 86400
DAILY_LIMIT = 60
USER_AGENT = 'ImovelRadar/1.5 (https://github.com/eep0x10/imovel-radar)'
QUERY = '[out:json][timeout:10];(nwr[railway=station][station=subway](-23.8,-46.9,-23.3,-46.3);nwr[railway=station][subway=yes](-23.8,-46.9,-23.3,-46.3););out body center;'


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _coords(lat, lon):
    return _number(lat) and _number(lon) and -24 <= lat <= -23 and -47 <= lon <= -46


def _read(key):
    with storage.connect() as db:
        row = db.execute('SELECT value FROM runtime WHERE key=?', ('osm-walking:' + key,)).fetchone()
    try:
        return json.loads(row['value']) if row else None
    except (ValueError, TypeError):
        return None


def _write(key, value):
    with storage.connect() as db:
        db.execute('INSERT OR REPLACE INTO runtime(key,value) VALUES(?,?)', ('osm-walking:' + key, json.dumps(value)))


def _reserve(kind):
    now = time.time()
    day = datetime.fromtimestamp(now, timezone.utc).date().isoformat()
    with storage.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT value FROM runtime WHERE key=?', ('osm-walking:budget',)).fetchone()
        state = json.loads(row['value']) if row else {}
        if state.get('catalog_cooldown' if kind == 'catalog' else 'cooldown', 0) > now:
            return 'provider_unavailable'
        if state.get('next_request', 0) > now:
            return 'rate_limit'
        if state.get('day') != day:
            state.update(day=day, routes=0)
        if kind == 'route' and state.get('routes', 0) >= DAILY_LIMIT:
            return 'daily_limit'
        if kind == 'route':
            state['routes'] = state.get('routes', 0) + 1
        state['next_request'] = now + 1.15
        db.execute('INSERT OR REPLACE INTO runtime VALUES(?,?)', ('osm-walking:budget', json.dumps(state)))
    return None


def _cooldown(kind="route"):
    with storage.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT value FROM runtime WHERE key=?', ('osm-walking:budget',)).fetchone()
        state = json.loads(row['value']) if row else {}
        state['catalog_cooldown' if kind == 'catalog' else 'cooldown'] = time.time() + 900
        db.execute('INSERT OR REPLACE INTO runtime VALUES(?,?)', ('osm-walking:budget', json.dumps(state)))


def _get(client, url, **kwargs):
    with client.stream('GET', url, **kwargs) as response:
        response.raise_for_status()
        body = bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > 2_000_000:
                raise ValueError('response too large')
    return json.loads(body)


def _stations(client):
    cached = _read('stations')
    if cached and time.time() - cached.get('at', 0) < TTL:
        return cached['items'], None
    reason = _reserve('catalog')
    if reason:
        return [], reason
    payload = None
    for endpoint in ('https://overpass-api.de/api/interpreter', 'https://overpass.private.coffee/api/interpreter'):
        try:
            payload = _get(client, endpoint, params={'data': QUERY}, timeout=18)
            if payload.get('remark'):
                raise ValueError('incomplete station response')
            break
        except (httpx.HTTPError, ValueError) as exc:
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (401, 403, 429):
                raise
            if endpoint.endswith('private.coffee/api/interpreter'):
                raise
            time.sleep(1.16)
            reason = _reserve('catalog')
            if reason:
                return [], reason
    stations = {}
    for element in payload.get('elements', []):
        tags = element.get('tags', {})
        if tags.get('railway') != 'station' or not (tags.get('station') == 'subway' or tags.get('subway') == 'yes'):
            continue
        if any(tags.get(k) not in (None, 'no') for k in ('construction', 'disused', 'abandoned', 'proposed')):
            continue
        name = tags.get('name')
        point = element.get('center', element)
        lat, lon = point.get('lat'), point.get('lon')
        if isinstance(name, str) and 0 < len(name) <= 150 and _coords(lat, lon):
            stations.setdefault(name.casefold(), {'name': name, 'latitude': lat, 'longitude': lon})
    items = list(stations.values())
    if not items:
        raise ValueError('no stations')
    _write('stations', {'at': time.time(), 'items': items})
    return items, None


def _distance(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))


def enrich_records(records, profile=None):
    output = deepcopy(records)
    result = dict(records=output, warnings=[], enriched=0, cache_hits=0, lookups=0, requests=0)
    with httpx.Client(timeout=25, follow_redirects=False, trust_env=False, headers={'User-Agent': USER_AGENT}) as client:
        stations = None
        station_coverage = 'mapped'
        for record in output:
            if _number(record.get('metro_minutes')) and record['metro_minutes'] >= 0 and record.get('metro_station'):
                continue
            lat, lon = record.get('latitude'), record.get('longitude')
            reason = 'coordinates_missing'
            if _coords(lat, lon):
                key = 'route:' + hashlib.sha256(f'{lat:.6f},{lon:.6f}'.encode()).hexdigest()
                cached = _read(key) or {}
                if cached.get('entry') and time.time() - cached.get('at', 0) < TTL:
                    record.update(cached['entry'])
                    result['cache_hits'] += 1
                    result['enriched'] += 1
                    continue
                try:
                    phase = 'catalog' if stations is None else 'route'
                    if stations is None:
                        stations, reason = _stations(client)
                        station_coverage = (_read('stations') or {}).get('coverage', 'mapped')
                    phase = 'route'
                    if stations:
                        candidates = sorted(stations, key=lambda s: _distance((lat, lon), (s['latitude'], s['longitude'])))[:3]
                        record['metro_candidate_station'] = candidates[0]['name']
                        routes = cached.get('candidates', {}) if time.time() - cached.get('at', 0) < TTL else {}
                        reason = None
                        for station in candidates:
                            if station['name'] in routes:
                                continue
                            time.sleep(1.16)
                            reason = _reserve('route')
                            if reason:
                                break
                            result['requests'] += 1
                            result['lookups'] += 1
                            url = f"https://routing.openstreetmap.de/routed-foot/route/v1/foot/{lon},{lat};{station['longitude']},{station['latitude']}"
                            payload = _get(client, url, params={'overview': 'false', 'steps': 'false', 'radiuses': '200;200'})
                            choices = payload.get('routes', [])
                            if payload.get('code') == 'NoRoute':
                                routes[station['name']] = None
                            elif payload.get('code') == 'Ok' and choices and all(_number(choices[0].get(f)) and choices[0][f] >= 0 for f in ('duration', 'distance')):
                                routes[station['name']] = {'duration': choices[0]['duration'], 'distance': choices[0]['distance']}
                            else:
                                raise ValueError('invalid route')
                            _write(key, {'at': time.time(), 'candidates': routes})
                        if not reason:
                            valid = [(name, route) for name, route in routes.items() if route]
                            if valid:
                                name, route = min(valid, key=lambda item: item[1]['duration'])
                                entry = dict(metro_minutes=round(route['duration']/60, 2), metro_distance_meters=round(route['distance']), metro_station=name, metro_route_mode='walking', metro_route_source=SOURCE, metro_checked_at=datetime.now(timezone.utc).isoformat(), metro_candidate_limit=len(candidates), metro_station_coverage=station_coverage, metro_status='ready', metro_message='Rota a pé calculada entre as três estações candidatas mais próximas.')
                                record.update(entry)
                                provenance = record.setdefault('provenance', {})
                                for field in ('metro_minutes', 'metro_station', 'metro_distance_meters'):
                                    provenance[field] = {'source': SOURCE, 'observed_at': entry['metro_checked_at']}
                                _write(key, {'at': time.time(), 'entry': entry})
                                result['enriched'] += 1
                                continue
                            reason = 'no_walking_route'
                    else:
                        reason = reason or 'stations_unavailable'
                except (httpx.HTTPError, ValueError, TypeError, KeyError):
                    _cooldown(phase)
                    reason = 'provider_unavailable'
            record['metro_status'] = reason
            record['metro_message'] = {'coordinates_missing': 'Localização precisa indisponível para calcular o trajeto.', 'daily_limit': 'Cálculo a pé pendente: limite diário do serviço público atingido.', 'rate_limit': 'Cálculo a pé aguardando a próxima consulta.', 'no_walking_route': 'Nenhuma rota a pé disponível para as estações candidatas.'}.get(reason, 'Serviço de rotas temporariamente indisponível; tente novamente pelo botão.')
            if record['metro_message'] not in result['warnings']:
                result['warnings'].append(record['metro_message'])
    return result
