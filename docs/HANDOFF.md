# Continuar o desenvolvimento pelo GitHub

O repositório público é [eep0x10/imovel-radar](https://github.com/eep0x10/imovel-radar). O nome antigo da pasta pode ser `imovel-search-SP`; o nome do produto é Imóvel Radar. Escolha uma única cópia de trabalho e confirme `git remote -v`, `git status` e `git rev-parse HEAD`. O diretório original não é requisito de instalação.

O Git contém aplicação, frontend, testes, dependências fixadas, documentação e instruções de agentes. **Os dados pessoais não acompanham o clone:** contas, sessões, perfis, imóveis, observações, favoritos, visitas, buscas salvas, notificações e fontes ficam no SQLite. `.env`, planilhas de origem e backups também são privados. O clone cria uma instalação nova. Para continuar o desenvolvimento basta clonar o GitHub, instalar as dependências e configurar .env a partir de .env.example. Nenhum pacote ou arquivo do computador anterior é necessário.

## Instalação limpa

Requisitos: Git, Python 3.11+ e acesso à internet para instalar dependências. A CI usa Python 3.13. Node.js/npm só são necessários para a verificação de formatação; a interface já está no repositório e não exige build. Confira [início rápido](QUICKSTART.md), [operação](OPERATIONS.md) e [privacidade](PRIVACY.md).

Windows/PowerShell, a partir da pasta escolhida para projetos:

```powershell
git clone https://github.com/eep0x10/imovel-radar.git
Set-Location imovel-radar
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.lock
Copy-Item .env.example .env
./.venv/Scripts/python.exe run.py
```

Linux/macOS:

```sh
git clone https://github.com/eep0x10/imovel-radar.git
cd imovel-radar
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
cp .env.example .env
.venv/bin/python run.py
```

Abra `http://127.0.0.1:8766`; `run.py` inicia API e worker, carrega `.env` e encerra ambos com Ctrl+C. `scripts/run.ps1` também inicia a aplicação, mas instala dependências apenas quando cria `.venv`: depois de atualizar o código, rode a instalação acima novamente. Não transporte `.venv` entre máquinas.

Configure `.env` localmente: host/porta, fuso/horário do worker e, se necessário, `IMOVEL_DB_PATH` absoluto. O padrão é `data/radar.sqlite3`. A cópia de `.env.example` seleciona `IMOVEL_METRO_PROVIDER=osm`, com cálculo de caminhada sob demanda e limites; Google é opcional e exige chave/faturamento próprios. Sem `.env`, não presuma o mesmo provedor do computador anterior. Chaves nunca vão para Git ou frontend. Não exponha a aplicação publicamente sem HTTPS, operação e backups adequados.

## Validação e continuação por outra IA

```powershell
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe scripts/privacy_audit.py --history
npx --yes prettier@3.6.2 --check "web/**/*.{html,css,js}"
```

Os testes usam fixtures; passar a suite não comprova acesso atual aos portais ou transferência do banco privado. Confira também login, Radar, Salvos, Configurações e API `/api/docs`. A saúde do worker aparece em Configurações; ele precisa estar ativo para processar pesquisas pendentes. Coletas externas só devem ser disparadas dentro da autorização das fontes. Uma coleta parcial não comprova cobertura total.

Entregue à próxima IA o commit/branch, objetivo e próximas ações, erros reproduzíveis e verificações executadas, sem dados pessoais ou credenciais. Ela deve começar pelo [AGENTS.md](../AGENTS.md); as regras de compra exclusiva, interface dinâmica, filtros enviados à origem, snapshots independentes de alertas e cálculo de metrô apenas por clique permanecem obrigatórias. [SEARCH-REVIEW.md](SEARCH-REVIEW.md) registra revisões e evidências históricas; confirme o estado atual antes de reapresentá-las como testes desta instalação.

## Para a próxima IA

Leia AGENTS.md, README.md e docs/ARCHITECTURE.md. Confira branch, remoto e alterações locais; instale requirements.lock no ambiente virtual, execute os testes e continue a tarefa solicitada seguindo as regras do projeto. Use dados sintéticos.
