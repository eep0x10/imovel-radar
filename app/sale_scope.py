"""This application supports buying homes only."""
import re
import unicodedata
from urllib.parse import urlsplit


def rental_listing(record):
    def plain(value):
        return ''.join(c for c in unicodedata.normalize('NFKD', str(value or '').lower()) if not unicodedata.combining(c))
    for key in ('transaction_type', 'business_context', 'business_type', 'purpose', 'operation', 'finalidade'):
        if plain(record.get(key)) in ('rent', 'rental', 'lease', 'aluguel', 'locacao', 'alugar'):
            return True
    path = plain(urlsplit(str(record.get('url') or '')).path)
    if re.search(r'/(alugar|aluguel|alugueis|locacao|rent)(?:/|-|$)', path):
        return True
    title = plain(record.get('title'))
    return bool(re.search(r'\b(para alugar|para locacao|para aluguel|aluga-se)\b', title))
