# Seu primeiro Radar

[Visão geral](../README.md) · [Fontes](SOURCES.md) · [Operação](OPERATIONS.md)

## Preparar a instalação

Tenha Git e Python 3.11+ disponíveis. No Windows:

```powershell
git clone https://github.com/eep0x10/imovel-radar.git
cd imovel-radar
./scripts/run.ps1
```

O script prepara o ambiente e inicia API e worker. Em outros sistemas, use os comandos do [README](../README.md#comece-em-poucos-minutos). Para personalizar variáveis, copie `.env.example` para `.env`, mantendo o arquivo somente no ambiente local.

## Configurar sua busca

1. Abra `http://127.0.0.1:8766` e crie uma conta com senha de pelo menos oito caracteres.
2. No **Radar**, ajuste orçamento, metragem e características. As preferências são salvas e aplicadas sem recarregar a página.
3. Em **Configurações → Fontes e atualização**, ative os coletores desejados e execute a primeira coleta. Confira cobertura, erros e avisos de cada fonte.
4. Volte ao **Radar**. Combine texto, fase, ordenação e **Aplicar minha busca**; use **Salvos** para consultar favoritos.
5. Selecione até quatro imóveis para comparar. Abra o anúncio original para confirmar disponibilidade e detalhes.
6. Crie um alerta a partir da busca atual. A lista existente forma a referência inicial; novas correspondências aparecem em **Notificações**.

## Entender o que aparece

- **Pronto** é a fase padrão quando não há indicação de planta ou obra; não é uma confirmação de entrega ou habitabilidade.
- **Na planta / em construção** reúne anúncios explicitamente classificados nessas fases.
- Uma mudança de preço recente aparece no card com valor anterior, diferença e data observada. O período é de 30 dias.
- Preços comparáveis são valores anunciados, não vendas efetivamente negociadas. Amostra insuficiente permanece visível como limitação.
- Tempo a pé até o metrô depende de localização precisa e da integração de rotas. Falhas do provedor aparecem nas configurações.

## Importar sem perder o histórico

Uploads passam por uma prévia; somente **Confirmar** grava. CSV, JSON, XLSX e XML VRSync têm contratos e limites no [guia de operação](OPERATIONS.md). A importação manual não mantém o arquivo sincronizado automaticamente.

Para migrar uma planilha legada local, coloque `resultados_quintoandar.xlsx` na raiz e habilite `IMOVEL_ENABLE_LEGACY_IMPORT=1`; esse fluxo é restrito à primeira conta. O arquivo é privado e não acompanha o projeto. Contas novas usam o perfil padrão do sistema, sem copiar preferências privadas de outra conta.

## Manter funcionando

API e worker precisam permanecer ativos. A coleta diária ocorre às 7h de `America/Sao_Paulo` por padrão; fontes pausadas ou bloqueadas não coletam. A sincronização da interface não substitui a coleta externa. Faça e teste backups conforme [Operação](OPERATIONS.md#backup-e-restauração).
