from tests.test_api import account, client, listing


def test_visit_assessment_persists_and_survives_source_refresh(client):
    headers = account(client)
    item = client.post('/api/properties', headers=headers, json=listing()).json()
    pid = item['id']
    result = client.patch(f'/api/properties/{pid}/tracking', headers=headers, json={
        'saved': True, 'notes': 'Checked on visit',
        'assessments': {'condition': 'good', 'sunlight': 'good', 'ventilation': 'good', 'documentation': 'unknown'},
    })
    assert result.status_code == 200
    assert result.json()['evaluation']['quality_coverage'] == 85
    assert result.json()['evaluation']['quality_score'] == 100
    assert result.json()['provenance']['condition']['source'] == 'Sua avaliação'
    updated = client.post('/api/properties', headers=headers, json=listing(price=295000, observed_at='2026-09-19T12:00:00Z'))
    assert updated.status_code == 201
    assert updated.json()['assessments']['condition'] == 'good'
    assert updated.json()['notes'] == 'Checked on visit'
    assert updated.json()['evaluation']['quality_coverage'] == 85
    assert client.patch(f'/api/properties/{pid}/tracking', headers=headers, json={'assessments': {'condition': 'invented'}}).status_code == 422
