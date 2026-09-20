"""Bounded collectors for the public search responses used by portal websites.

No cookies, credentials, CAPTCHA solving, challenge bypass, or proxy rotation.
Pagination is bounded and coverage describes the actual query, never all housing.
"""
from __future__ import annotations
import http.client
import json
import ssl
import time
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urlencode, quote
from .ingestion import _resolve_public, parse_upload, MAX_BYTES

QA_URL = 'https://www.quintoandar.com.br/api/yellow-pages/v2/search'
LOFT_URL = 'https://landscape-api.loft.com.br/listing/v2/search'
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36'
RETURN_FIELDS = ['id','coverImage','salePrice','iptuPlusCondominium','area','address','regionName','city','type','forSale','bedrooms','parkingSpaces','bathrooms','installations','listingTags','floor','latitude','longitude']


def _request_json(url, payload=None):
    parsed, address, port = _resolve_public(url)
    if parsed.hostname not in ('www.quintoandar.com.br', 'landscape-api.loft.com.br') or parsed.scheme != 'https':
        raise ValueError('Endpoint de portal não permitido')
    headers = {'Host': parsed.hostname, 'User-Agent': USER_AGENT, 'Accept-Encoding': 'identity'}
    if parsed.hostname == 'www.quintoandar.com.br':
        headers.update({'Content-Type':'text/plain;charset=UTF-8', 'Accept':'application/p_click_version.V3.4+p_click_sale_version.V1+json', 'Origin':'https://www.quintoandar.com.br'})
    else:
        headers.update({'Accept':'application/json', 'Referer':'https://loft.com.br/', 'Origin':'https://loft.com.br'})
    body = json.dumps(payload).encode() if payload is not None else None
    connection = http.client.HTTPConnection(address, port, timeout=20)
    try:
        connection.connect()
        connection.sock = ssl.create_default_context().wrap_socket(connection.sock, server_hostname=parsed.hostname)
        connection.request('POST' if payload is not None else 'GET', parsed.path + ('?' + parsed.query if parsed.query else ''), body=body, headers=headers)
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f'Coleta HTTP retornou {response.status}; sem contorno de bloqueio. Tente novamente mais tarde.')
        if response.getheader('Content-Encoding','identity') != 'identity':
            raise ValueError('Resposta comprimida inesperada')
        length = response.getheader('Content-Length')
        if length and int(length) > MAX_BYTES:
            raise ValueError('Página excede 10 MB')
        chunks, size, deadline = [], 0, time.monotonic()+35
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError('Tempo máximo de coleta excedido')
            if connection.sock is not None:
                connection.sock.settimeout(min(20, remaining))
            chunk = response.read1(min(65536, MAX_BYTES+1-size))
            if not chunk: break
            chunks.append(chunk); size += len(chunk)
            if size > MAX_BYTES: raise ValueError('Página excede 10 MB')
        try:
            data = json.loads(b''.join(chunks))
        except (ValueError, UnicodeError):
            raise ValueError('Portal não retornou JSON; página de bloqueio ou formato alterado') from None
        if not isinstance(data,dict): raise ValueError('Formato do portal alterado')
        return data
    except (OSError,http.client.HTTPException):
        raise ValueError('Falha de rede ao consultar portal') from None
    finally:
        connection.close()


def _bounds(profile):
    raw = profile.get('search_bounds')
    if not raw: return None
    keys = ('north','south','east','west')
    result = {}
    for key in keys:
        value = raw.get(key, raw.get('bounds_'+key))
        if value is None: raise ValueError('Limites geográficos exigem north/south/east/west')
        value = float(value)
        if not (-90 <= value <= 90 if key in ('north','south') else -180 <= value <= 180):
            raise ValueError('Limite geográfico inválido')
        result[key] = value
    if result['north'] <= result['south'] or result['east'] <= result['west']:
        raise ValueError('Limites geográficos invertidos')
    return result


def _qa_payload(profile, page, size):
    filters = {'availability':'any','occupancy':'any','country_code':'BR','house_type':['Apartamento','StudioOuKitchenette'],
               'offset':page*size,'page_size':size,'sorting':{'criteria':'sale_price','order':'asc'}}
    area = {k:v for k,v in {'min_area':profile.get('area_min'),'max_area':profile.get('area_max')}.items() if v is not None}
    cost = {k:v for k,v in {'min_value':profile.get('budget_min'),'max_value':profile.get('budget_max')}.items() if v is not None}
    if area: filters['area']=area
    if cost: filters['cost']={'cost_type':'sale_price',**cost}
    filters['min_bedrooms']=profile.get('bedrooms_min',0)
    filters['min_parking_spaces']=profile.get('parking_min',0)
    bounds = _bounds(profile)
    if bounds:
        filters['map'] = {'bounds_'+k:v for k,v in bounds.items()}
        filters['map'].update(center_lat=(bounds['north']+bounds['south'])/2,center_lng=(bounds['east']+bounds['west'])/2)
    return {'business_context':'SALE','filters':filters,'force_raw_search':False,'relax_query':False,'return':RETURN_FIELDS,'search_query_context':'unknown'}


def _loft_url(profile,page,size):
    params={'page':page,'hitsPerPage':size,'orderBy[]':'rankB'}
    for key,field in {'priceMin':'budget_min','priceMax':'budget_max','areaMin':'area_min','areaMax':'area_max','bedrooms':'bedrooms_min','parkingSpots':'parking_min'}.items():
        if profile.get(field) is not None: params[key]=profile[field]
    cities=profile.get('cities') or ['São Paulo']
    params['cities[]']=[city + ', SP' if ',' not in city else city for city in cities]
    bounds = _bounds(profile)
    if bounds: params.update(neLatBoundary=bounds['north'],neLngBoundary=bounds['east'],swLatBoundary=bounds['south'],swLngBoundary=bounds['west'])
    return LOFT_URL+'?'+urlencode(params,doseq=True)


def _qa_record(hit, observed):
    data = hit.get('_source')
    if not isinstance(data,dict): raise ValueError('Anúncio QuintoAndar sem _source')
    identifier=hit.get('_id',data.get('id'))
    if identifier is None: raise ValueError('Anúncio sem identificador')
    raw={**data,'source':'QuintoAndar','external_id':str(identifier),'url':f'https://www.quintoandar.com.br/imovel/{quote(str(identifier),safe="")}/comprar/','observed_at':observed}
    # The sale search field sums condominium and the monthly IPTU installment.
    # Verified against public detail price panels (IPTU is displayed as 12x).
    if data.get('iptuPlusCondominium') is not None:
        raw['combined_monthly_cost'] = data['iptuPlusCondominium']
        raw['combined_cost_period'] = 'monthly'
    image=data.get('coverImage')
    if image and str(image).startswith(('http://','https://')):
        raw['image_url']=image
    elif image:
        # Media hostname is the public image route used in portal cards.
        raw['image_url']='https://www.quintoandar.com.br/img/xxl/'+quote(str(image),safe='')
    raw['occupied'] = True if 'BUY_RENTED' in data.get('listingTags',[]) or 'BUY_RENTED' in hit.get('fields',{}).get('listingTags',[]) else None
    return raw


def _loft_record(data,observed):
    address=data.get('address') or {}
    identifier=data.get('id')
    if identifier is None: raise ValueError('Anúncio sem identificador')
    raw={'source':'Loft','external_id':str(identifier),'url':f'https://loft.com.br/imovel/{quote(str(identifier),safe="")}',
         'price':data.get('price'),'area':data.get('area'),'bedrooms':data.get('bedrooms'),'bathrooms':data.get('restrooms'),
         'parking':data.get('parkingSpots'),'floor':data.get('floor'),'condo_fee':data.get('complexFee'),
         'property_tax':data.get('propertyTax'),'tax_period':'unknown','address':address.get('streetFullName'),
         'city':address.get('city'),'neighborhood':address.get('neighborhood'),'latitude':address.get('lat'),'longitude':address.get('lng'),
         'property_type': data.get('homeType') or address.get('type'),'status':data.get('status'),'amenities':data.get('amenities'),
         'observed_at':observed,'occupied':None}
    image=data.get('image_thumbnail') or data.get('image')
    if image:
        raw['image_url'] = image if str(image).startswith(('http://','https://')) else 'https://content.loft.com.br/homes/'+quote(str(identifier),safe='')+'/'+quote(str(image),safe='')
    return raw


def _collect_region(portal: str, profile: dict) -> dict:
    """Collect at most max_pages pages; fail closed on partial transport/schema failure.

    search_bounds accepts north/south/east/west (or bounds_ aliases). Date is
    actual collection time. Unknown walking distance, floor and occupancy stay unknown.
    """
    if portal not in ('quintoandar','loft'): raise ValueError('Portal desconhecido')
    max_pages=max(1,min(int(profile.get('max_pages',5)),25))
    size=max(1,min(int(profile.get('page_size',50)),100))
    result={'records':[],'errors':[],'warnings':[], 'coverage':{'pages':0,'complete':False,'reason':'page_limit','total_reported':None,'received':0}}
    seen=set(); observed=datetime.now(timezone.utc).isoformat(); total=None
    for page in range(max_pages):
        if time.monotonic() >= profile.get("_collection_deadline", float("inf")):
            result["coverage"]["reason"] = "time_limit"
            break
        try:
            data=_request_json(QA_URL,_qa_payload(profile,page,size)) if portal=='quintoandar' else _request_json(_loft_url(profile,page,size))
            if portal=='quintoandar':
                hits=data.get('hits',{}); rows=hits.get('hits')
                totalinfo=hits.get('total'); exact=isinstance(totalinfo,dict) and totalinfo.get('relation')=='eq'
                total=totalinfo.get('value') if isinstance(totalinfo,dict) else totalinfo
                if data.get('engine_timed_out') or data.get('relaxed'):
                    raise ValueError('Portal retornou consulta incompleta ou critérios relaxados')
            else:
                rows=data.get('listings'); pagination=data.get('pagination',{}); total=pagination.get('total'); exact=isinstance(total,int)
            if not isinstance(rows,list): raise ValueError('Estrutura de resultados do portal mudou')
            result['coverage']['pages']+=1;result['coverage']['total_reported']=total
            fresh=0
            for row in rows:
                raw=_qa_record(row,observed) if portal=='quintoandar' else _loft_record(row,observed)
                identity=raw['external_id']
                if identity in seen: continue
                seen.add(identity);fresh+=1
                occupied=raw.pop('occupied')
                if profile.get('exclude_occupied') and occupied is True: continue
                if portal=='loft' and raw.get('property_type') not in (None,'apartment','studio','Apartamento','studio_apartment'): continue
                parsed=parse_upload(json.dumps([raw]).encode(),'portal.json')
                if parsed['errors']:
                    result['errors'].extend(parsed['errors']);continue
                record=parsed['records'][0];record['occupied']=occupied;record['data_origin']='portal'
                result['records'].append(record)
            result['coverage']['received']=len(seen)
            if exact and isinstance(total,int) and len(seen)>=total:
                result['coverage'].update(complete=True,reason='exhausted');break
            if not rows:
                result['coverage']['reason']='empty_page_before_total' if total else 'empty_page_unverified';break
            if not fresh:
                result['coverage']['reason']='repeated_page';break
            if page+1<max_pages: time.sleep(0.4)
        except (ValueError,TypeError,KeyError) as exc:
            result['errors'].append({'row':0,'message':str(exc)});result['coverage']['reason']='error';break
    if result['errors']:
        result['coverage']['complete']=False
    result['warnings'].append('Coleta de preços anunciados; disponibilidade e critérios desconhecidos precisam de confirmação.')
    if not result['coverage']['complete']: result['warnings'].append('Cobertura parcial: '+result['coverage']['reason'])
    return result



DEFAULT_SP_BOUNDS = {'north': -23.35, 'south': -24.01, 'east': -46.36, 'west': -46.83}


def collect_portal(portal: str, profile: dict) -> dict:
    """Collect São Paulo city only, across user bounds, at most 20 pages/run.

    The public portal contracts currently verified here cover São Paulo/SP.
    Other cities fail explicitly instead of silently querying another location.
    Bounds list is merged by stable source + external_id, never address similarity.
    """
    if portal not in ('quintoandar', 'loft'):
        raise ValueError('Portal desconhecido')
    from .locations import canonical_city
    cities = profile.get('cities') or ['São Paulo']
    for city in cities:
        if canonical_city(city) != 'São Paulo':
            raise ValueError('Coleta automática atualmente validada somente para São Paulo/SP')
    bounds = profile.get('search_bounds') or [DEFAULT_SP_BOUNDS]
    if isinstance(bounds, dict): bounds = [bounds]
    if not isinstance(bounds, list) or not bounds or len(bounds) > 4:
        raise ValueError('Configure de uma a quatro regiões de busca')
    result = {'records': [], 'errors': [], 'warnings': [], 'coverage': {'pages': 0, 'complete': True, 'reason': 'exhausted', 'total_reported': None, 'received': 0, 'regions': []}}
    remaining = 20
    deadline = time.monotonic() + 180
    seen = set()
    for index, region in enumerate(bounds):
        if not isinstance(region, dict): raise ValueError('Região geográfica inválida')
        if not remaining:
            result['coverage'].update(complete=False, reason='run_page_limit')
            break
        local_profile = {**profile, '_collection_deadline': deadline, 'cities': ['São Paulo'], 'search_bounds': region,
                         'max_pages': min(remaining, max(1, min(int(profile.get('max_pages', 5)), 5)))}
        part = _collect_region(portal, local_profile)
        coverage = part['coverage']
        result['coverage']['regions'].append({'region': region.get('name') or str(index + 1), **coverage})
        result['coverage']['pages'] += coverage['pages']
        remaining -= coverage['pages']
        if not coverage['complete']:
            result['coverage'].update(complete=False, reason=coverage['reason'])
        result['errors'].extend(part['errors'])
        result['warnings'].extend(part['warnings'])
        for record in part['records']:
            identity = (record['source'], record['external_id'])
            if identity not in seen:
                seen.add(identity); result['records'].append(record)
        # A blocked transport does not justify retries across additional regions.
        if part['errors']: break
    result['coverage']['received'] = len(seen)
    if len(bounds) == 1 and result['coverage']['regions']:
        result['coverage']['total_reported'] = result['coverage']['regions'][0]['total_reported']
    neighborhoods = profile.get('neighborhoods') or []
    if neighborhoods:
        def normalized_location(value):
            return ' '.join(''.join(c for c in unicodedata.normalize('NFD', str(value).casefold()) if not unicodedata.combining(c)).split())
        requested = {normalized_location(value) for value in neighborhoods}
        result['records'] = [r for r in result['records'] if not r.get('neighborhood') or normalized_location(r['neighborhood']) in requested]
        result['warnings'].append('Bairros aplicados como filtro local aos resultados coletados; bairros desconhecidos preservados para avaliação. A paginação limitada não cobre necessariamente todos os anúncios desses bairros.')
        result['coverage']['neighborhood_filter'] = 'local'
        result['coverage']['retained'] = len(result['records'])
    result['warnings'] = list(dict.fromkeys(result['warnings']))
    return result


def _quinto_detail_html(identifier, timeout=20, _url=None, _redirects=0):
    """Read public detail, allowing two strictly same-property HTTPS redirects."""
    import re
    if not re.fullmatch(r'[0-9]{1,20}', str(identifier)):
        raise ValueError('Identificador QuintoAndar inválido para detalhes')
    from urllib.parse import urljoin, urlsplit
    url = _url or 'https://www.quintoandar.com.br/imovel/' + str(identifier) + '/comprar'
    target = urlsplit(url)
    allowed_path = '/imovel/' + str(identifier) + '/comprar'
    if (target.scheme != 'https' or target.hostname != 'www.quintoandar.com.br'
            or target.username or target.password or target.port not in (None, 443)
            or target.fragment or target.query
            or not (target.path == allowed_path or target.path.startswith(allowed_path + '/'))):
        raise ValueError('Redirecionamento de detalhe fora do imóvel permitido')
    parsed, address, port = _resolve_public(url)
    timeout = max(0.1, min(float(timeout), 20))
    deadline = time.monotonic() + timeout
    connection = http.client.HTTPConnection(address, port, timeout=timeout)
    try:
        def remaining_timeout():
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise ValueError('Tempo máximo de detalhe excedido')
            if connection.sock is not None: connection.sock.settimeout(remaining)
        connection.connect()
        remaining_timeout()
        connection.sock = ssl.create_default_context().wrap_socket(connection.sock, server_hostname=parsed.hostname)
        remaining_timeout()
        connection.request('GET', parsed.path, headers={'Host':parsed.hostname,'User-Agent':USER_AGENT,'Accept':'text/html','Accept-Encoding':'identity'})
        remaining_timeout()
        response = connection.getresponse()
        if response.status in (301,302,303,307,308):
            location = response.getheader('Location')
            if _redirects >= 2 or not location:
                raise ValueError('Redirecionamento de detalhe excedeu limite seguro')
            redirected = urljoin(url, location)
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise ValueError('Tempo máximo de detalhe excedido')
            connection.close()
            return _quinto_detail_html(identifier, timeout=remaining, _url=redirected, _redirects=_redirects+1)
        if response.status != 200: raise ValueError(f'Detalhe QuintoAndar HTTP {response.status}')
        if response.getheader('Content-Encoding','identity') != 'identity': raise ValueError('Detalhe comprimido inesperado')
        length = response.getheader('Content-Length')
        if length and int(length) > MAX_BYTES: raise ValueError('Detalhe excede 10 MB')
        chunks, size = [], 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise ValueError('Tempo máximo de detalhe excedido')
            if connection.sock is not None: connection.sock.settimeout(remaining)
            chunk = response.read1(min(65536, MAX_BYTES+1-size))
            if not chunk: break
            chunks.append(chunk); size += len(chunk)
            if size > MAX_BYTES: raise ValueError('Detalhe excede 10 MB')
        return b''.join(chunks).decode('utf-8')
    except (OSError,http.client.HTTPException,UnicodeError):
        raise ValueError('Falha de rede ou formato no detalhe QuintoAndar') from None
    finally:
        connection.close()


def _parse_quinto_detail(html):
    import re
    import math
    match = re.search(r'<script\b[^>]*\bid=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html, re.S)
    if not match: raise ValueError('Detalhe sem dados públicos estruturados')
    try:
        info = json.loads(match.group(1))['props']['pageProps']['initialState']['house']['houseInfo']
    except (ValueError,KeyError,TypeError):
        raise ValueError('Estrutura de detalhe QuintoAndar mudou') from None
    result = {}
    bounds = info.get('rangeFloor') or {}
    lower, upper = bounds.get('min'), bounds.get('max')
    def finite(value):
        return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)
    if finite(lower) and finite(upper) and lower <= upper and int(lower)==lower and int(upper)==upper:
        result.update(floor_min_reported=int(lower),floor_max_reported=int(upper))
    address = info.get('address') or {}
    if isinstance(address,dict):
        lat,lng = address.get('lat'),address.get('lng')
        if finite(lat) and finite(lng) and -90<=lat<=90 and -180<=lng<=180:
            result.update(latitude=lat,longitude=lng,coordinate_precision='portal_reported')
        for incoming,outgoing in [('street','address'),('neighborhood','neighborhood'),('city','city')]:
            if isinstance(address.get(incoming),str) and address[incoming].strip(): result[outgoing]=address[incoming].strip()[:2000]
    # Read the public price panel, never infer tax periodicity from iptuType.
    from html import unescape
    visible_html = re.sub(r'<script\b[^>]*>.*?</script>', '', html, flags=re.S | re.I)
    price_text = unescape(re.sub(r'<[^>]+>', ' ', visible_html))
    periods={'monthly':'monthly','mensal':'monthly','annual':'annual','anual':'annual'}
    period=periods.get(str(info.get('iptuPeriod') or info.get('propertyTaxPeriod') or '').lower())
    if not period and re.search(r'IPTU\s+12\s*x\s+R\$', price_text, re.I):
        period = 'monthly'
    if period and finite(info.get('iptu')) and info['iptu']>=0:
        result.update(property_tax=info['iptu'],tax_period=period)
    condo_period=periods.get(str(info.get('condoPeriod') or '').lower())
    # condoPrice is the condominium charge displayed by the public detail panel.
    if condo_period in (None, 'monthly') and finite(info.get('condoPrice')) and info['condoPrice']>=0:
        result['condo_fee']=info['condoPrice']
    if 'condo_fee' in result and result.get('tax_period') == 'monthly':
        result.update(combined_monthly_cost=result['condo_fee']+result['property_tax'], combined_cost_period='monthly')
    for installation in info.get('installations') or []:
        if isinstance(installation,dict) and installation.get('key')=='ELEVADOR' and installation.get('value') in ('SIM','NAO'):
            result['elevator']=installation['value']=='SIM'
    return result


def enrich_quinto_details(records, limit=50):
    """Public detail enrichment, 50 requests / 90 seconds max; seven-day DB cache.

    Cache stores only whitelisted public fields, never the HTML/contact details.
    Range endpoints are retained, never converted into a fabricated exact floor.
    """
    from . import storage
    from contextlib import closing
    from datetime import timedelta
    import sqlite3
    limit=max(0,min(int(limit),50)); deadline=time.monotonic()+90
    result={'records':[],'warnings':[]}; requests=0; partial=False; blocked=False
    memo={}
    now=datetime.now(timezone.utc)
    for original in records:
        record=dict(original)
        if record.get('source')!='QuintoAndar': result['records'].append(record);continue
        identifier=str(record.get('external_id',''));key='quinto_detail:'+identifier
        cached=memo.get(key)
        if cached is None:
            try:
                with closing(storage.connect()) as conn:
                    row=conn.execute('SELECT value FROM runtime WHERE key=?',(key,)).fetchone()
                if row:
                    entry=json.loads(row[0]);timestamp=datetime.fromisoformat(entry['observed_at'])
                    if entry.get('cost_schema') == 2 and timestamp.tzinfo is not None and now-timedelta(days=7)<=timestamp<=now:
                        cached=entry
            except (sqlite3.Error,ValueError,KeyError,TypeError): pass
        if cached is None:
            if requests>=limit or time.monotonic()>=deadline or blocked:
                partial=True;result['records'].append(record);continue
            requests+=1
            try:
                fields=_parse_quinto_detail(_quinto_detail_html(identifier,timeout=min(20,max(.1,deadline-time.monotonic()))))
                cached={'observed_at':datetime.now(timezone.utc).isoformat(),'fields':fields,'cost_schema':2}
                with storage.transaction() as conn:
                    conn.execute('INSERT INTO runtime(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(key,storage.dumps(cached)))
            except (ValueError,sqlite3.Error) as error:
                partial=True
                if any(reason in str(error) for reason in ('HTTP 403', 'HTTP 429', 'HTTP 308', 'Redirecionamento')): blocked=True
                result['warnings'].append(str(error));result['records'].append(record);continue
        memo[key]=cached
        fields = dict(cached['fields'])
        # The current search aggregate is fresher than the seven-day detail cache.
        if record.get('combined_monthly_cost') is not None and record.get('combined_cost_period') == 'monthly':
            fields.pop('combined_monthly_cost', None)
            fields.pop('combined_cost_period', None)
        record.update(fields)
        record['detail_observed_at']=cached['observed_at']
        provenance=dict(record.get('provenance') or {})
        provenance.update({field:{'source':'QuintoAndar detalhe público','observed_at':cached['observed_at']} for field in fields})
        record['provenance']=provenance
        result['records'].append(record)
    if partial: result['warnings'].append('Detalhamento parcial: limite de tempo, páginas ou falha; campos desconhecidos foram preservados.')
    result['warnings']=list(dict.fromkeys(result['warnings']))
    return result
