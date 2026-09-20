"""Two purchase phases; ready is a user-defined default, not source confirmation."""
import re
import unicodedata


def normalize_phase(value):
    return 'under_construction' if value in ('off_plan', 'under_construction') else 'ready'


def construction_status(record):
    explicit = record.get('construction_status')
    if explicit in ('off_plan', 'under_construction'):
        return 'under_construction'
    if explicit == 'ready':
        return 'ready'
    text = ' '.join(str(record.get(key) or '') for key in ('title', 'description'))
    text = ''.join(c for c in unicodedata.normalize('NFKD', text.lower()) if not unicodedata.combining(c))
    text = re.sub(r'\b(?:nao (?:esta |e )?|sem )(?:na planta|em construcao|em obras)\b', '', text)
    if re.search(r'\b(?:na planta|em construcao|em obras|obra em andamento)\b', text):
        return 'under_construction'
    return 'ready'
