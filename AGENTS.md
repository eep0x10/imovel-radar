# Escopo do produto

Este sistema é exclusivamente para COMPRA de imóveis, nunca aluguel. Coletores, importações, filtros, comparações e alertas devem respeitar esse escopo. Rejeitar anúncios explicitamente de locação. Um imóvel à venda com inquilino continua sendo uma venda; ocupação é um critério separado.

Interfaces devem atualizar dados e ações sem full refresh, preservando filtros e edições.

## Fluxos integrados

O Radar reúne filtros e comparação dinâmica. Favoritos ficam em Salvos no Radar; não há aba Minha jornada. Mudanças de preço dos últimos 30 dias aparecem no próprio imóvel, sem aba Preço caiu. Notificações são geradas por buscas salvas: registrar baseline na criação, nunca emitir avisos retroativos, deduplicar novas correspondências e isolar por usuário. Alterar o Radar não altera o snapshot dos alertas existentes. Configurações reúne conta, fontes, importações e diagnósticos.

Novas funcionalidades e correções preservam o estilo existente e seguem sem prévias. Prévias visuais só são necessárias quando o usuário pedir explicitamente mudar/recriar a apresentação do frontend.

Pesquisar nas fontes aguarda o salvamento/validação dos filtros e cria job persistente por conta; alterações durante coleta enfileiram o último snapshot. Filtros locais não disparam coleta automaticamente. Alertas coletam com seus próprios snapshots, nunca com o perfil atual da conta. Fontes de coleta ativas: QuintoAndar e Loft; VivaReal e OLX removidos por solicitação do usuário.

## Coleta orientada pelos filtros

Toda coleta deve consultar QuintoAndar e Loft com os filtros da pesquisa solicitada ou com o snapshot do alerta. É proibido fazer dump do catálogo inteiro e só depois aplicar os critérios. Enviar à origem os filtros suportados (preço, área, quartos, vagas e localização), preservar esses parâmetros em todas as páginas e não relaxar a consulta silenciosamente. Critérios sem suporte no portal são refinados apenas no conjunto já limitado pela consulta; documentar essa limitação sem afirmar que todos os filtros foram aplicados na origem.
