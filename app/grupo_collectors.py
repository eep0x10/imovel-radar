"""Read public SSR listing pages; no login, challenges, internal API or bypass.

VivaReal exposes JSON-LD; OLX exposes listing data in public React flight scripts.
Coverage is a bounded sample of the observed São Paulo search, never a full catalog.
"""
from datetime import datetime, timezone
from html.parser import HTMLParser
import http.client
import json
import math
import re
import urllib.request
import urllib.error
import unicodedata
import time
from urllib.parse import urljoin, urlsplit, parse_qs, urlencode

from .ingestion import MAX_BYTES, _resolve_public, parse_upload

BASE_URLS = {
    'vivareal': 'https://www.vivareal.com.br/venda/sp/sao-paulo/apartamento_residencial/',
    'olx': 'https://www.olx.com.br/imoveis/venda/apartamentos/estado-sp/sao-paulo-e-regiao',
}
LABELS = {'vivareal': 'VivaReal', 'olx': 'OLX'}


def _price_query(value, upper=False):
    # Portal URLs use whole reais. Query broadly, then apply the exact local filter.
    return str(math.ceil(float(value)) if upper else math.floor(float(value)))


def _brl(value):
    if isinstance(value, str):
        text = value.replace('R$', '').strip().replace(' ', '')
        if ',' in text:
            return text.replace('.', '').replace(',', '.')
        if re.fullmatch(r'\d{1,3}(?:\.\d{3})+', text):
            return text.replace('.', '')
        return text
    return value


def _exact_number(value):
    return value if value is not None and re.fullmatch(r'\d+', str(value).strip()) else None


def _city(value):
    return ''.join(c for c in unicodedata.normalize('NFD', str(value or '').casefold()) if not unicodedata.combining(c)).strip()


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirecionamento de catálogo bloqueado')


def _download_html(url, remaining=45):
    parsed, _, _ = _resolve_public(url)
    if parsed.scheme != 'https' or parsed.hostname not in ('www.vivareal.com.br', 'www.olx.com.br') or parsed.port not in (None, 443):
        raise ValueError('Host de catálogo não permitido')
    deadline = time.monotonic() + min(45, remaining)
    request = urllib.request.Request(url, headers={'User-Agent': 'ImovelRadar/1.0 public-feed-research', 'Accept-Encoding': 'identity'})
    # Standard public HTTP client; no cookies, auth, proxies or redirects.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    try:
        with opener.open(request, timeout=min(12, max(.1, remaining))) as response:
            if response.getheader('Content-Encoding', 'identity') != 'identity':
                raise ValueError('Compressão inesperada no catálogo')
            chunks, size = [], 0
            while True:
                budget = deadline - time.monotonic()
                if budget <= 0:
                    raise ValueError('Tempo total do catálogo excedido')
                chunk = response.read1(min(65536, MAX_BYTES + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk); size += len(chunk)
                if size > MAX_BYTES:
                    raise ValueError('Catálogo excede 10 MB')
            return b''.join(chunks).decode('utf-8')
    except urllib.error.HTTPError as exc:
        raise ValueError(f'Catálogo retornou HTTP {exc.code}; coleta interrompida sem contorno de bloqueio') from None
    except (OSError, http.client.HTTPException, UnicodeError):
        raise ValueError('Falha de rede ou codificação do catálogo') from None


class _Page(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.scripts, self.links = [], []
        self.script = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script':
            self.script = [attrs.get('type'), '']
        elif tag == 'a' and attrs.get('href'):
            self.links.append(attrs['href'])

    def handle_data(self, data):
        if self.script is not None:
            self.script[1] += data

    def handle_endtag(self, tag):
        if tag == 'script' and self.script is not None:
            self.scripts.append(self.script)
            self.script = None


def _vr_rows(page, observed):
    products, apartments = [], {}
    for kind, script in page.scripts:
        if kind != 'application/ld+json':
            continue
        try:
            data = json.loads(script)
        except ValueError:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if node.get('@type') == 'Apartment':
                apartments[str(node.get('@id'))] = node
            if node.get('@type') == 'ItemList':
                products.extend(v.get('item', {}) for v in node.get('itemListElement', []) if isinstance(v, dict))
    if not products:
        raise ValueError('Catálogo VivaReal sem ItemList de imóveis reconhecível')
    for item in products:
        offer = item.get('offers') or {}
        url = item.get('url', '')
        # Launches contain area/price ranges from different units, not one apartment.
        if '/imoveis-lancamentos/' in url or offer.get('@type') != 'Offer' or not offer.get('price'):
            continue
        if item.get('additionalType', '').rsplit('/', 1)[-1] != 'Apartment':
            continue
        if offer.get('priceCurrency') != 'BRL':
            continue
        extra = apartments.get(str(item.get('@id')), {})
        size = item.get('floorSize') or {}
        if size.get('unitCode') != 'M2':
            continue
        address = item.get('address') or {}
        features = [v.get('value') for v in item.get('amenityFeature', []) if isinstance(v, dict) and isinstance(v.get('value'), str)]
        image = item.get('image') or []
        fee = offer.get('additionalProperty') or {}
        yield {'source': 'VivaReal', 'external_id': str(item.get('@id') or url), 'url': url, 'title': item.get('name'),
               'price': offer.get('price'), 'area': size.get('value'), 'bedrooms': item.get('numberOfBedrooms'),
               'bathrooms': item.get('numberOfBathroomsTotal'), 'floor': extra.get('floorLevel'),
               'address': address.get('streetAddress'), 'city': address.get('addressLocality'),
               'neighborhood': address.get('addressNeighborhood'), 'property_type': 'apartment',
               'image_url': image[0] if isinstance(image, list) and image else image if isinstance(image, str) else None,
               'condo_fee': fee.get('value') if fee.get('name') == 'Condominium Fee' and fee.get('unitText') == 'BRL/month' else None,
               'elevator': True if 'Elevator' in features else None, 'amenities': features,
               'status': 'active' if offer.get('availability', '').endswith('/InStock') else 'unknown', 'observed_at': observed}


def _olx_rows(page, observed):
    chunks = []
    decoder = json.JSONDecoder()
    for _, script in page.scripts:
        marker = 'self.__next_f.push('
        if not script.startswith(marker):
            continue
        try:
            payload, _ = decoder.raw_decode(script[len(marker):])
            if len(payload) > 1 and isinstance(payload[1], str):
                chunks.append(payload[1])
        except (ValueError, TypeError):
            continue
    text = ''.join(chunks)
    rows = []
    for match in re.finditer(r'"ads"\s*:\s*(?=\[)', text):
        try:
            ads, _ = decoder.raw_decode(text[match.end():])
            if isinstance(ads, list):
                rows.extend(a for a in ads if isinstance(a, dict))
        except ValueError:
            continue
    if not rows:
        raise ValueError('Catálogo OLX sem lista pública de anúncios reconhecível')
    for item in rows:
        props = {p.get('name'): p.get('value') for p in item.get('properties', []) if isinstance(p, dict)}
        kind = props.get('real_estate_type', '')
        if 'Venda' not in kind or 'apartamento' not in kind.lower():
            continue
        size = props.get('size')
        match = re.fullmatch(r'\s*(\d+(?:[.,]\d+)?)\s*m[²2]\s*', str(size))
        if not match:
            continue
        location = item.get('locationDetails') or {}
        images = item.get('images') or []
        yield {'source': 'OLX', 'external_id': str(item['listId']), 'url': item.get('url'), 'title': item.get('subject'),
               'price': _brl(item.get('priceValue') or item.get('price')), 'area': match.group(1), 'bedrooms': _exact_number(props.get('rooms')),
               'bathrooms': _exact_number(props.get('bathrooms')), 'parking': _exact_number(props.get('garage_spaces')), 'city': location.get('municipality'),
               'neighborhood': location.get('neighbourhood'), 'property_type': 'apartment',
               'condo_fee': _brl(props.get('condominio')), 'property_tax': _brl(props.get('iptu')), 'tax_period': 'unknown',
               'image_url': images[0].get('original') if images and isinstance(images[0], dict) else None,
               'status': 'active', 'observed_at': observed}


def collect_grupo_portal(portal, profile):
    if portal not in BASE_URLS:
        raise ValueError('Fonte não habilitada; ZAP apresentou bloqueio HTTP e não é contornado')
    cities = profile.get('cities') or []
    if cities and any(_city(city) != 'sao paulo' for city in cities):
        raise ValueError('Este coletor público tem cobertura verificada apenas para São Paulo')
    url = BASE_URLS[portal]
    if portal == 'vivareal':
        query = {key: _price_query(profile[field], field == "budget_max") for key, field in [('precoMinimo', 'budget_min'), ('precoMaximo', 'budget_max')] if profile.get(field) is not None}
        if query:
            url += '?' + urlencode(query)
    max_pages = max(1, min(int(profile.get('max_pages', 3)), 20))
    result = {'records': [], 'errors': [], 'warnings': ['Amostra pública de São Paulo; campos não publicados permanecem desconhecidos.'],
              'coverage': {'pages': 0, 'complete': False, 'reason': 'page_limit', 'received': 0, 'excluded_known_filters': 0, 'scope': 'São Paulo / SP'}}
    if profile.get('search_bounds'):
        result['warnings'].append('Limites do mapa pendentes: estes catálogos não publicam coordenadas nesta listagem; confirme a localização no anúncio.')
    deadline = time.monotonic() + 180
    seen, visited = set(), set()
    for page_number in range(1, max_pages + 1):
        try:
            if url in visited:
                result['coverage']['reason'] = 'repeated_page'
                break
            visited.add(url)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                result['coverage']['reason'] = 'time_limit'
                break
            page = _Page(_download_html(url, remaining))
            observed = datetime.now(timezone.utc).isoformat()
            raw_rows = list(_vr_rows(page, observed) if portal == 'vivareal' else _olx_rows(page, observed))
            result['coverage']['pages'] += 1
            fresh = 0
            for raw in raw_rows:
                if raw['external_id'] in seen:
                    continue
                seen.add(raw['external_id']); fresh += 1
                parsed = parse_upload(json.dumps([raw]).encode(), 'public.json')
                if parsed['errors']:
                    result['errors'].append({'row': 0, 'message': 'Anúncio público mudou de formato; revisão necessária'})
                    continue
                record = parsed['records'][0]
                # Public OLX region also includes neighbouring cities; preserve the explicit scope.
                if _city(record.get('city')) != 'sao paulo':
                    result['coverage']['excluded_known_filters'] += 1
                    continue
                excluded = False
                for field, pref, direction in [('price', 'budget_min', 'min'), ('price', 'budget_max', 'max'), ('area', 'area_min', 'min'), ('area', 'area_max', 'max'), ('bedrooms', 'bedrooms_min', 'min')]:
                    value, limit = record.get(field), profile.get(pref)
                    if value is not None and limit is not None and (value < limit if direction == 'min' else value > limit):
                        excluded = True
                if excluded:
                    result['coverage']['excluded_known_filters'] += 1
                    continue
                record['data_origin'] = 'portal'
                result['records'].append(record)
            result['coverage']['received'] = len(seen)
            if not fresh:
                result['coverage']['reason'] = 'repeated_page'
                break
            key = 'pagina' if portal == 'vivareal' else 'o'
            next_url = None
            for href in page.links:
                candidate = urljoin(url, href)
                parsed = urlsplit(candidate)
                if parsed.scheme == 'https' and parsed.port in (None, 443) and not parsed.username and parsed.hostname == urlsplit(url).hostname and parsed.path == urlsplit(BASE_URLS[portal]).path and parse_qs(parsed.query).get(key) == [str(page_number + 1)]:
                    if portal == 'vivareal':
                        merged = parse_qs(parsed.query)
                        for query_key, field in [('precoMinimo', 'budget_min'), ('precoMaximo', 'budget_max')]:
                            if profile.get(field) is not None:
                                merged[query_key] = [_price_query(profile[field], field == "budget_max")]
                        candidate = parsed._replace(query=urlencode(merged, doseq=True)).geturl()
                    next_url = candidate
                    break
            if not next_url:
                result['coverage']['reason'] = 'no_next_link'
                break
            url = next_url
            if page_number < max_pages:
                time.sleep(.5)
        except (ValueError, TypeError, KeyError) as exc:
            result['errors'].append({'row': 0, 'message': str(exc)[:300]})
            result['coverage']['reason'] = 'error'
            break
    result['warnings'].append('Cobertura parcial: ' + result['coverage']['reason'] + '. Ausência não confirma indisponibilidade.')
    return result
