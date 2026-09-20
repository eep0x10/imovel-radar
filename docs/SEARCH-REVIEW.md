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


## Correção dos filtros — 1.5.1

Separados condomínio mensal (`condo_max`) e condomínio + IPTU (`monthly_max`), preservando o limite anterior. Zero é um limite real; vazio desativa o respectivo limite. Dados insuficientes têm rótulo “Filtros a confirmar”; a exclusão de desconhecidos continua uma escolha explícita. IPTU anual é dividido por 12 somente quando a periodicidade é conhecida.

A origem do defeito principal era a periodicidade descartada pelo adaptador QuintoAndar: todo custo combinado ficava pendente. O contrato foi conferido em três anúncios públicos. Migração idempotente corrige apenas registros vinculados ao coletor QuintoAndar, sem alterar importações genéricas, preço, observações ou favoritos. Na base local, 264 registros foram reparados após snapshot; 1.009 imóveis e 1.408 observações preservados, integrity_check=ok.

Também corrigidos: regiões aplicadas apenas na coleta e ignoradas no Radar, reativação visual de região sem restaurar coordenadas, aliases de São Paulo e espaços em bairros, anúncios vendidos/inativos, validação inteira de quartos/vagas/andar e serialização concorrente de salvamentos. Buscas salvas mantêm seu snapshot independente. Ranking versionado em 1.2.0 para refletir cobertura geográfica e condomínio separado.

QA isolado pelo navegador integrado: condomínio 500 elimina 700, mantém 400 e 500; desconhecido aparece identificado e é removido ao ativar exclusão. Total mensal 500 mantém condomínio 400 + IPTU anual 1.200; teto de condomínio zero retorna vazio. Desativar e reativar região restaura a restrição. Formulário e resultados preservados sem navegação/reload; desktop e 390 px inspecionados. Estilo e integração Anime.js existentes mantidos; feedback de salvamento é imediato, sem nova animação de formulário.

Suite: 284 testes aprovados, incluindo matriz de limites, valores ausentes, mapa e alerta congelado. Auditoria local após a correção: 154 correspondências entre 1.008 anúncios de compra, nenhuma acima do custo mensal conhecido configurado. Isso não comprova custos ausentes nem disponibilidade futura dos portais.


## Caminhadas — revisão 1.5.2

Causa reproduzida: o provedor Google respondeu `billing_required`; a base tinha zero rotas apesar de 773 anúncios com coordenadas. O usuário escolheu a alternativa gratuita limitada. O modo OSM foi configurado localmente; a chave Google permanece privada e sem uso nesse modo.

Mantida a apresentação existente. Cartões e comparação exibem tempo a pé e nome da estação, ou motivo da pendência. O dossiê também contém a informação. Atribuição acompanha os resultados OSM. Atualizações entram pelo polling existente sem full refresh; atualização de fundo não repete animação Anime.js. Nenhuma nova animação necessária para troca de valores textuais.


Validação real: sete anúncios no Largo São José do Maranhão receberam rota a pé de 1.316 m / 17,55 min até Carrão – Assaí Atacadista, reutilizando um cálculo em três estações candidatas. Catálogo inicial OSM contém 64 estações por nós, com cobertura explicitamente parcial; a consulta completa de nós/vias/relações sofreu indisponibilidade. Resultados dessa base recebem qualificação de cobertura parcial. Isso não garante a estação absolutamente mais próxima fora do catálogo. Desktop e 390px verificados em base QA isolada com estado calculado e pendente, sem erros de console.

Validação: 296 testes passaram; verificações focadas da fila e do provedor foram repetidas após o ajuste de prioridade. Banco manteve 1.009 imóveis e 1.408 observações com integrity_check=ok. API local saudável na versão 1.5.2 e worker ativo.


## Rotas sob demanda — 1.5.3

A pedido do usuário, a fila automática foi retirada. Coletas e rotina diária não chamam serviços de caminhada. Cada cartão e dossiê oferece Calcular rota até o metrô: feedback de carregamento imediato, botão desativado durante a consulta e troca somente do bloco de rota daquele imóvel. Cache válido evita consultas repetidas; os demais anúncios não são gravados, mesmo na mesma coordenada. Falhas e limites permitem nova tentativa manual. Autenticação, propriedade do anúncio, lock por imóvel e verificação da localização antes da gravação protegem a operação concorrente.

Estilo mantido, sem prévia de redesign. Carregamento textual acessível por aria-live e aria-busy; nenhuma animação bloqueia a operação. Anime.js existente permanece nos resultados; cálculo não redesenha a lista nem interfere em formulário ou scroll.

QA: 299 testes aprovados. Navegador integrado demonstrou carregamento em um único cartão, resultado de 12,5 min na fixture escolhida e três imóveis vizinhos sem rota, mesmo com coordenadas iguais. Desktop e 390 px inspecionados; console sem erros.
