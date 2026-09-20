"""Portal contract fixtures; these unit tests never prove current live access."""
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit
import pytest
from app.portal_collectors import collect_portal,_qa_payload,_loft_url,_request_json


def qa(identifier='1',**changes):
    return {'_id':identifier,'_source':{'salePrice':300000,'area':50,'type':'Apartamento','city':'São Paulo','regionName':'Mooca','forSale':True,'bedrooms':2,'parkingSpaces':1,**changes}}


def qa_page(rows,total=1):
    return {'hits':{'hits':rows,'total':{'value':total,'relation':'eq'}},'relaxed':False,'engine_timed_out':False}


def loft(identifier='1',**changes):
    return {'id':identifier,'price':300000,'area':50,'homeType':'apartment','address':{'city':'São Paulo','neighborhood':'Mooca'},'complexFee':400,'propertyTax':100,'status':'FOR_SALE',**changes}


def loft_page(rows,total=1):
    return {'listings':rows,'pagination':{'total':total,'page':0,'totalPages':1}}


def test_qa_pagination_identity_dates_unknown_and_images():
    responses=[qa_page([qa('1',coverImage='test.jpg')],2),qa_page([qa('2')],2)]
    with patch('app.portal_collectors._request_json',side_effect=responses) as fetch,patch('app.portal_collectors.time.sleep'):
        result=collect_portal('quintoandar',{'max_pages':3,'page_size':1})
    assert not result['errors']
    assert result['coverage']['complete'] is True and result['coverage']['pages']==2
    assert fetch.call_args_list[1].args[1]['filters']['offset']==1
    assert {r['external_id'] for r in result['records']}=={'1','2'}
    for row in result['records']:
        assert row['source']=='QuintoAndar' and row['observed_at']
        assert row['metro_minutes'] is None and row['floor'] is None and row['occupied'] is None
    assert result['records'][0]['image_url'].endswith('/test.jpg')


def test_loft_cost_fields_are_separate_and_tax_period_unknown():
    with patch('app.portal_collectors._request_json',return_value=loft_page([loft(image='banner.jpg')])):
        result=collect_portal('loft',{})
    row=result['records'][0]
    assert row['source']=='Loft' and row['external_id']=='1'
    assert row['condo_fee']==400 and row['property_tax']==100 and row['tax_period']=='unknown'
    assert row['combined_monthly_cost'] is None
    assert row['image_url']=='https://content.loft.com.br/homes/1/banner.jpg'


def test_bounds_and_profile_are_applied_to_requests():
    profile={'budget_min':150000,'budget_max':330000,'area_min':35,'area_max':70,'bedrooms_min':2,'parking_min':1,'search_bounds':{'north':-23.5,'south':-23.6,'east':-46.5,'west':-46.65},'cities':['São Paulo']}
    payload=_qa_payload(profile,2,20)
    assert payload['filters']['cost']['min_value']==150000
    assert payload['filters']['offset']==40
    assert payload['filters']['map']['bounds_west']==-46.65
    query=parse_qs(urlsplit(_loft_url(profile,2,20)).query)
    assert query['priceMax']==['330000'] and query['neLatBoundary']==['-23.5']
    assert query['cities[]']==['São Paulo, SP']


def test_page_limit_is_partial():
    with patch('app.portal_collectors._request_json',return_value=qa_page([qa()],100)):
        result=collect_portal('quintoandar',{'max_pages':1})
    assert not result['coverage']['complete'] and result['coverage']['reason']=='page_limit'


def test_repeated_page_stops_without_duplicate_records():
    with patch('app.portal_collectors._request_json',return_value=qa_page([qa()],100)),patch('app.portal_collectors.time.sleep'):
        result=collect_portal('quintoandar',{'max_pages':5})
    assert len(result['records'])==1 and result['coverage']['pages']==2
    assert result['coverage']['reason']=='repeated_page'


def test_http_failure_does_not_claim_complete():
    with patch('app.portal_collectors._request_json',side_effect=ValueError('HTTP 403')):
        result=collect_portal('loft',{})
    assert result['errors'] and not result['records'] and not result['coverage']['complete']


def test_mid_collection_error_is_explicit():
    with patch('app.portal_collectors._request_json',side_effect=[qa_page([qa()],100),ValueError('HTTP 429')]),patch('app.portal_collectors.time.sleep'):
        result=collect_portal('quintoandar',{})
    assert len(result['records'])==1 and result['errors'] and result['coverage']['reason']=='error'


def test_known_occupied_exclusion_does_not_invent_vacancy():
    with patch('app.portal_collectors._request_json',return_value=qa_page([qa('1',listingTags=['BUY_RENTED']),qa('2')],2)):
        result=collect_portal('quintoandar',{'exclude_occupied':True})
    assert [r['external_id'] for r in result['records']]==['2']
    assert result['records'][0]['occupied'] is None


def test_missing_required_values_report_validation_errors():
    with patch('app.portal_collectors._request_json',return_value=qa_page([qa(area=None)])):
        result=collect_portal('quintoandar',{})
    assert result['errors'] and not result['coverage']['complete']


def test_land_is_not_presented_as_apartment():
    with patch('app.portal_collectors._request_json',return_value=loft_page([loft(homeType='land_lot')])):
        result=collect_portal('loft',{})
    assert not result['records']


def test_empty_page_before_reported_total_is_partial():
    with patch('app.portal_collectors._request_json',return_value=qa_page([],50)):
        result=collect_portal('quintoandar',{})
    assert not result['coverage']['complete']
    assert result['coverage']['reason']=='empty_page_before_total'


def test_unknown_portal_rejected():
    with pytest.raises(ValueError):collect_portal('arbitrary',{})


def test_multiple_regions_merge_stable_identity_and_report_each_coverage():
    regions=[{'name':'A','north':-23.5,'south':-23.6,'east':-46.5,'west':-46.6}, {'name':'B','north':-23.4,'south':-23.6,'east':-46.4,'west':-46.6}]
    with patch('app.portal_collectors._request_json',side_effect=[qa_page([qa('1')]),qa_page([qa('1'),qa('2')],2)]):
        result=collect_portal('quintoandar',{'search_bounds':regions})
    assert len(result['records'])==2
    assert result['coverage']['pages']==2 and result['coverage']['complete']
    assert len(result['coverage']['regions'])==2
    assert result['coverage']['total_reported'] is None


@pytest.mark.parametrize('portal',['quintoandar','loft'])
def test_unsupported_city_is_rejected_without_request(portal):
    with patch('app.portal_collectors._request_json') as fetch:
        with pytest.raises(ValueError,match='São Paulo'): collect_portal(portal,{'cities':['Rio de Janeiro']})
    fetch.assert_not_called()


def test_default_qa_bounds_prevent_country_wide_query():
    with patch('app.portal_collectors._request_json',return_value=qa_page([] ,0)) as fetch:
        collect_portal('quintoandar',{})
    bounds=fetch.call_args.args[1]['filters']['map']
    assert bounds['bounds_west'] < -46 and bounds['bounds_north'] < -23


def test_qa_absolute_cover_url_is_kept():
    with patch('app.portal_collectors._request_json',return_value=qa_page([qa(coverImage='https://example.com/cover.jpg')])):
        result=collect_portal('quintoandar',{})
    assert result['records'][0]['image_url']=='https://example.com/cover.jpg'


def test_neighborhood_filter_is_local_and_exposes_its_coverage_limit():
    rows=[qa('1',regionName='Mooca'),qa('2',regionName='Belenzinho'),qa('3',regionName=None)]
    with patch('app.portal_collectors._request_json',return_value=qa_page(rows,3)):
        result=collect_portal('quintoandar',{'neighborhoods':['moóca']})
    assert {r['external_id'] for r in result['records']}=={'1','3'}
    assert result['coverage']['neighborhood_filter']=='local'
    assert result['coverage']['retained']==2
    assert any('filtro local' in warning for warning in result['warnings'])


def test_transport_uses_single_read_and_remaining_deadline_timeout():
    from unittest.mock import MagicMock
    from urllib.parse import urlsplit
    connection=MagicMock()
    secure_socket=MagicMock()
    response=connection.getresponse.return_value
    response.status=200
    response.getheader.side_effect=lambda name,default=None:default
    response.read1.side_effect=[b'{"listings":[]}',b'']
    with patch('app.portal_collectors._resolve_public',return_value=(urlsplit('https://landscape-api.loft.com.br/listing/v2/search'),'93.184.216.34',443)),patch('app.portal_collectors.http.client.HTTPConnection',return_value=connection),patch('app.portal_collectors.ssl.create_default_context') as tls,patch('app.portal_collectors.time.monotonic',side_effect=[100,130,131]):
        tls.return_value.wrap_socket.return_value=secure_socket
        result=_request_json('https://landscape-api.loft.com.br/listing/v2/search')
    assert result=={'listings':[]}
    assert secure_socket.settimeout.call_args_list[0].args==(5,)
    assert secure_socket.settimeout.call_args_list[1].args==(4,)
    response.read.assert_not_called()
    connection.close.assert_called_once()


def test_transport_stops_at_deadline():
    from unittest.mock import MagicMock
    from urllib.parse import urlsplit
    connection=MagicMock()
    response=connection.getresponse.return_value
    response.status=200
    response.getheader.side_effect=lambda name,default=None:default
    with patch('app.portal_collectors._resolve_public',return_value=(urlsplit('https://landscape-api.loft.com.br/listing/v2/search'),'93.184.216.34',443)),patch('app.portal_collectors.http.client.HTTPConnection',return_value=connection),patch('app.portal_collectors.ssl.create_default_context'),patch('app.portal_collectors.time.monotonic',side_effect=[100,136]):
        with pytest.raises(ValueError,match='Tempo máximo'):_request_json('https://landscape-api.loft.com.br/listing/v2/search')
    response.read1.assert_not_called()
    connection.close.assert_called_once()


def detail_html(info):
    import json
    data={'props':{'pageProps':{'initialState':{'house':{'houseInfo':info}}}}}
    return '<script id="__NEXT_DATA__" type="application/json">'+json.dumps(data)+'</script>'


@pytest.fixture
def detail_db(tmp_path,monkeypatch):
    from app import storage
    monkeypatch.setenv('IMOVEL_DB_PATH',str(tmp_path/'detail.sqlite3'))
    storage.initialize()


def test_public_detail_range_no_exact_floor_and_seven_day_cache(detail_db):
    from app.portal_collectors import enrich_quinto_details
    row={'source':'QuintoAndar','external_id':'123','floor':None,'condo_fee':None,'tax_period':'unknown'}
    html=detail_html({'rangeFloor':{'min':0,'max':3},'condoPrice':400,'condoType':'Normal','iptu':20,'iptuType':'Normal','address':{'lat':-23.55,'lng':-46.63,'street':'Rua pública'},'installations':[{'key':'ELEVADOR','value':'SIM'}]})
    with patch('app.portal_collectors._quinto_detail_html',return_value=html) as fetch:
        first=enrich_quinto_details([row]);second=enrich_quinto_details([row])
    assert fetch.call_count==1
    value=first['records'][0]
    assert value['floor'] is None and value['floor_min_reported']==0 and value['floor_max_reported']==3
    assert value['latitude']==-23.55 and value['elevator'] is True
    assert value['condo_fee'] is None and value['tax_period']=='unknown'
    assert second['records'][0]['detail_observed_at']==value['detail_observed_at']
    assert row['floor'] is None and 'floor_min_reported' not in row


def test_detail_limits_preserve_remaining_records(detail_db):
    from app.portal_collectors import enrich_quinto_details
    rows=[{'source':'QuintoAndar','external_id':str(i),'floor':None} for i in (1,2)]
    with patch('app.portal_collectors._quinto_detail_html',return_value=detail_html({'rangeFloor':{'min':4,'max':7}})) as fetch:
        result=enrich_quinto_details(rows,limit=1)
    assert fetch.call_count==1 and len(result['records'])==2
    assert 'floor_min_reported' not in result['records'][1]
    assert any('parcial' in w for w in result['warnings'])


def test_detail_failure_block_stops_further_requests(detail_db):
    from app.portal_collectors import enrich_quinto_details
    rows=[{'source':'QuintoAndar','external_id':str(i)} for i in (1,2)]
    with patch('app.portal_collectors._quinto_detail_html',side_effect=ValueError('Detalhe QuintoAndar HTTP 403')) as fetch:
        result=enrich_quinto_details(rows)
    assert fetch.call_count==1 and result['records']==rows and result['warnings']


def test_detail_expired_cache_refreshes(detail_db):
    from app import storage
    from app.portal_collectors import enrich_quinto_details
    with storage.transaction() as conn:
        conn.execute('INSERT INTO runtime VALUES(?,?)',('quinto_detail:123',storage.dumps({'observed_at':'2000-01-01T00:00:00+00:00','fields':{'floor_min_reported':0,'floor_max_reported':3}})))
    with patch('app.portal_collectors._quinto_detail_html',return_value=detail_html({'rangeFloor':{'min':4,'max':7}})) as fetch:
        result=enrich_quinto_details([{'source':'QuintoAndar','external_id':'123'}])
    fetch.assert_called_once()
    assert result['records'][0]['floor_min_reported']==4


def test_detail_explicit_financial_period_only():
    from app.portal_collectors import _parse_quinto_detail
    fields=_parse_quinto_detail(detail_html({'iptu':1200,'iptuPeriod':'annual','condoPrice':400,'condoPeriod':'monthly'}))
    assert fields=={'property_tax':1200,'tax_period':'annual','condo_fee':400}


def test_detail_deadline_preserves_input(detail_db):
    from app.portal_collectors import enrich_quinto_details
    rows=[{'source':'QuintoAndar','external_id':'123'}]
    with patch('app.portal_collectors.time.monotonic',side_effect=[0,91]),patch('app.portal_collectors._quinto_detail_html') as fetch:
        result=enrich_quinto_details(rows)
    fetch.assert_not_called()
    assert result['records']==rows and result['warnings']


@pytest.mark.parametrize('url', ['https://evil.example/imovel/123/comprar', 'http://www.quintoandar.com.br/imovel/123/comprar', 'https://www.quintoandar.com.br/imovel/456/comprar', 'https://u:p@www.quintoandar.com.br/imovel/123/comprar', 'https://www.quintoandar.com.br/imovel/123/alugar'])
def test_detail_redirect_target_rejected_before_dns(url):
    from app.portal_collectors import _quinto_detail_html
    with patch('app.portal_collectors._resolve_public') as dns:
        with pytest.raises(ValueError,match='Redirecionamento'):_quinto_detail_html('123',_url=url)
    dns.assert_not_called()


def test_detail_redirect_failure_stops_following_properties(detail_db):
    from app.portal_collectors import enrich_quinto_details
    rows=[{'source':'QuintoAndar','external_id':str(i)} for i in (1,2)]
    with patch('app.portal_collectors._quinto_detail_html',side_effect=ValueError('Redirecionamento de detalhe excedeu limite seguro')) as fetch:
        result=enrich_quinto_details(rows)
    assert fetch.call_count==1 and result['records']==rows and result['warnings']


def test_loft_prefers_public_card_thumbnail_route():
    with patch('app.portal_collectors._request_json',return_value=loft_page([loft(image='banner.jpg',image_thumbnail='banner_thumbnail.jpg')])):
        result=collect_portal('loft',{})
    assert result['records'][0]['image_url']=='https://content.loft.com.br/homes/1/banner_thumbnail.jpg'
