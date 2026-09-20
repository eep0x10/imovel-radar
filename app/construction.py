"""Conservative construction-stage classification; missing evidence stays unknown."""
import re
import unicodedata


def construction_status(record):
    explicit = record.get('construction_status')
    if explicit in ('off_plan', 'under_construction', 'ready'):
        return explicit
    text = unicodedata.normalize('NFKD', str(record.get('title') or '').lower())
    text = ''.join(c for c in text if not unicodedata.combining(c))
    # Do not interpret negated promotional phrases as evidence.
    if re.search(r'\b(nao|sem)\b', text):
        return 'unknown'
    if re.search(r'\bna planta\b', text):
        return 'off_plan'
    if re.search(r'\bem (construcao|obras)\b', text):
        return 'under_construction'
    if re.search(r'\bpronto para morar\b', text):
        return 'ready'
    return 'unknown'
