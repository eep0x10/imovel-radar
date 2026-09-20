# Contrato de implementação aprovado — v1

Protótipo aprovado pelo usuário em 19/09/2026. Interface mantém estrutura visual em `prototype/`. Implementação em `web/`, API FastAPI em `app/`. SQLite local com transações e migrações versionadas; adaptador de armazenamento posterior pode migrar a PostgreSQL. Esta decisão reduz infraestrutura inicial e permite executar o produto no computador atual. Frontend usa módulos JS nativos para preservar o protótipo aprovado sem etapa de build. Nenhum dado demonstrativo inserido no banco real.

## Fatias

1. Criar conta → importar arquivo com preview → listar dados persistidos exclusivamente do usuário. Prova: testes HTTP de dois usuários + importação repetida idempotente.
2. Observar mudança → guardar histórico → explicar avaliação e comparáveis → comparar imóveis. Prova: tests domínio/outliers/nulls/deduplicação e mudança de preço.
3. Salvar → registrar visita/nota → recarregar → manter estado e notificar mudança. Prova: API/browser e isolamento.
4. Configurar feed → validar preview → executar worker → exibir estado real → repetir diariamente. Prova: fixture HTTP, falha preserva snapshot, lock e execução idempotente. Sem scraping sem permissão.
5. Backup → restaurar em cópia → rodar smoke tests → disponibilizar local. Deploy remoto só com destino/preflight válido.

## JSON comum de anúncio (normalizado)

`id` inteiro interno, `source` string, `external_id` string, `url` https/http pública, `title`, `address`, `neighborhood`, `city`, `property_type` (apartment/house/studio), `price` BRL número >0, `area` m² >0, `bedrooms`, `bathrooms`, `parking`, `floor`, `elevator`, `condo_fee` mensal, `property_tax` valor original, `tax_period` monthly/annual/unknown, `metro_minutes`, `latitude`, `longitude`, `image_url`, `amenities` lista, `condition` good/needs_work/unknown, `sunlight` good/poor/unknown, `ventilation` good/poor/unknown, `documentation` verified/pending/unknown, `status` active/unavailable/unknown, `observed_at` ISO ou null, `first_seen`, `last_seen`, `data_origin` import/manual/feed, `canonical_key` string conservadora. Campos opcionais desconhecidos null. Datas desconhecidas nunca viram data atual de observação. `imported_at` é distinto.

JSON enriquecido na API adiciona `evaluation` = domínio descrito abaixo, `saved` bool, `stage`, `notes`, `visit_at`, `checklist` dict, `price_change` número|null; `/properties/{id}` adiciona `history` [{price,observed_at,recorded_at}], `source_links` [{source,url}], `provenance` {campo:{source,observed_at}} e `alerts`.

## Perfil

GET/PUT `/api/profile` → objeto: `name`, `budget_max` default 330000, `area_min` 35, `area_max` 70, `bedrooms_min` 2, `parking_min` 0, `metro_max` 15, `monthly_max` 580, `cities` [São Paulo], `neighborhoods` [], `require_elevator` false, `weights` {price:40,location:35,quality:25}, `alert_drop_percent` 5, `exclude_unknown_required` false. Defaults editáveis; eliminar filtros vazios conscientemente.

## Domínio (agente domínio)

`app/domain.py` sem banco: `evaluate_property(property:dict, peers:list[dict], profile:dict, now:datetime|None=None)->dict` retorna `{fit_score:number|null,quality_score:number|null,opportunity_percent:number|null,confidence:'insufficient'|'low'|'medium'|'high',comparables_count:int,benchmark_m2:number|null,comparables:list[{id,price,area,price_m2}],eligible:bool,pending_requirements:list[str],reasons:list[str],missing:list[str],quality_factors:list[{label,value,weight}],fit_factors:list[{label,score,weight}],score_version:str}`. Perfil e propriedades acima. Requisito falho → eligible false; desconhecido → pending, e eliminar se profile.exclude_unknown_required. Comparáveis recentes (<90 dias), mesma cidade/bairro/tipo, área +-25%, dormitórios e vagas quando conhecidos; excluir próprio/canonical_key repetido, observação desconhecida. Poucos peers -> sem desconto. Qualidade não depende de preço; peso pessoal afeta fit apenas.

`simulate_budget(payload:dict)->dict` campos input `price,down_payment,annual_rate,months,monthly_costs,acquisition_costs,reserve,model` (price/sac), retorna `principal,monthly_rate,first_payment,last_payment,total_interest,total_paid,initial_cash,first_month_total,schedule` [{month,payment,interest,amortization,balance}]. ValueError para inválidos. Não assumir taxas legais.

## Importação (agente ingestion)

`app/ingestion.py`: `parse_upload(content:bytes, filename:str)->dict {records:list[dict],errors:list[{row,message}],warnings:list[str]}` CSV UTF8/semicolon/comma, JSON lista ou {listings:[]}, XLSX legado. Sem side effect. Preservar IDs fonte+external_id, mapear alias do arquivo original. Nunca transformar campo combinado IPTU+condomínio em dois conhecidos; conservar `combined_monthly_cost` e tax_period unknown. Planilha pode ter bairros em regionName, timestamp desconhecido, forSale heterogêneo. Limites 10MB/5000 linhas, validação finita/URLs sem javascript, unknown null; propriedades sem preço/área rejeitadas. Só concatena; nunca combine_first. `fetch_feed(url:str)->dict` feed JSON/CSV/XML VRSync se viável, autorizado configurado pelo usuário, HTTP público apenas; bloquear SSRF (loopback/private/link-local/resolved IP), redirects revalidados ou desabilitados, timeout, máx10MB, backoff limitado sem credencial hardcoded. Retorno parse padrão. Extração não pode ser marcada completa sem evidência. Sem coletar portais por endpoints internos.

## API (raiz)

Auth usa Bearer token opaco aleatório, guardado sessionStorage no frontend, hash token no DB, expiração 7 dias. Sem cookies/CSRF. `POST /api/auth/register {email,password,name}` e login `{email,password}` → `{token,user:{id,email,name}}`; GET `/api/auth/me` → user; POST logout invalida token. Password >=12. Não expor usuários existentes além de erro de registro.

- GET `/api/properties?q=&sort=fit|price|price_m2|opportunity&saved=false&drops=false&apply_profile=false&page=1&page_size=50` → `{items,total,page,page_size,summary:{total,new,price_drops,saved},last_updated}`. Backend filtra/ordena e nunca mistura usuários.
- GET `/api/properties/{id}` → detalhe enriquecido; PATCH `/api/properties/{id}/tracking` body `{saved?,stage?,notes?,visit_at?,checklist?}` → detalhe; stages `saved,contacted,visit,visited,offer,rejected,bought`.
- POST `/api/properties` body normalizado → registro manual. Pode omitir source/external_id (manual/UUID).
- POST `/api/import/preview` multipart `file` → `{preview_id,records,errors,warnings,total,valid}`; até 20 registros exibidos. Prévia privada persistida por 30min. POST `/api/import/commit {preview_id}` → `{created,updated,unchanged,alerts,errors}`. Preview com errors não pode commit; preview idempotente; frontend oferece baixar template `/api/import/template.csv` autenticado (fetch blob).
- GET `/api/sources` → `{items:[{id,name,kind,status,url,last_attempt,last_success,error,record_count,enabled,authorized}],schedule:{hour,timezone,worker_heartbeat}}`; portais pendentes no catálogo não são fontes ativas.
- POST `/api/sources {name,url,authorized:true}` → fonte feed; PATCH `/api/sources/{id} {enabled?}` (nome imutável para preservar namespace); POST `/api/sources/{id}/refresh` → ingestão ou erro 422. POST `/api/refresh` atualiza fontes habilitadas do usuário, com resultados por fonte. Sem autorização implícita para envios externos.
- GET `/api/alerts` → `{items:[{id,property_id,kind,title,body,created_at,read}],unread}`; PATCH `/api/alerts/{id} {read:true}`.
- POST `/api/budget` body domínio → simulação.
- GET `/api/export` → JSON de dados da conta (sem credenciais/tokens).
- GET `/api/health` → status/version, sem dados privados; GET `/api/status` auth → scheduler health.

Erros FastAPI `{detail:string|array}`. Frontend mostra erro e retry; loading/disabled durante mutations; nunca usa fixtures da demonstração em produção. Sem upload automático da planilha existente a serviço externo. Import local via conta de onboarding precisa fluxo explícito, ou CLI que não expõe credenciais.

## Responsabilidade de arquivos

Raiz: app/main.py, storage.py, security.py, worker.py, tests/test_api.py, configuração/run/backup/docs. Agente domínio: app/domain.py, tests/test_domain.py. Agente ingestão: app/ingestion.py, tests/test_ingestion.py. Agente frontend: web/**, exclusivamente; pode ler prototype/** sem alterar. Contrato muda por coordenação.
