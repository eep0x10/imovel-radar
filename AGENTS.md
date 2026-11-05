# Orientação para qualquer agente

Este repositório contém o **Imóvel Radar**, aplicação local Python/FastAPI + SQLite com frontend JavaScript e worker. As instruções abaixo são autossuficientes: não dependem de skills, memórias ou caminhos do computador original. Leia [README](README.md), [arquitetura](docs/ARCHITECTURE.md) e [handoff](docs/HANDOFF.md) antes de alterar o projeto. Verifique `git status`, branch e remoto; preserve alterações de outras pessoas.

Instale `requirements.lock` em um ambiente virtual novo; execute `python run.py` a partir da raiz. Consulte o handoff para comandos Windows/Linux, configuração e transferência de dados. O código versionado e o backup privado são entregas separadas; clonar o Git não recupera contas, filtros, favoritos, histórico ou segredos.

Antes de concluir mudanças, execute `python -m pytest -q` e `python scripts/privacy_audit.py`; ao publicar, inclua `--history` na auditoria. Para UI, execute `npx --yes prettier@3.6.2 --check "web/**/*.{html,css,js}"` e confira a superfície real em desktop e 390px. Use dados sintéticos nos testes; não publique banco, `.env`, logs, planilhas ou evidências privadas. Mudanças de dados precisam de backup online e restauração validada; nunca copie um SQLite ativo ignorando WAL/SHM. Registre quais verificações foram de fato executadas.

# Escopo do produto

Este sistema é exclusivamente para COMPRA de imóveis, nunca aluguel. Coletores, importações, filtros, comparações e alertas devem respeitar esse escopo. Rejeitar anúncios explicitamente de locação. Um imóvel à venda com inquilino continua sendo uma venda; ocupação é um critério separado.

Interfaces devem atualizar dados e ações sem full refresh, preservando filtros e edições.

## Fluxos integrados

O Radar reúne filtros e comparação dinâmica. Favoritos ficam em Salvos no Radar; não há aba Minha jornada. Mudanças de preço dos últimos 30 dias aparecem no próprio imóvel, sem aba Preço caiu. Notificações são geradas por buscas salvas: registrar baseline na criação, nunca emitir avisos retroativos, deduplicar novas correspondências e isolar por usuário. Alterar o Radar não altera o snapshot dos alertas existentes. Configurações reúne conta, fontes, importações e diagnósticos.

Novas funcionalidades e correções preservam o estilo existente e seguem sem prévias. Prévias visuais só são necessárias quando o usuário pedir explicitamente mudar/recriar a apresentação do frontend.

Pesquisar nas fontes aguarda o salvamento/validação dos filtros e cria job persistente por conta; alterações durante coleta enfileiram o último snapshot. Filtros locais não disparam coleta automaticamente. Alertas coletam com seus próprios snapshots, nunca com o perfil atual da conta. Fontes de coleta ativas: QuintoAndar e Loft; VivaReal e OLX removidos por solicitação do usuário.

## Coleta orientada pelos filtros

Toda coleta deve consultar QuintoAndar e Loft com os filtros da pesquisa solicitada ou com o snapshot do alerta. É proibido fazer dump do catálogo inteiro e só depois aplicar os critérios. Enviar à origem os filtros suportados (preço, área, quartos, vagas e localização), preservar esses parâmetros em todas as páginas e não relaxar a consulta silenciosamente. Critérios sem suporte no portal são refinados apenas no conjunto já limitado pela consulta; documentar essa limitação sem afirmar que todos os filtros foram aplicados na origem.

## Caminhadas e segurança

Calcular rota até o metrô somente por clique explícito no imóvel. Coleta, agenda, polling, abertura da página e imóveis vizinhos não podem disparar cálculo automático. Preservar cache, limites do provedor, estado acessível de carregamento, isolamento por conta e lock por imóvel. Cobertura parcial das estações deve continuar visível; não inventar tempo a pé ou estação mais próxima.

Preservar autenticação e `user_id` em todo acesso a dados pessoais, senhas scrypt, validação/limites de importação e proteção SSRF dos feeds (DNS, redirecionamentos, destinos privados, tempo e tamanho). Chaves ficam no backend e fora do Git. Falhas não apagam resultados anteriores, ausência em coleta não comprova venda e desconhecido não vira dado confirmado. Para UI, preservar Anime.js com limpeza de instâncias e `prefers-reduced-motion`.
