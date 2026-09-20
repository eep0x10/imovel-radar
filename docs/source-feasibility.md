# Viabilidade das fontes e enriquecimento

Pesquisa verificada em **19/09/2026**. Documento de engenharia: distingue recursos documentados de integrações ainda não validadas. Nenhum conector foi executado contra os portais nesta pesquisa.

## Estado encontrado

O projeto original contém `imovel.py` e uma planilha de resultados. Inspeção estática identificou funções para QuintoAndar e Loft, com endpoints `quintoandar.com.br/api/yellow-pages/v2/search` e `landscape-api.loft.com.br/listing/v2/search`. São dependências internas sem contrato público de disponibilidade encontrado nesta pesquisa. Existência de um endpoint não comprova autorização, cobertura, estabilidade ou funcionamento atual. O script não foi executado; nenhum segredo é reproduzido aqui.

## Matriz de aquisição

| Fonte | Evidência primária e limite | Caminho implementável | Estado real |
| --- | --- | --- | --- |
| QuintoAndar | [Termos oficiais](https://publicfiles.quintoandar.com.br/termos-condicoes.pdf) exigem autorização escrita para extração automatizada e permissão para reutilização de conteúdo, incluindo fotos. | Solicitar acesso/licença de dados; enquanto isso, usuário registra link e seus próprios dados, sem coleta automática do portal. | Conector legado não validado; acesso autorizado pendente. |
| Loft | [Termos oficiais](https://loft.com.br/institucional/termos-e-condicoes-de-uso) restringem scraping e reutilização sem consentimento expresso; parcerias dependem de aprovação e condições específicas. | Parceria e feed licenciado; cadastro de links com dados fornecidos pelo usuário. | API interna não validada; não presumir API pública. |
| ZAP | [Integração oficial do Grupo OLX](https://developers.grupozap.com/feeds/integration.html) descreve envio de XML por anunciantes para publicar/atualizar ofertas. | Consumir feed próprio de imobiliária com permissão para republicação/análise ou negociar licença. | A documentação não oferece leitura irrestrita do catálogo. |
| VivaReal | [Mesmo canal oficial](https://developers.grupozap.com/feeds/integration.html); publicação depende do plano contratado. | Mesmo adaptador de feed autorizado, preservando identificador/origem e evitando duplicatas com ZAP. | Nenhum conector de catálogo público confirmado. |
| OLX | [Portal oficial de integração](https://developers.grupozap.com/) cobre integrações de anúncios e leads. | Feed de parceiro ou acordo de dados; importação autorizada. | Integração de anunciante não equivale à autorização de agregação. |
| Imovelweb | [Ajuda oficial de integração](https://help.imovelweb.com.br/s/article/Como-habilitar-uma-integra%C3%A7%C3%A3o-de-an%C3%BAncios) existe, mas retornou tela de erro de carregamento nesta consulta. | Confirmar especificação e direitos diretamente; adaptar feed de imobiliária autorizado. | Formato/contrato e API de leitura ainda não verificados. |
| Imobiliárias locais/CRM | Feed fornecido diretamente pelo titular pode oferecer cobertura adicional sem depender da interface dos portais. | Importador CSV/JSON e, depois, XML VRSync mediante amostra e autorização. | Viável tecnicamente; só marcar conectado após importação real validada. |

A documentação Grupo OLX informa processamento dos feeds de publicação a cada 12 horas. Isso é a cadência do portal para anunciantes, não um SLA de atualização deste aplicativo. Ausência de API pública localizada não prova que nenhuma parceria exista.

## Dados de contexto para São Paulo

- **GeoSampa:** [mapa e downloads oficiais](https://novogeosampa.prefeitura.sp.gov.br/) e [catálogo de metadados](https://metadados.geosampa.prefeitura.sp.gov.br/geonetwork/srv/search?type=dataset). Candidato a limites administrativos, equipamentos, mobilidade e camadas territoriais. Escolher camada por metadados, data, licença e precisão; validar sistema de coordenadas. Não inferir risco de um endereço a partir de uma média do distrito. [Página de download](https://download.geosampa.prefeitura.sp.gov.br/PaginasPublicas/_SBC.aspx) informa diferenças de cadência entre visualização e arquivos da camada LOTES; outras camadas podem ter outra periodicidade. Não contornar desafios de acesso.
- **FipeZAP:** [página oficial e séries Excel](https://www.fipe.org.br/pt-br/indices/fipezap/). Usa amostras de preços anunciados em portais Grupo OLX. Serve de contexto agregado e tendência mensal, não de avaliação exata de uma unidade nem de preço efetivamente negociado. Manter período de referência e granularidade visíveis.
- **ITBI de São Paulo:** [página oficial de transações com recolhimento](https://prefeitura.sp.gov.br/web/fazenda/w/acesso_a_informacao/31501). A extração desta pesquisa recuperou o título, mas não os arquivos do conjunto. Ingestão ainda depende de localizar e validar exportação, dicionário e cobertura. Não anunciar histórico transacional implementado. Distinguir valor declarado da transação, base tributária e valor venal; não misturar campos em um preço médio.
- **Custos de aquisição:** [serviços oficiais ITBI](https://prefeitura.sp.gov.br/web/fazenda/servicos/itbi) para referência e acesso ao cálculo. Simulador deve aceitar parâmetros informados e datados, sem fixar regra tributária universal. Condomínio, IPTU, reforma e financiamento devem ser campos separados, com periodicidade explícita e valores desconhecidos preservados.

## Plano incremental

1. Importar a planilha existente com prévia, relatório de erros, mapeamento de colunas e proveniência. Separar demonstração de dados reais; preservar data original desconhecida como desconhecida.
2. Estabelecer cadastro manual e CSV/JSON como contrato comum: fonte, ID externo, URL, preço, área útil, dormitórios, vagas, endereço/precisão, condomínio mensal, IPTU/período, primeira e última observação, status e direitos de mídia. Não inventar dado ausente.
3. Adicionar feeds autorizados de imobiliárias. Guardar origem e identificação de cada anúncio; só unificar imóveis com evidência suficiente. Similaridade fraca gera sugestão, não fusão destrutiva.
4. Agendar atualização diária por fonte configurada, com timeout, limites, backoff, idempotência e execução auditável. Falha ou resposta vazia não deve remover imóveis nem marcar todo o estoque vendido. Diferenciar execução concluída, parcial, bloqueada e falha, mostrando última coleta bem-sucedida.
5. Integrar séries FipeZAP e camadas GeoSampa após validação de licença/metadados. ITBI fica pendente de validação de amostra. Enriquecimentos não devem impedir ingestão de anúncios.
6. Habilitar conectores QuintoAndar, Loft e outros portais somente com rota de aquisição comprovada. Uma caixa de configuração não é uma integração ativa; a interface deve mostrar claramente pendência e cobertura.

## Comparativos e qualidade de decisão

O benchmark inicial deve usar imóveis únicos comparáveis, excluindo a própria unidade, segmentados por cidade/bairro, tipo, área e dormitórios. Exibir mediana por m², intervalo interquartil, tamanho da amostra, janela temporal e filtros; amostra insuficiente significa confiança baixa, não oportunidade extraordinária. Comparar preços anunciados com anunciados e transações com transações.

Separar três dimensões: **qualidade objetiva e dados disponíveis**, **adequação às preferências pessoais** e **oportunidade de preço com confiança estatística**. Campos ausentes não equivalem a zero nem a ausência de amenidade. Barato pode refletir reforma, ocupação, leilão, documentação, fração ideal ou área cadastrada incorretamente. Essas situações precisam de marcação e verificação própria; não receber selo automático de melhor compra.

Histórico deve registrar observações com data e eventos reais de preço. Mostrar novo, redução, aumento, revisitado, indisponível confirmado e desatualizado separadamente. Uma rotina diária precisa de fonte válida e host em execução; agenda configurada sem fonte operacional não entrega monitoramento diário de mercado.
