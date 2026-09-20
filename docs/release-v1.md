# Entrega funcional v1 — 19/09/2026

Protótipo aprovado explicitamente pelo usuário. Interface real em `web/`, API em `app/`, referência visual preservada em `prototype/`.

## Decisões finais

- SQLite versionado (schema v2) e módulos JavaScript nativos substituem a sugestão inicial de PostgreSQL/React. Instalação local sem build Node, sem serviço adicional de banco e com fronteira de API documentada para evolução.
- O modelo v1.1 de avaliação separa qualidade, aderência e preço. Não há comparativos fabricados quando falta data ou amostra.
- Conectores ativos são importação CSV/JSON/XLSX, feed público autorizado JSON/CSV/XML VRSync e cadastro manual. Catálogo dos seis portais é explicitamente pendente; nenhuma integração real com esses catálogos foi anunciada como funcionando.
- Feed consultado registra observação real no momento da consulta quando não fornece data; importação de arquivo antigo conserva data desconhecida. Atualização sem alteração de conteúdo renova a observação sem duplicar histórico/alertas.
- O namespace fonte+ID é integral, não truncado. Datas são comparadas como instantes UTC. Retornos a preços anteriores produzem eventos novos. A privacidade da planilha original é restrita à primeira conta quando a opção local está habilitada.
- Avaliações da visita pertencem ao usuário, separadas do anúncio da fonte e preservadas em atualizações futuras.

## Evidências

- 96 testes Python passaram: domínio, importação, fetch/SSRF, autenticação, isolamento entre contas, histórico, agenda, leases, backup, avaliações e regressões.
- Prettier 3.6.2 validou parser e formatação dos cinco arquivos frontend. Uma checagem Node isolada não detectou um erro sintático identificado no navegador; erro corrigido e browser revalidado.
- Navegador Chromium automatizado: cadastro → prévia da planilha original → confirmação → 24 anúncios persistidos → favoritos → notas/etapa/avaliação → reload conservando dados; comparador e dossiê testados.
- Seis telas em 1440px e 390px sem overflow horizontal da página. Comparação usa rolagem interna. Inspeção visual de radar desktop/mobile, jornada mobile, dossiê desktop e fontes desktop.
- Base QA separada em `data/qa.sqlite3`; conta e notas de teste não pertencem ao banco de uso real.
- Totais combinados do legado têm periodicidade desconhecida, pois o coletor antigo podia somar IPTU anual e condomínio mensal. O valor original é preservado, não aparece como `/mês` e gera pendência no requisito de custo mensal.
- Backup online da base QA: `integrity_check=ok`, 24 imóveis, 48 observações (24 primeiras importações + 24 títulos normalizados), 1 acompanhamento. Restore em arquivo novo: `integrity_check=ok`, 24 imóveis.
- Preflight de produção recusou deploy: projeto não cadastrado. Sem publicação no VPS, sem exclusão de dados/volumes.

Capturas em `output/qa/` e backups em `data/backups/`, ambos fora do Git. A execução em Docker e o CI remoto devem ser distinguidos dos testes locais; empacotamento não equivale a deploy comprovado.

## Operação e limitações

Aplicação local em 127.0.0.1:8766; cadastro e importação pelo frontend. Rotina diária depende de processo/host ligado e feed válido. Nenhum feed de mercado real foi fornecido nesta sessão. Sem esses acessos, o sistema organiza/importa/avalia, mas ainda não entrega descoberta diária automática dos portais.

Removida a chave Google Maps hardcoded do código atual; rotação no provedor ainda é necessária, pois o segredo permanece no histórico Git. Não houve reescrita do histórico.
