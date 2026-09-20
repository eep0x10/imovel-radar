"""Canonical display names for the city aliases supported by portal search."""
import re
import unicodedata


def canonical_city(value):
    value = " ".join(str(value or "").split())
    key = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    if re.fullmatch(r"sao paulo(?:\s*[-,]\s*sp)?", key):
        return "São Paulo"
    return value
