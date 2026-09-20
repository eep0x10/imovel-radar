# Coleta e cobertura

QuintoAndar e Loft usam consultas HTTP aos endpoints públicos consumidos por suas buscas. Não há login, cookies de usuário, solução de CAPTCHA ou rotação de proxies. Respostas HTTP403/429 e formatos inesperados são falhas explícitas; preservam os dados anteriores.

Os critérios da conta alimentam a consulta. Campos não disponibilizados pelo portal continuam desconhecidos. Paginação é limitada e a cobertura registra páginas, quantidade reportada, completude e motivo da interrupção. Coleta parcial nunca equivale ao catálogo inteiro.

Uma busca válida sem resultados pode concluir com zero. Falha de transporte ou formato não equivale a zero. Imóveis ausentes não são removidos nem marcados vendidos por inferência.

Datas de coleta são instantes reais. Planilha histórica sem data permanece sem data. Comparativos não devem tratar a data de importação como data de verificação do imóvel.

IPTU e condomínio são campos separados quando disponíveis. Valores combinados sem periodicidade confirmada não são aprovados no filtro mensal. Tempos de caminhada só são publicados quando retornados por fonte de rotas; distância em linha reta não equivale a caminhada.

A integração é independente e sujeita a mudanças dos portais. VivaReal e OLX têm coletores de HTML público (JSON-LD e dados SSR). ZAP e Imovelweb bloquearam acesso HTTP na verificação e permanecem sem coletor ativo. Fontes de feed e upload complementam o catálogo.

## Abrangência atual

Coleta automática validada para São Paulo/SP, até quatro regiões e vinte páginas por execução. Outras cidades são recusadas explicitamente. Filtros de bairros são aplicados localmente ao lote coletado; não ampliam a cobertura da paginação.

Detalhes do QuintoAndar preservam faixas de andar, com cache de sete dias, até cinquenta consultas e noventa segundos por execução. Caminhadas opcionais usam Google Maps com cache de trinta dias e limite padrão de vinte imóveis por coleta. Falhas de chave/quota preservam campos desconhecidos e aparecem nos avisos.

## VivaReal e OLX

Os coletores consultam páginas públicas sem cookies, login ou proxies. VivaReal publica anúncios em JSON-LD; OLX publica dados estruturados no HTML renderizado pelo servidor. Anúncios agregados de lançamentos não são tratados como apartamentos individuais. Preços na URL do VivaReal são expressos em reais inteiros, preservando filtros nas páginas seguintes; a comparação local aplica os limites exatos do perfil.

A amostra padrão cobre até três páginas, com teto de vinte. A cobertura permanece parcial. Anúncios sem coordenadas não têm correspondência geográfica garantida com seus limites de mapa; isso aparece nos avisos. Banheiros, vagas e impostos não publicados permanecem desconhecidos. Erros HTTP403/500 ou mudança de estrutura preservam o snapshot anterior e são registrados, sem tentativas de contorno.

### Fase do imóvel

No Radar, use **Fase do imóvel** para selecionar **Na planta**, **Em construção**, **Pronto para morar** ou **Fase não informada**. O filtro combina com a busca, favoritos e paginação. A ausência de informação não significa imóvel pronto.

Importações JSON/CSV podem informar `construction_status` como `off_plan`, `under_construction`, `ready` ou `unknown`. Sem campo explícito, somente expressões claras no título são reconhecidas; “novo”, “lançamento” e “planta ampla” não comprovam a fase. O filtro não amplia automaticamente a cobertura dos coletores nem transforma anúncios agregados de empreendimentos em unidades individuais.
