import json

import pytest

from app import grupo_collectors as collector


def vr_html(price=300000):
    product = {'@type': 'Product', '@id': '123', 'additionalType': 'https://schema.org/Apartment',
               'url': 'https://www.vivareal.com.br/imovel/test-id-123/', 'name': 'Apto',
               'floorSize': {'value': 50, 'unitCode': 'M2'}, 'numberOfBedrooms': 2,
               'address': {'addressLocality': 'São Paulo', 'streetAddress': 'Rua pública'},
               'offers': {'@type': 'Offer', 'price': price, 'priceCurrency': 'BRL', 'availability': 'https://schema.org/InStock',
                          'additionalProperty': {'name': 'Condominium Fee', 'value': 400, 'unitText': 'BRL/month'}}}
    launch = {**product, '@id': 'launch', 'url': 'https://www.vivareal.com.br/imoveis-lancamentos/foo/'}
    data = {'@type': 'ItemList', 'itemListElement': [{'item': product}, {'item': launch}]}
    return '<script type="application/ld+json">' + json.dumps(data) + '</script>'


def olx_html():
    ad = {'listId': 123, 'subject': 'Apto', 'priceValue': 'R$ 300.000',
          'url': 'https://sp.olx.com.br/sao-paulo-e-regiao/imoveis/apto-123',
          'locationDetails': {'municipality': 'São Paulo', 'neighbourhood': 'Mooca'},
          'properties': [{'name': k, 'value': v} for k, v in {'real_estate_type': 'Venda - apartamento padrão', 'size': '50m²', 'rooms': '2', 'garage_spaces': '0', 'iptu': 'R$ 100'}.items()]}
    payload = [1, '0:' + json.dumps({'ads': [ad]})]
    return '<script>self.__next_f.push(' + json.dumps(payload) + ')</script>'


@pytest.mark.parametrize('portal,html', [('vivareal', vr_html()), ('olx', olx_html())])
def test_public_formats_normalize_and_preserve_unknowns(monkeypatch, portal, html):
    monkeypatch.setattr(collector, '_download_html', lambda *args: html)
    result = collector.collect_grupo_portal(portal, {})
    assert not result['errors']
    assert len(result['records']) == 1
    record = result['records'][0]
    assert record['price'] == 300000 and record['area'] == 50
    assert record['floor'] is None and record['occupied'] is None
    assert record['tax_period'] == 'unknown'
    assert not result['coverage']['complete']
    assert result['coverage']['reason'] == 'no_next_link'


def test_partial_zero_does_not_claim_empty_catalog(monkeypatch):
    monkeypatch.setattr(collector, '_download_html', lambda *args: vr_html(700000))
    result = collector.collect_grupo_portal('vivareal', {'budget_max': 330000, 'search_bounds': {'north': 1}})
    assert result['records'] == []
    assert result['coverage']['received'] == 1
    assert result['coverage']['excluded_known_filters'] == 1
    assert result['coverage']['complete'] is False
    assert any('coordenadas' in w for w in result['warnings'])


def test_no_bypass_or_other_city(monkeypatch):
    with pytest.raises(ValueError):
        collector.collect_grupo_portal('zap', {})
    with pytest.raises(ValueError):
        collector.collect_grupo_portal('olx', {'cities': ['Campinas']})
    def blocked(*args):
        raise ValueError('Catálogo retornou HTTP 403')
    monkeypatch.setattr(collector, '_download_html', blocked)
    result = collector.collect_grupo_portal('vivareal', {})
    assert result['errors'] and not result['records']
    assert result['coverage']['reason'] == 'error'


def test_pagination_follows_observed_link_and_detects_repeated_page(monkeypatch):
    html = vr_html() + '<a href="/venda/sp/sao-paulo/apartamento_residencial/?pagina=2">2</a>'
    monkeypatch.setattr(collector, '_download_html', lambda *args: html)
    monkeypatch.setattr(collector.time, 'sleep', lambda _: None)
    result = collector.collect_grupo_portal('vivareal', {'max_pages': 3})
    assert len(result['records']) == 1
    assert result['coverage']['pages'] == 2
    assert result['coverage']['reason'] == 'repeated_page'


def test_olx_qualified_count_remains_unknown_not_schema_failure(monkeypatch):
    html = olx_html().replace('\\"2\\"', '\\"5 ou mais\\"')
    monkeypatch.setattr(collector, '_download_html', lambda *args: html)
    result = collector.collect_grupo_portal('olx', {'bedrooms_min': 2})
    assert not result['errors']
    assert len(result['records']) == 1
    assert result['records'][0]['bedrooms'] is None


def test_pagination_preserves_public_price_filters(monkeypatch):
    requested = []
    html = vr_html() + '<a href="/venda/sp/sao-paulo/apartamento_residencial/?pagina=2">2</a>'
    def download(url, *args):
        requested.append(url)
        return html
    monkeypatch.setattr(collector, '_download_html', download)
    monkeypatch.setattr(collector.time, 'sleep', lambda _: None)
    collector.collect_grupo_portal('vivareal', {'budget_min': 150000, 'budget_max': 330000})
    assert len(requested) == 2
    assert 'precoMinimo=150000' in requested[1] and 'precoMaximo=330000' in requested[1]


def test_float_profile_prices_use_integer_query_on_every_page(monkeypatch):
    from urllib.parse import urlsplit, parse_qs
    urls = []
    def download(url, *args):
        urls.append(url)
        return vr_html() + '<a href="?pagina=2">2</a>'
    monkeypatch.setattr(collector, '_download_html', download)
    result = collector.collect_grupo_portal('vivareal', {'budget_min':150000.0,'budget_max':330000.0,'max_pages':2})
    assert not result['errors']
    assert len(urls) == 2
    for url in urls:
        query = parse_qs(urlsplit(url).query)
        assert query['precoMinimo'] == ['150000']
        assert query['precoMaximo'] == ['330000']
    assert collector._price_query(150000.5) == '150000'
    assert collector._price_query(330000.5, True) == '330001'


@pytest.mark.parametrize('value,expected', [('R$ 300.000',300000),('300000.00',300000),('R$ 2.500,50',2500.5),(2500.5,2500.5)])
def test_currency_does_not_multiply_decimal_prices(value,expected):
    assert float(collector._brl(value)) == expected
