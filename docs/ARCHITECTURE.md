# Arquitetura

Frontend HTML/CSS/JavaScript modular, servido por FastAPI. SQLite com WAL mantém contas, sessões, fontes, propriedades, observações, avaliações, alertas e execuções. Todas as consultas privadas delimitam user_id.

`app/portal_collectors.py` consulta endpoints públicos fixos e normaliza respostas. `app/ingestion.py` valida importações/feeds. `app/services.py` aplica transações, identidade e histórico. `app/domain.py` calcula avaliações puras. `app/worker.py` agenda coletas com leases e cooldown. `app/backup.py` produz snapshots online e valida restauração.

Identidade é origem + ID do anúncio. Feeds agregados usam namespace próprio. Endereço de prédio sem unidade não prova que anúncios representam o mesmo apartamento. Comparáveis são preços anunciados e exigem recência e amostra suficiente.

A sessão usa token opaco, hash no banco e validade de sete dias. A senha usa scrypt. O cliente não recebe segredos externos. Importações têm limite de tamanho, prévia privada e transação integral.
