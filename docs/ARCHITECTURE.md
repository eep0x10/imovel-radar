# Arquitetura

Frontend HTML/CSS/JavaScript modular, servido por FastAPI. SQLite com WAL mantém contas, sessões, fontes, propriedades, observações, avaliações, alertas e execuções. Todas as consultas privadas delimitam user_id.

`app/portal_collectors.py` consulta endpoints públicos fixos e normaliza respostas. `app/ingestion.py` valida importações/feeds. `app/services.py` aplica transações, identidade e histórico. `app/domain.py` calcula avaliações puras. `app/worker.py` agenda coletas com leases e cooldown. `app/backup.py` produz snapshots online e valida restauração.

Identidade é origem + ID do anúncio. Feeds agregados usam namespace próprio. Endereço de prédio sem unidade não prova que anúncios representam o mesmo apartamento. Comparáveis são preços anunciados e exigem recência e amostra suficiente.

A sessão usa token opaco, hash no banco e validade de sete dias. A senha usa scrypt. O cliente não recebe segredos externos. Importações têm limite de tamanho, prévia privada e transação integral.

## Mapa de responsabilidades

| Camada | Arquivos | Contrato |
| --- | --- | --- |
| HTTP e autenticação | `app/main.py`, `app/security.py`, `app/schemas.py` | Validação de entrada e delimitação da conta |
| Coleta e importação | `app/portal_collectors.py`, `app/grupo_collectors.py`, `app/ingestion.py` | Normalização de anúncios de compra |
| Fases | `app/construction.py` | Planta e obra agrupadas; pronto como padrão |
| Histórico e preço | `app/services.py` | Observações, transações e mudança recente de 30 dias |
| Alertas | `app/saved_searches.py` | Critérios congelados, baseline e deduplicação |
| Persistência | `app/storage.py` | SQLite, migrações e carregamento normalizado |
| Interface | `web/app.js`, `web/ui.js`, `web/motion.js` | Estado dinâmico, cards e Anime.js com movimento reduzido |

O catálogo é carregado sob a regra atual de fase, inclusive para registros antigos. Mudanças de apresentação não reescrevem observações históricas. Busca salva mantém seu próprio snapshot de critérios; mudar o Radar não altera automaticamente esse snapshot.
