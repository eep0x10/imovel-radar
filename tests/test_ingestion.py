import io
import json
import socket
import zipfile
from unittest.mock import patch
import pytest
from app.ingestion import parse_upload, fetch_feed, _resolve_public, MAX_ROWS

BASE = {'source': 'test', 'external_id': '1', 'price': 300000, 'area': 50}

def parse(rows):
    return parse_upload(json.dumps(rows).encode(), 'listings.json')

def test_legacy_aliases_unknown_dates_combined_cost():
    r = parse([{'origem': 'Loft', '_id': 'abc', 'salePrice': 'R$ 350.000,00', 'area': 50, 'iptuPlusCondominium': 450, 'regionName': 'Mooca', 'forSale': 'ACTIVE', 'parkingSpaces': 0}])
    assert not r['errors']
    p = r['records'][0]
    assert p['source'] == 'Loft' and p['external_id'] == 'abc'
    assert p['combined_monthly_cost'] == 450
    assert p['condo_fee'] is None and p['property_tax'] is None
    assert p['observed_at'] is None and p['tax_period'] == 'unknown'
    assert p['neighborhood'] == 'Mooca' and p['status'] == 'active'
    assert p['provenance']['price']['observed_at'] is None

@pytest.mark.parametrize('field,value', [('price', 0), ('area', -1), ('price', float('inf')), ('price', float('nan')), ('url', 'javascript:alert(1)'), ('image_url', 'file:///etc/passwd'), ('bedrooms', 1.5), ('observed_at', 'yesterday'), ('latitude', 91)])
def test_invalid_records(field, value):
    result = parse([{**BASE, field: value}])
    assert not result['records'] and result['errors'][0]['row'] == 1

def test_two_sources_keep_identity_and_zero():
    r = parse([BASE, {**BASE, 'source': 'other', 'parking': 0}])
    assert len(r['records']) == 2
    assert r['records'][1]['parking'] == 0
    assert r['records'][0]['parking'] is None

def test_semicolon_csv():
    r = parse_upload(b'source;external_id;price;area\ntest;1;"300.000,50";50\n', 'a.csv')
    assert r['records'][0]['price'] == 300000.5

def test_row_limit_discards_partial_result():
    r = parse([BASE] * (MAX_ROWS + 1))
    assert r['errors'] and not r['records']

def test_size_limit():
    assert parse_upload(b'x' * (10 * 1024 * 1024 + 1), 'a.csv')['errors']

def test_xlsx_compatibility():
    from openpyxl import Workbook
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(['origem', '_id', 'salePrice', 'area', 'regionName', 'forSale'])
    sheet.append(['QuintoAndar', 123, 300000, 45, 'Mooca', True])
    stream = io.BytesIO()
    workbook.save(stream)
    result = parse_upload(stream.getvalue(), 'a.xlsx')
    assert not result['errors']
    assert result['records'][0]['external_id'] == '123'

def test_zip_bomb_rejected():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('xl/worksheets/sheet1.xml', 'x' * (21 * 1024 * 1024))
    assert parse_upload(stream.getvalue(), 'a.xlsx')['errors']

@pytest.mark.parametrize('ip', ['127.0.0.1', '10.0.0.1', '169.254.169.254', '::1', 'fc00::1', '::ffff:127.0.0.1', '192.168.1.1', '0.0.0.0'])
def test_ssrf_blocked_after_dns(ip):
    with patch('app.ingestion.socket.getaddrinfo', return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 80))]):
        with pytest.raises(ValueError, match='públicos'):
            _resolve_public('http://feed.example/listings')

def test_mixed_dns_blocked():
    with patch('app.ingestion.socket.getaddrinfo', return_value=[(2, 1, 6, '', ('8.8.8.8', 80)), (2, 1, 6, '', ('127.0.0.1', 80))]):
        with pytest.raises(ValueError):
            _resolve_public('http://feed.example')

def test_feed_retries_and_marks_origin():
    with patch('app.ingestion._download_once', side_effect=[TimeoutError(), (json.dumps([BASE]).encode(), 'application/json')]) as download, patch('app.ingestion.time.sleep'):
        result = fetch_feed('https://example.com/feed')
    assert download.call_count == 2
    assert result['records'][0]['data_origin'] == 'feed'

def test_xml_vrsync():
    xml = b'<ListingDataFeed xmlns="http://www.vivareal.com/schemas/1.0/VRSync"><Listings><Listing><ListingID>abc</ListingID><Details><ListPrice>300000</ListPrice><LivingArea>50</LivingArea><PropertyType>Residential / Apartment</PropertyType></Details></Listing></Listings></ListingDataFeed>'
    result = parse_upload(xml, 'a.xml')
    assert not result['errors']
    assert result['records'][0]['property_type'] == 'apartment'

def test_xml_entities_rejected():
    result = parse_upload(b'<!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><a>&x;</a>', 'a.xml')
    assert result['errors']

def test_download_redirect_rejected():
    from unittest.mock import MagicMock
    from urllib.parse import urlsplit
    from app.ingestion import _download_once
    connection = MagicMock()
    connection.getresponse.return_value.status = 302
    with patch('app.ingestion._resolve_public', return_value=(urlsplit('http://example.com/feed'), '93.184.216.34', 80)), patch('app.ingestion.http.client.HTTPConnection', return_value=connection):
        with pytest.raises(ValueError, match='Redirecionamento'):
            _download_once('http://example.com/feed')
    connection.close.assert_called_once()


def test_streaming_limit_and_pinned_connection():
    from unittest.mock import MagicMock
    from urllib.parse import urlsplit
    from app.ingestion import _download_once
    connection = MagicMock()
    response = connection.getresponse.return_value
    response.status = 200
    response.getheader.side_effect = lambda name, default=None: default
    response.read.return_value = b'x' * 65536
    with patch('app.ingestion.MAX_BYTES', 65536), patch('app.ingestion._resolve_public', return_value=(urlsplit('http://example.com/feed'), '93.184.216.34', 80)), patch('app.ingestion.http.client.HTTPConnection', return_value=connection) as factory:
        with pytest.raises(ValueError, match='10 MB'):
            _download_once('http://example.com/feed')
    factory.assert_called_once_with('93.184.216.34', 80, timeout=12)
    assert connection.request.call_args.kwargs['headers']['Host'] == 'example.com'
    connection.close.assert_called_once()


def test_multiple_vrsync_feeds_have_distinct_source_identity():
    xml = b'<ListingDataFeed><Listings><Listing><ListingID>abc</ListingID><ListPrice>300000</ListPrice><LivingArea>50</LivingArea></Listing></Listings></ListingDataFeed>'
    with patch('app.ingestion._download_once', return_value=(xml, 'application/xml')):
        a = fetch_feed('https://one.example/feed')['records'][0]
        b = fetch_feed('https://two.example/feed')['records'][0]
    assert a['source'] != b['source']
    assert a['provenance']['price']['source'] == a['source']


def test_source_length_rejected_without_silent_identity_collision():
    assert not parse([{**BASE, 'source': 's' * 200}])['errors']
    result = parse([{**BASE, 'source': 's' * 200 + 'a'}, {**BASE, 'source': 's' * 200 + 'b'}])
    assert not result['records'] and len(result['errors']) == 2
    assert all('200' in e['message'] for e in result['errors'])


@pytest.mark.parametrize('field', ['url', 'image_url'])
def test_url_length_exact_limit_and_rejection(field):
    prefix = 'https://example.com/'
    exact = prefix + 'x' * (2048 - len(prefix))
    good = parse([{**BASE, field: exact}])
    assert not good['errors'] and good['records'][0][field] == exact
    bad = parse([{**BASE, field: exact + 'x'}])
    assert not bad['records'] and '2048' in bad['errors'][0]['message']


@pytest.mark.parametrize('changes,expected', [
    ({'type': 'apartment', 'area': 49, 'regionName': 'Mooca'}, 'Apartamento de 49 m² · Mooca'),
    ({'area': 49}, 'Imóvel de 49 m²'),
    ({'property_type': 'house', 'area': 49.5}, 'Casa de 49,5 m²'),
    ({'property_type': 'studio', 'title': 'Título original'}, 'Título original'),
])
def test_missing_titles_derived_only_from_known_facts(changes, expected):
    result = parse([{**BASE, **changes}])
    assert not result['errors']
    assert result['records'][0]['title'] == expected


@pytest.mark.parametrize('alias', ['iptuPlusCondominium', 'complexFee'])
def test_legacy_combined_cost_has_unknown_period_even_if_period_supplied(alias):
    for period in (None, 'monthly'):
        result = parse([{**BASE, alias: 450, 'combined_cost_period': period}])
        assert not result['errors']
        row = result['records'][0]
        assert row['combined_monthly_cost'] == 450
        assert row['combined_cost_period'] == 'unknown'
        assert row['condo_fee'] is None and row['property_tax'] is None


@pytest.mark.parametrize('period,expected', [(None, 'monthly'), ('monthly', 'monthly'), ('unknown', 'unknown')])
def test_canonical_combined_monthly_cost_retains_explicit_period(period, expected):
    result = parse([{**BASE, 'combined_monthly_cost': 450, 'combined_cost_period': period}])
    assert not result['errors']
    assert result['records'][0]['combined_cost_period'] == expected
    assert result['records'][0]['combined_monthly_cost'] == 450
