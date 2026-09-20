# Operação

## Rotina diária e disponibilidade

O worker verifica a agenda a cada minuto, às 7h de America/Sao_Paulo por padrão. Uma fonte que concluiu no dia não é repetida pelo agendamento; falhas têm intervalo mínimo de uma hora. Leases impedem concorrência e são renovados entre fontes. O último sinal do worker aparece no frontend.

**O computador/servidor e o processo precisam estar ligados.** Sem fonte válida, a rotina não coleta novos imóveis. Importações manuais não se atualizam sozinhas; ative um coletor ou feed. Falha, bloqueio ou feed vazio preservam o snapshot anterior; não marcam automaticamente imóveis como vendidos. Uma coleta bem-sucedida não comprova cobertura de todo o mercado.

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
