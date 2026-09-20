<div align="center">
<img src="docs/assets/banner.png" alt="Imóvel Radar architectural brand illustration" width="100%">

# Imóvel Radar

### Your next home, with context.

A local home-buying workspace: collect listings, track asking prices, compare properties and organize visits.

[Português](README.md) · [Quick start](docs/QUICKSTART.md) · [Architecture](docs/ARCHITECTURE.md)
</div>

## Start

Python 3.11+. On Windows run `scripts/run.ps1`; on other platforms create a virtual environment, install `requirements.lock` and run `python run.py`. Open http://127.0.0.1:8766 and create an account (minimum 8-character password).

Set your preferences, enable QuintoAndar, Loft, VivaReal and OLX in Sources, and run the first collection. The worker checks the daily schedule while the application is running. Paginated public search collection reports actual coverage and failures. ZAP and Imovelweb currently block HTTP collection and remain unconnected. JSON/CSV/VRSync feeds and spreadsheet imports are supported.

## Evidence before conclusions

Quality, personal fit and asking-price opportunity are separate scores. Missing values remain unknown. Price comparisons require recent comparable listings and show sample confidence. Asking prices are not completed transactions. Monthly costs never assume an unknown tax period.

Accounts have isolated listings, favorites, visits, notes and assessments. SQLite online snapshots and restore checks support local ownership of data. Credentials belong in ignored local environment files. Personal spreadsheets and databases are not distributed.

## Development

Run `python -m pytest -q` and `python scripts/privacy_audit.py`. See the Portuguese operational and architecture guides for deployment, source limits and backup procedures. The AI-created banner is illustrative branding, not a real property or application screenshot.

Independent project, unaffiliated with listing portals. Email password recovery, MFA and external notifications are not implemented.

## Integrated Radar and saved-search notifications

Filters live directly in Radar and save automatically. Compare listings in a dialog without leaving the results, save favorites in My journey, and create a notification rule from the current search. Existing matches establish a baseline; only new matches produce notifications, without duplicates on repeated imports. Each rule keeps its own criteria snapshot. Account details, sources, imports and diagnostics are grouped in Settings.
