# Coleta e cobertura

QuintoAndar e Loft usam consultas HTTP aos endpoints públicos consumidos por suas buscas. Não há login, cookies de usuário, solução de CAPTCHA ou rotação de proxies. Respostas HTTP403/429 e formatos inesperados são falhas explícitas; preservam os dados anteriores.

Os critérios da conta alimentam a consulta. Campos não disponibilizados pelo portal continuam desconhecidos. Paginação é limitada e a cobertura registra páginas, quantidade reportada, completude e motivo da interrupção. Coleta parcial nunca equivale ao catálogo inteiro.

Uma busca válida sem resultados pode concluir com zero. Falha de transporte ou formato não equivale a zero. Imóveis ausentes não são removidos nem marcados vendidos por inferência.

Datas de coleta são instantes reais. Planilha histórica sem data permanece sem data. Comparativos não devem tratar a data de importação como data de verificação do imóvel.

IPTU e condomínio são campos separados quando disponíveis. O adaptador do QuintoAndar reconhece `iptuPlusCondominium` da busca de venda como soma mensal; no detalhe, `condoPrice` é condomínio e IPTU exige período explícito ou apresentação em 12 parcelas. `complexFee` da Loft é somente condomínio. Importações genéricas com valores combinados sem periodicidade confirmada continuam pendentes. Custos desconhecidos podem aparecer se a opção **Excluir requisitos desconhecidos** estiver desmarcada. Tempos de caminhada só são publicados quando retornados por fonte de rotas; distância em linha reta não equivale a caminhada.

A integração é independente e sujeita a mudanças dos portais. Coleta ativa somente de QuintoAndar e Loft; OLX e VivaReal foram removidos a pedido do usuário. Dados históricos importados são preservados.

## Abrangência atual

Coleta automática validada para São Paulo/SP, até quatro regiões e vinte páginas por execução. Outras cidades são recusadas explicitamente. Filtros de bairros são aplicados localmente ao lote coletado; não ampliam a cobertura da paginação.

Detalhes do QuintoAndar preservam faixas de andar, com cache de sete dias, até cinquenta consultas e noventa segundos por execução. Caminhadas opcionais usam Google Maps com cache de trinta dias e limite padrão de vinte imóveis por coleta. Falhas de chave/quota preservam campos desconhecidos e aparecem nos avisos.

## Fase do imóvel

O Radar usa duas fases: **Pronto** e **Na planta / em construção**. Na ausência de indicação de obra, aplica Pronto por convenção do usuário, sem afirmar que a entrega foi verificada. `off_plan` e `under_construction` pertencem ao mesmo grupo. Expressões claras de planta ou construção no título/descrição indicam obra; “planta ampla” não comprova construção.

## Pesquisa e alertas

Pesquisar nas fontes congela os filtros atuais e inicia coleta em segundo plano. Alertas consultam seus próprios critérios salvos. Veja [fluxo e evidências da revisão](SEARCH-REVIEW.md).


## Caminhada até o metrô

`IMOVEL_METRO_PROVIDER=osm` usa estações operacionais do OpenStreetMap em São Paulo e rotas reais do perfil pedestre FOSSGIS/OSRM. São comparadas três estações geograficamente próximas; vence a menor duração calculada. É uma estimativa de caminhada baseada no mapa, sem usar distância em linha reta como tempo e sem estações favoritas.

O modo gratuito é gradual: limite global de 60 chamadas de rotas por dia (até 20 localizações novas com três candidatos), intervalo superior a um segundo e cache de 30 dias. Anúncios na mesma coordenada compartilham o cálculo. Falhas, ausência de coordenadas e esgotamento da cota ficam visíveis, sem números inventados. O worker retoma a fila dos anúncios existentes em lotes, independentemente de nova coleta. Recoletas preservam rotas válidas apenas se a localização permanecer igual.

Atribuição e política: [OpenStreetMap](https://www.openstreetmap.org/copyright), [FOSSGIS e limites de uso](https://routing.openstreetmap.de/about.html), [corrigir o mapa](https://www.openstreetmap.org/fixthemap). Serviços públicos não possuem garantia de disponibilidade. Google Maps continua opcional com chave, APIs e faturamento habilitados; erros não expõem a chave.
