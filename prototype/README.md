# Protótipo v1 — Imóvel Radar

Interface isolada. Nenhuma API de imóveis, login, banco ou agendamento de produção está conectado. Dados fictícios; ações guardadas somente em memória e perdidas ao recarregar.

Abrir com servidor estático limitado a localhost:

```powershell
& C:/Users/eep0x10/scoop/apps/python/current/python.exe -m http.server 8765 --bind 127.0.0.1 --directory C:/Users/eep0x10/dev/imovel-search-SP/prototype
```

Acesse http://127.0.0.1:8765. Rotas: radar, compare, journey, budget, profile, sources.

- Experimente buscar Belém, filtrar quedas, salvar, selecionar dois imóveis e comparar.
- Abra um dossiê com dados incompletos para ver a diferença entre preço baixo e evidência insuficiente.
- Altere limites em Minha busca e aplique-os no radar.
- Registre uma nota e mova um imóvel em Minha jornada.
- Compare SAC e Price e teste taxa zero no planejamento.
- Alterne Lista/Mapa: o mapa é somente um esquema visual, sem coordenadas reais e sem vínculo aos filtros.

Os pesos são controles demonstrativos; não recalculam as notas fictícias. A foto do primeiro imóvel é gerada por IA e identificada na interface; os demais mostram ausência de foto. A galeria completa depende das fontes reais.

Antes de integrar à aplicação, esta versão deve receber aprovação explícita do usuário, conforme a skill frontend-craft.
