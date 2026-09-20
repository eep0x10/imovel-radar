# Validação do protótipo v1

Data local: 19/09/2026. Escopo: somente interface isolada em `prototype/`.

## Evidências

- `node --check prototype/app.js`: passou.
- Servidor HTTP local em 127.0.0.1:8765.
- Navegador integrado: tentativa de abertura por CUA expirou; abertura de painel por `open_in_codex` posteriormente ficou enfileirada. Não afirmar navegação integrada bem-sucedida.
- Playwright CLI com Chrome instalado no sistema falhou na inicialização; Chromium já instalado em cache iniciou e executou a validação.
- Seis telas em 1440px e 390px: nenhuma ultrapassou a largura do documento. Comparador utiliza rolagem interna horizontal intencional.
- Inspeção visual de radar desktop/mobile, dossiê mobile, preferências mobile, jornada desktop e comparador desktop. Corrigidos fechamento de heading na jornada, separação de rótulos e restauração de foco do diálogo.
- Console após recarregamento: sem erros observados; antes havia 404 de favicon, resolvido com ícone inline.

## Fluxos exercitados

1. Radar inicial com seis imóveis; busca por Belém retorna dois; busca inexistente mostra estado vazio e permite limpar filtros.
2. Dois imóveis selecionados abrem tabela de comparação; botão remove seleção; dossiê abre e Escape fecha, devolvendo foco ao acionador após correção.
3. Orçamento máximo de R$ 300.000 com os demais filtros padrão retorna dois exemplos. Um assert inicial executado antes da renderização falhou; inspeção subsequente confirmou o estado esperado. A espera foi ajustada nas verificações seguintes.
4. Nota digitada na jornada permanece ao mudar a etapa do imóvel na mesma sessão.
5. Price a juros zero, principal R$ 158.000 e prazo de 100 meses: R$ 1.580 de parcela + R$ 485 de despesas = R$ 2.065. SAC produz resultado; entrada maior que o imóvel é rejeitada.
6. Alternativa Mapa abre esquema explicitamente fictício. Nenhuma distância/coordenada real validada.

Capturas locais em `prototype/evidence/`, excluídas do Git por serem evidências geradas. Exemplos: `radar-desktop.png`, `radar-mobile.png`, `comparison-selected-1440.png`, `comparison-selected-390.png`, `dossier-390.png`, `journey-1440.png`.

## Não validado / não implementado

Contas, isolamento de usuários, banco, persistência após reload, feeds, coleta dos portais, scheduler, alertas reais, ranking calculado, mapa geográfico e deploy. Os valores de ranking são fixtures. Nenhuma chamada aos endpoints antigos foi realizada. Script e planilha legados continuam intactos; a chave hardcoded segue exigindo rotação e correção durante a implementação.

## Decisão visual pendente

Recomendação: lista como entrada principal para comparar oportunidades diárias; mapa como visualização secundária para explorar localização. Paleta verde/oliva, valores alinhados, evidência e pendências junto ao anúncio. O protótipo v1 precisa de aprovação explícita antes de integração ao produto.
