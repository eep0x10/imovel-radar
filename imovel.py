"""Entrada compatível: inicia o Imóvel Radar com API e worker diário.

O coletor legado foi substituído. Dados existentes são importados com prévia
pela interface. Nenhuma credencial é mantida neste arquivo.
"""
from run import main

if __name__ == "__main__":
    raise SystemExit(main())
