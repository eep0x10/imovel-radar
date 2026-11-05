# Transferência para outro computador ou agente

O repositório público é [eep0x10/imovel-radar](https://github.com/eep0x10/imovel-radar). O nome antigo da pasta pode ser `imovel-search-SP`; o nome do produto é Imóvel Radar. Escolha uma única cópia de trabalho e confirme `git remote -v`, `git status` e `git rev-parse HEAD`. O diretório original não é requisito de instalação.

O Git contém aplicação, frontend, testes, dependências fixadas, documentação e instruções de agentes. **Os dados pessoais não acompanham o clone:** contas, sessões, perfis, imóveis, observações, favoritos, visitas, buscas salvas, notificações e fontes ficam no SQLite. `.env`, planilhas de origem e backups também são privados. O clone vazio cria uma instalação nova; para continuar a instalação existente, transfira o snapshot privado verificado.

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

## Preservar a instalação existente

1. Na origem, confirme qual banco o processo usa. Para manter toda a atividade até o corte, encerre API e worker e impeça novos escritores durante o snapshot final. A API online de backup também funciona com o banco ativo, mas alterações posteriores ao snapshot não são transferidas. Não copie diretamente banco ativo, WAL ou SHM.
2. Na raiz do projeto, crie o snapshot e confira a saída `integrity_check: "ok"`, caminho, SHA-256 e contagens. O comando abaixo carrega `.env` explicitamente: o módulo de backup isolado não faz esse carregamento. Variáveis já exportadas no terminal têm precedência sobre `.env`; confirme que `IMOVEL_DB_PATH` aponta para a origem certa.

```powershell
./.venv/Scripts/python.exe -c "from dotenv import load_dotenv; load_dotenv('.env'); from app.backup import main; main()"
```

3. Transfira por meio privado o `.sqlite3` gerado e seu `.manifest.json`. Preserve também planilhas/arquivos pessoais necessários e configurações locais indispensáveis; recrie segredos no destino ou transporte-os separadamente por meio protegido. Não os anexe a issue, release, commit ou prompt. Guarde cópia de rollback na origem.
4. No destino, instale o código antes de iniciar a aplicação. Coloque o snapshot e manifesto em `data/backups/` ou outro diretório privado. Substitua `SEU-SNAPSHOT` nos comandos seguintes pelo mesmo nome de arquivo real. Compare SHA-256 antes de restaurar:

```powershell
$snapshotPath = 'data/backups/SEU-SNAPSHOT.sqlite3'
$manifestPath = 'data/backups/SEU-SNAPSHOT.manifest.json'
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
$receivedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $snapshotPath).Hash
if ($receivedHash -ne $manifest.sha256) { throw 'Hash do snapshot divergente' }
./.venv/Scripts/python.exe -m app.backup --restore-copy $snapshotPath --out data/restored.sqlite3
```

O restore exige destino novo e valida esquema, integridade e referências. Não execute se `data/restored.sqlite3` já existe; escolha outro nome e preserve o arquivo anterior. Compare a contagem `properties` retornada com `counts.properties` do manifesto. O manifesto serve à conferência de transferência, não é uma assinatura de autenticidade; use uma origem confiável.

5. Com o destino ainda parado, configure em `.env` `IMOVEL_DB_PATH` com o caminho absoluto da cópia restaurada (exemplo: `C:/Projetos/imovel-radar/data/restored.sqlite3`). Remova/corrija qualquer variável de ambiente anterior que sobreponha essa opção. Inicie `run.py`, entre com a conta existente e confira filtros, favoritos, notas/visitas, histórico, fontes e buscas salvas. Não crie uma nova conta para substituir a conta restaurada. O banco pode conter sessões; proteja o pacote inteiro como dado privado.
6. Compare o commit de origem/destino e confira os testes abaixo. Somente considere o corte concluído depois da conferência funcional e de dados. Mantenha a origem parada para evitar divergência. Para rollback, pare o destino e volte a usar a origem preservada; gravações novas no destino exigem reconciliação antes de voltar. Nunca sobrescreva o banco anterior para simplificar o rollback.

Em Linux/macOS, use `.venv/bin/python` nos comandos Python. A restauração é a mesma. SHA-256 pode ser conferido com `sha256sum` (Linux) ou `shasum -a 256` (macOS), comparando com `sha256` no manifesto.

## Validação e continuação por outra IA

```powershell
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe scripts/privacy_audit.py --history
npx --yes prettier@3.6.2 --check "web/**/*.{html,css,js}"
```

Os testes usam fixtures; passar a suite não comprova acesso atual aos portais ou transferência do banco privado. Confira também login, Radar, Salvos, Configurações e API `/api/docs`. A saúde do worker aparece em Configurações; ele precisa estar ativo para processar pesquisas pendentes. Coletas externas só devem ser disparadas dentro da autorização das fontes. Uma coleta parcial não comprova cobertura total.

Entregue à próxima IA o commit/branch, objetivo e próximas ações, erros reproduzíveis e verificações executadas, sem dados pessoais ou credenciais. Ela deve começar pelo [AGENTS.md](../AGENTS.md); as regras de compra exclusiva, interface dinâmica, filtros enviados à origem, snapshots independentes de alertas e cálculo de metrô apenas por clique permanecem obrigatórias. [SEARCH-REVIEW.md](SEARCH-REVIEW.md) registra revisões e evidências históricas; confirme o estado atual antes de reapresentá-las como testes desta instalação.
