# Operação

## Rotina diária e disponibilidade

O worker verifica a agenda a cada minuto, às 7h de America/Sao_Paulo por padrão. Uma fonte que concluiu no dia não é repetida pelo agendamento; falhas têm intervalo mínimo de uma hora. Leases impedem concorrência e são renovados entre fontes. O último sinal do worker aparece no frontend.

**O computador/servidor e o processo precisam estar ligados.** Sem fonte válida, a rotina não coleta novos imóveis. Importações manuais não se atualizam sozinhas; ative um coletor ou feed. Falha, bloqueio ou feed vazio preservam o snapshot anterior; não marcam automaticamente imóveis como vendidos. Uma coleta bem-sucedida não comprova cobertura de todo o mercado.

Para um ciclo avulso:

```powershell
./.venv/Scripts/python.exe -m app.worker --once --force
```

`--force` ignora horário/cooldown, mas não a idempotência diária. O botão de atualização da fonte permite uma verificação manual adicional.

## Dados aceitos

CSV UTF-8 com vírgula ou ponto e vírgula, JSON em lista ou `{ "listings": [...] }`, XLSX (incluindo cabeçalhos legados) e XML VRSync para feeds. Limites: 10 MB, 5.000 registros por arquivo e limite de descompressão XLSX. Um erro impede o commit de todo o lote.

Campos mínimos: `source`, `external_id` (ou URL), `price`, `area`. Recomendados: `title`, `url`, `city`, `neighborhood`, `property_type`, `bedrooms`, `parking`, `condo_fee`, `property_tax`, `tax_period`, `observed_at`, `status`. A interface fornece modelo CSV. Datas ISO; IPTU com `monthly`, `annual` ou `unknown`.

Feeds bloqueiam destinos privados/loopback/link-local e redirecionamentos. DNS é validado e a conexão usa o IP validado com TLS/SNI preservados. Timeouts e tamanho limitados. Não coloque segredos na URL; endpoints que exigem autenticação específica precisam de um conector apropriado.

## Backup e restauração

```powershell
./.venv/Scripts/python.exe -m app.backup
./.venv/Scripts/python.exe -m app.backup --restore-copy data/backups/SEU-SNAPSHOT.sqlite3 --out data/restore-check.sqlite3
```

O backup usa a API online SQLite, inclui dados confirmados no WAL e verifica `integrity_check=ok`. Manifesto contém hash SHA-256 e contagens. A restauração recusa sobrescrever qualquer destino existente. Para trocar o banco ativo, pare a aplicação, preserve o anterior e configure `IMOVEL_DB_PATH` para a cópia restaurada. Backups contêm dados privados; mantenha-os fora do Git e teste-os periodicamente.

## Testes e implantação

```powershell
./.venv/Scripts/python.exe -m pytest
```

Testes cobrem isolamento entre contas, auth, importação, regressões de identidade/data/histórico, segurança do fetch, comparáveis, SAC/Price, agenda, leases e backup/restauração. Interface validada separadamente em 1440px e 390px. Evidências locais em `output/qa/`, ignoradas no Git.

`compose.yaml` fornece empacotamento para instalação própria com volume persistente. Não houve implantação remota nesta entrega: este repositório não tem destino de produção cadastrado. Para exposição pública, configurar HTTPS/reverse proxy, backups externos e operar a atualização. A API está documentada em `/api/docs`.

## Diagnóstico Google Maps

A tela Fontes mostra se o serviço de rotas está configurado e o motivo de uma recusa. `billing_required` significa que o Google exige faturamento habilitado no projeto da chave; não significa que o formato da chave esteja errado. Habilitar faturamento é uma ação do titular no Google Cloud, sujeita à cobrança do provedor.

Recusas de acesso, faturamento e quota suspendem novas consultas por uma hora. Rotas já armazenadas e ainda válidas continuam disponíveis. Uma chave nova tem diagnóstico independente. A aplicação só guarda códigos e mensagens próprias; nunca respostas de erro com credenciais.

Referência: [Google Geocoding: uso e faturamento](https://developers.google.com/maps/documentation/geocoding/usage-and-billing).

## Interface dinâmica

A busca reage à digitação e aos seletores. Preferências são salvas automaticamente após uma breve pausa e aplicadas ao Radar. A lista usa rolagem infinita em lotes, sem limite fixo de páginas; há botão acessível de carregamento e repetição em caso de erro. As telas de dados visíveis sincronizam a cada 15 segundos e ao reconectar, sem recarregar o documento. A sincronização aguarda o término de edições e dossiês abertos. Coleta externa continua seguindo sua rotina própria; atualizar a interface não dispara scraping.

O produto é exclusivo para compra. Anúncios explicitamente de aluguel são rejeitados na entrada e excluídos da listagem. Imóveis à venda com inquilino continuam classificados como compra.

## Buscas salvas e notificações

No Radar, **Criar alerta desta busca** guarda uma cópia dos critérios pessoais, texto de busca e fase do imóvel. Os imóveis compatíveis já existentes são registrados como lista inicial e não geram notificações retroativas. Cada alerta é independente: alterar os filtros do Radar depois não muda a busca salva.

Após uma importação ou coleta concluída, novas correspondências geram notificações vinculadas à busca e ao imóvel. Repetir a mesma coleta não duplica avisos. Uma queda de preço que faça um imóvel entrar pela primeira vez no filtro também pode gerar uma nova correspondência. Se a coleta falhar, a lista anterior permanece preservada.

Pausar interrompe novos avisos. Retomar reconcilia os imóveis atualmente disponíveis e informa correspondências ainda não notificadas uma única vez. Os alertas legados ficam separados como histórico; não são atribuídos retroativamente a buscas salvas. O feed principal é interno ao aplicativo, com lidas/não lidas e contador; não envia e-mail, mensagens ou notificações externas.

A migração do esquema 2 para 3 é aditiva e preserva imóveis, observações, favoritos e histórico. Faça backup antes da atualização. A restauração suporta snapshots das versões 1, 2 e 3 e exige as tabelas de buscas salvas em snapshots da versão 3.

## Navegação integrada

**Radar** reúne filtros e comparação dinâmica; **Minha jornada** reúne favoritos e acompanhamento. **Configurações** reúne conta, fontes, importações e diagnósticos. Links antigos de busca, fontes e comparação continuam encaminhando para o fluxo correspondente. A identidade visual existente é preservada: esta mudança reorganiza funcionalidades, sem exigir uma recriação do frontend.
