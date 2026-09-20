# Imóvel Radar — evolução proposta

Status: descoberta e protótipo v1, aguardando aprovação visual. Data: 2026-09-19.

## Base verificada

Repositório original no commit 44f3f11: `imovel.py` e uma planilha. Sem aplicação web, autenticação, banco, testes ou agendamento versionados. Não executei o coletor legado, para não usar a chave embutida nem sobrescrever a planilha.

Problemas confirmados no código:

- `combine_first` combina fontes pelo índice da linha em vez de concatenar anúncios. Pode gerar linhas com dados de imóveis diferentes.
- Identificação somente por `_id`, sem namespace da fonte; ausência de deduplicação do mesmo imóvel entre portais.
- Requisições sem timeout, tratamento HTTP, paginação confiável, retries limitados ou observabilidade. Um pedido enorme não prova cobertura completa.
- Três regiões Loft usam as mesmas coordenadas; campos de status incompatíveis são renomeados como se fossem equivalentes.
- Google Maps tem chave hardcoded. Revogar/rotacionar no provedor e usar variável de ambiente; retirar do código não elimina exposição no histórico.
- Tempo de caminhada extraído de texto localizado; duração deve usar segundos estruturados. Desconhecido não é zero.
- Detecção de andar por substring da página não demonstra o andar do imóvel.
- IPTU e condomínio combinados sem unidade/período verificado. Financiamento divide principal por 96 sem juros ou despesas.
- Registros removidos não estão no dataframe atual para receber status REMOVIDO; arquivo sobrescrito perde observações e histórico.

## Produto

Organizar a decisão diária de compra, do anúncio à visita e à proposta, para múltiplos usuários. São Paulo é o primeiro mercado, com modelo extensível a outras cidades.

Fluxos: criar perfil de busca → atualizar fontes → revisar novidades → entender preço e lacunas → comparar → salvar → visitar → registrar proposta e decisão.

### Experiência prevista

1. Radar: novidades, quedas, filtros, ordenação, favoritos e resumo diário.
2. Dossiê: fotos de origem, características, fontes e datas por campo, histórico de preço, comparáveis, despesas, mobilidade, lacunas e perguntas de visita.
3. Comparador: até quatro imóveis, preço/m², despesas, qualidades, preferências, confiança e pendências lado a lado.
4. Minha busca: orçamento, área, quartos, acessibilidade, vaga, elevador, pets, sol, andar, deslocamentos e prioridades; requisitos eliminatórios separados de preferências.
5. Jornada: salvos, contatados, visita marcada, visitados, proposta, descartados e comprado; notas e checklist por usuário.
6. Orçamento: entrada, reserva, reforma, despesas de aquisição configuráveis, SAC/Price, taxa efetiva, prazo, seguros e CET quando disponível. Nunca tratar simulação como oferta bancária.
7. Fontes: última tentativa e último sucesso separados, cobertura/paginação, falha/bloqueio/dado antigo visíveis, importação autorizada e links originais.
8. Alertas: dentro da aplicação; e-mail/Telegram somente após configuração e autorização de envio. Alertas idempotentes para entrada no perfil, queda relevante e atualização.

## Três avaliações, sem falsa precisão

- Qualidade observável: estado, planta, ventilação/iluminação, acessibilidade, conservação, custos recorrentes e documentação verificada. Um atributo só recebe avaliação quando há evidência. Sol, ruído e condição estrutural não podem ser inferidos de marketing.
- Aderência: requisitos e pesos pessoais. Ausência de informação em requisito obrigatório produz pendência, não aprovação automática. Mudanças de preferência recalculam esta avaliação sem alterar os dados do imóvel.
- Oportunidade: preço pedido por m² comparado com anúncios comparáveis ativos, únicos e recentes. Não confundir preço anunciado com preço de transação ou garantia de valorização.

Comparáveis: mesmo tipo, microrregião, área próxima, dormitórios, vagas e características disponíveis; excluir o próprio imóvel, duplicatas e outliers por regra versionada. Mostrar mediana, dispersão, N, período e raio; registrar fallback geográfico. N insuficiente → sem estimativa, em vez de desconto inventado. Confiança depende de amostra, homogeneidade, frescor e completude. A fórmula e seus pesos devem ser versionados e inspecionáveis. FIPEZAP é contexto agregado, não avaliação pontual.

Dados ausentes são NULL. Zero vagas difere de vagas desconhecidas. IPTU anual e mensal preservam unidade e valor originais. Condomínio não vira prestação. Endereço aproximado não produz trajeto preciso. Cobertura insuficiente deve ficar visível.

## Arquitetura recomendada para implementação

- Backend Python/FastAPI, PostgreSQL com migrations; frontend React/TypeScript. Processo worker independente para coletas; scheduler diário configurável em America/Sao_Paulo, trava contra sobreposição e chave de idempotência.
- Entidades: users, sessions, search_profiles, sources, ingestion_runs, source_listings, canonical_properties, observations, price_history, saved_properties, user_notes, visit_tasks, alerts, comparable_snapshots.
- Separar propriedade física e anúncio. Match automático apenas com evidência suficiente; candidatos ambíguos permanecem separados. Conservar links, IDs, proveniência e divergências.
- Fonte adaptadora com contrato normalizado e fixtures. Timeouts, paginação, limites, backoff limitado, cache e parada em bloqueio. Sem prometer API pública ou raspar todos os portais até validação.
- Uma falha não remove imóveis nem substitui um snapshot válido por vazio. Ausência vira suspeita de indisponibilidade apenas após coleta completa e confirmação posterior, com razão auditável.
- Conta própria, senha com hash robusto, sessão segura, autorização por proprietário em cada recurso; testes de isolamento entre usuários. Não adicionar CSRF sem nova autorização explícita.
- Importação da planilha legada validada e com preview, sem sobrescrever o original. Exportação de dados pessoais e exclusão planejada, com confirmação apropriada.
- Configuração por ambiente, logs sem segredos, healthchecks distintos da saúde dos coletores, backups com restauração testada e documentação operacional.

## Etapas e critérios observáveis

1. Aprovar protótipo v1: navegação, filtros, comparador, dossiê, preferências, jornada, fontes e orçamento, desktop e 390px. Fixtures explicitamente fictícias; sem backend ou persistência de produção.
2. Núcleo: normalização, banco/migrations, autenticação e isolamento; testes de unidades, duplicação, dinheiro, estados ausentes e importação idempotente.
3. Coleta: validar QuintoAndar e Loft hoje; ampliar para conectores efetivamente acessíveis, feeds de imobiliárias e importação. Demonstrar repetição, falha parcial e preservação do histórico. Catálogo de fonte não equivale a integração ativa.
4. Inteligência: comparáveis auditáveis, ranking explicável, trajetória de preço e custo total. Testar amostra pequena, duplicatas, outliers, requisito ausente e monotonicidade.
5. Aplicação completa: ligar telas aprovadas, testar cadastro/login e acesso cruzado, salvar/recarregar favoritos, notas, visitas, alertas e perfil.
6. Operação: executar coleta diária real com evidência, testar recuperação e backup; publicar somente após descobrir destino e passar preflight de produção. Nenhuma produção cadastrada foi confirmada nesta fase.

## Limites atuais

Este documento e o protótipo não constituem sistema pronto, coleta diária ativa, integração validada, preço de mercado comprovado ou autenticação implementada. Serviços de geocodificação, feeds parceiros e envio podem exigir credenciais e custos; escolher opções reais durante implementação sem contratar automaticamente.
