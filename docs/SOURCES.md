# Coleta e cobertura

QuintoAndar e Loft usam consultas HTTP aos endpoints públicos consumidos por suas buscas. Não há login, cookies de usuário, solução de CAPTCHA ou rotação de proxies. Respostas HTTP403/429 e formatos inesperados são falhas explícitas; preservam os dados anteriores.

Os critérios da conta alimentam a consulta. Campos não disponibilizados pelo portal continuam desconhecidos. Paginação é limitada e a cobertura registra páginas, quantidade reportada, completude e motivo da interrupção. Coleta parcial nunca equivale ao catálogo inteiro.

Uma busca válida sem resultados pode concluir com zero. Falha de transporte ou formato não equivale a zero. Imóveis ausentes não são removidos nem marcados vendidos por inferência.

Datas de coleta são instantes reais. Planilha histórica sem data permanece sem data. Comparativos não devem tratar a data de importação como data de verificação do imóvel.

IPTU e condomínio são campos separados quando disponíveis. Valores combinados sem periodicidade confirmada não são aprovados no filtro mensal. Tempos de caminhada só são publicados quando retornados por fonte de rotas; distância em linha reta não equivale a caminhada.

A integração é independente e sujeita a mudanças dos portais. ZAP, VivaReal, OLX e Imovelweb permanecem sem coletor. Fontes de feed e upload complementam o catálogo.

## Abrangência atual

Coleta automática validada para São Paulo/SP, até quatro regiões e vinte páginas por execução. Outras cidades são recusadas explicitamente. Filtros de bairros são aplicados localmente ao lote coletado; não ampliam a cobertura da paginação.

Detalhes do QuintoAndar preservam faixas de andar, com cache de sete dias, até cinquenta consultas e noventa segundos por execução. Caminhadas opcionais usam Google Maps com cache de trinta dias e limite padrão de vinte imóveis por coleta. Falhas de chave/quota preservam campos desconhecidos e aparecem nos avisos.
