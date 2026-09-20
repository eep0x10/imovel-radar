# Pesquisa, Radar e alertas — revisão 1.5

O Radar distingue filtragem dos anúncios coletados de uma nova consulta aos portais. Alterações de critérios salvam automaticamente; **Pesquisar nas fontes** aguarda a gravação, valida intervalos e envia uma cópia dos parâmetros para um job persistente por conta. Consultas usam fontes habilitadas e autorizadas. Texto e fase refinam os resultados normalizados; somente filtros suportados pelos portais são enviados à origem.

## Comportamento e operação

- Área mínima 70 com máxima vazia significa 70 m² ou mais; mínima e máxima 70 significam exatamente 70 m².
- Regiões geográficas herdadas aparecem nos critérios avançados e podem ser desmarcadas; não são removidas sem ação do usuário.
- Um job por conta; cliques iguais não duplicam coletas. Alteração durante coleta agenda a última versão dos filtros. Estado e progresso sobrevivem a reinícios, com lease renovável e retomada pelo worker.
- Falhas preservam anúncios existentes. Coleta parcial nunca significa cobertura integral. O app não contorna bloqueios. OLX e VivaReal foram retirados da coleta a pedido do usuário.
- Alertas usam o perfil salvo, com primeira execução pelo worker e execução diária subsequente. Falhas por fonte permitem nova tentativa após uma hora. Limite de páginas sem erro permanece explicitamente parcial.
- O worker precisa estar ativo. Enquanto parado, jobs ficam pendentes; sem fontes, a pesquisa informa erro e orienta a configuração.
- A ausência em uma coleta não remove imóveis nem comprova venda. Preços e disponibilidade precisam de confirmação no anúncio.

## Decisões de interação

Mantido o estilo existente: esta revisão corrige comportamento, não redesenha a aplicação. Intervalos e restrições ficam explicados perto dos campos, e o progresso fica junto da busca. Inputs continuam editáveis durante coleta. Erros de validação mantêm o rascunho e impedem consulta com valores antigos. Resultados e notificações atualizam sem full refresh.

Anime.js mantém transição curta nos resultados de uma ação explícita e nos lotes de scroll infinito; atualização de fundo e progresso são imediatos para não produzir piscadas. Instâncias são revertidas na troca de conteúdo e ao sair; prefers-reduced-motion desativa a transição. Seleção, erro e confirmação têm texto imediato; foco e rascunho são preservados durante atualização automática.

## Evidência de QA

Reprodução isolada: editar mínima para 70, limpar máxima e clicar imediatamente iniciou coleta com 70/null; imóveis de 72 e 95 m² apareceram sem reload. Máxima 60 com mínima 70 bloqueou coleta com mensagem clara. Testes de regressão cobrem fila, isolamento de contas, reinício, snapshots de alertas, retries e ranking equivalente.

Benchmark local com 1.009 registros: avaliação original 11,639 s, agrupada 1,612 s; resultados idênticos com instante fixo. A coleta real com os filtros da conta consultou 216 registros no QuintoAndar (9 páginas, completa) e 509 na Loft (17 páginas, parcial). OLX e VivaReal foram removidos da coleta após o usuário solicitar.

Prontidão operacional é limitada pela disponibilidade externa e pela execução contínua local. Esses testes não certificam disponibilidade de todos os portais nem implantação pública.

QA adicional: com Radar em 100 m², alerta previamente salvo em 70 m² encontrou dois novos anúncios de 82 m² no provedor controlado e exibiu duas notificações; sem alterar os critérios atuais da conta. Desktop e viewport de 390 px revisados, incluindo erro de intervalo, progresso, resultados e feed de notificações. Controles móveis de ordenação/fase receberam linhas próprias para não truncar as opções. Backup de 1.009 registros restaurado em banco isolado com integrity_check=ok.
