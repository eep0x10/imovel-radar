# Imóvel Radar

Aplicação local para organizar a compra da casa própria: anúncios privados por conta, filtros, avaliação explicável, histórico de preços, comparação, visitas, notas, orçamento e atualização diária de feeds autorizados.

**Estado real:** aplicação funcional com SQLite e interface web. QuintoAndar, Loft, ZAP, VivaReal, OLX e Imovelweb aparecem no catálogo como acesso pendente; seus catálogos não estão conectados. O coletor antigo dependia de endpoints internos. Não confundir um portal listado com integração ativa. Detalhes em [viabilidade das fontes](docs/source-feasibility.md).

## Executar no Windows

```powershell
./scripts/run.ps1
```

Abra **http://127.0.0.1:8766** e crie sua conta. O comando prepara o ambiente se necessário e inicia API + worker. Requer Python 3.11+ (validado com 3.14). O endereço padrão aceita somente conexões locais.

Em Linux/macOS:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python run.py
```

Copie `.env.example` para `.env` para personalizar porta, banco, fuso e horário da coleta. Sem credenciais externas obrigatórias.

## Primeiro uso

1. Crie a conta e ajuste orçamento, área, vagas, metrô e prioridades em **Minha busca**.
2. Em **Fontes e atualização**, envie sua planilha/CSV/JSON e examine a prévia. Apenas a confirmação grava os registros.
3. Para migrar a planilha original deste repositório, habilite `IMOVEL_ENABLE_LEGACY_IMPORT=1` em instalação local. O botão de prévia é exclusivo da primeira conta. Nunca habilite essa conveniência em uma instalação compartilhada sem definir quem é o proprietário.
4. Explore o radar, compare até quatro imóveis e salve os relevantes. Na jornada, registre visita, notas, checklist e sua avaliação de conservação, iluminação, ventilação e documentação.
5. Cadastre a URL de um feed JSON/CSV/XML autorizado, confirme a autorização e execute a primeira atualização. A interface informa sucesso/falha e última atualização real.

O arquivo original `resultados_quintoandar.xlsx` não é sobrescrito. Sua data de coleta é desconhecida: anúncios importados não são apresentados como recém-verificados. As 24 linhas originais passaram na validação de formato; isso não comprova disponibilidade atual.

## O que funciona

- Contas separadas, senhas scrypt com salt, sessões opacas de sete dias, logout revogável e limitação de tentativas de login.
- Importação transacional, prévia privada com expiração, validação por linha e idempotência. Campos desconhecidos permanecem desconhecidos.
- Identidades por origem + ID; feeds têm namespace estável. Endereço de prédio sem identificação de unidade não funde imóveis automaticamente.
- Histórico de transições, inclusive quando o preço volta ao valor anterior. Atualizações antigas não substituem observações mais recentes.
- Ranking v1.1: qualidade observada, aderência pessoal e oportunidade separadas. Qualidade exige cobertura mínima de 70%; oportunidade exige anúncio atual/ativo e pelo menos três comparáveis únicos e recentes. Amostras pequenas ficam com confiança baixa. Critérios e imóveis comparáveis são inspecionáveis.
- Despesas combinadas do legado preservadas sem inventar a divisão condomínio/IPTU nem sua periodicidade. Enquanto o período não for confirmado, o total não aprova o filtro de custo mensal. Simulação SAC e Price com taxa efetiva anual, amortização mensal, custos iniciais e reserva.
- Favoritos, etapas, visitas, checklist e notas persistidos. Avaliações do usuário não são apagadas por atualização do feed.
- Alertas dentro da aplicação para novos imóveis elegíveis e queda de preço acima do limiar pessoal. Nenhuma mensagem externa é enviada.
- Exportação JSON da conta sem hash de senha ou token, backup online e restauração em cópia nova.

## Rotina diária e disponibilidade

O worker verifica a agenda a cada minuto, às 7h de America/Sao_Paulo por padrão. Uma fonte que concluiu no dia não é repetida pelo agendamento; falhas têm intervalo mínimo de uma hora. Leases impedem concorrência e são renovados entre fontes. O último sinal do worker aparece no frontend.

**O computador/servidor e o processo precisam estar ligados.** Sem fonte válida, a rotina não coleta novos imóveis. Sem API/contrato dos portais, importações manuais não se atualizam sozinhas. Falha, bloqueio ou feed vazio preservam o snapshot anterior; não marcam automaticamente imóveis como vendidos. Uma coleta bem-sucedida não comprova cobertura de todo o mercado.

Para um ciclo avulso:

```powershell
./.venv/Scripts/python.exe -m app.worker --once --force
```

`--force` ignora horário/cooldown, mas não a idempotência diária. O botão de atualização da fonte permite uma verificação manual adicional.

## Dados aceitos

CSV UTF-8 com vírgula ou ponto e vírgula, JSON em lista ou `{ "listings": [...] }`, XLSX (incluindo cabeçalhos legados) e XML VRSync para feeds. Limites: 10 MB, 5.000 registros por arquivo e limite de descompressão XLSX. Um erro impede o commit de todo o lote.

Campos mínimos: `source`, `external_id` (ou URL), `price`, `area`. Recomendados: `title`, `url`, `city`, `neighborhood`, `property_type`, `bedrooms`, `parking`, `condo_fee`, `property_tax`, `tax_period`, `observed_at`, `status`. A interface fornece modelo CSV. Datas ISO; IPTU com `monthly`, `annual` ou `unknown`.

Feeds bloqueiam destinos privados/loopback/link-local e redirecionamentos. DNS é validado e a conexão usa o IP validado com TLS/SNI preservados. Timeouts e tamanho limitados. Não coloque segredos na URL; endpoints que exigem autenticação específica precisam de um conector apropriado.

## Backup e restauração

```powershell
./.venv/Scripts/python.exe -m app.backup
./.venv/Scripts/python.exe -m app.backup --restore-copy data/backups/SEU-SNAPSHOT.sqlite3 --out data/restore-check.sqlite3
```

O backup usa a API online SQLite, inclui dados confirmados no WAL e verifica `integrity_check=ok`. Manifesto contém hash SHA-256 e contagens. A restauração recusa sobrescrever qualquer destino existente. Para trocar o banco ativo, pare a aplicação, preserve o anterior e configure `IMOVEL_DB_PATH` para a cópia restaurada. Backups contêm dados privados; mantenha-os fora do Git e teste-os periodicamente.

## Testes e implantação

```powershell
./.venv/Scripts/python.exe -m pytest
```

Testes cobrem isolamento entre contas, auth, importação, regressões de identidade/data/histórico, segurança do fetch, comparáveis, SAC/Price, agenda, leases e backup/restauração. Interface validada separadamente em 1440px e 390px. Evidências locais em `output/qa/`, ignoradas no Git.

`compose.yaml` fornece empacotamento para instalação própria com volume persistente. Não houve implantação remota nesta entrega: este repositório não tem destino de produção cadastrado. Para exposição pública, configurar HTTPS/reverse proxy, backups externos e operar a atualização. A API está documentada em `/api/docs`.

## Limitações conhecidas

- Fontes de portal ainda exigem rota de acesso autorizada. Fotos só aparecem quando fornecidas por fonte/importação; não há fotos fictícias no produto.
- Não há mapa geográfico, geocodificação automática, camadas GeoSampa/FipeZAP/ITBI conectadas ou envio externo de alertas nesta versão.
- Contas têm login por senha; recuperação de senha por e-mail e autenticação multifator não estão implementadas. Não habilite acesso público antes de completar a operação correspondente.
- SQLite atende a instalação local; grande volume de usuários requer migração e benchmark de PostgreSQL. Não há edição destrutiva em lote ou exclusão automática.
- O ranking é apoio à investigação, não avaliação técnica do imóvel, preço de transação ou garantia de valorização. Documentação/condição física exigem conferência.
- A chave Google Maps embutida no coletor antigo foi removida do código atual. **Ela permanece no histórico do Git e precisa ser revogada/rotacionada no Google Cloud pelo titular.** O histórico não foi reescrito.

O protótipo aprovado permanece em `prototype/` como referência, separado da aplicação real em `web/`.
