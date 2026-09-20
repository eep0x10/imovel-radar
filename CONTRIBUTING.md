# Contribuir

Crie um ambiente virtual e instale `requirements.lock`. Execute pytest, auditoria de privacidade e Prettier conforme README.

Inclua regressões para mudanças em coleta, identidade, datas, ranking, isolamento de contas e backup. Use fixtures sintéticas, nunca snapshots privados ou chaves reais. Coletores devem ter timeout, limite de páginas/tamanho, identidade estável e falhas visíveis.

Mudanças de UI exigem verificação desktop e móvel. Mudanças em armazenamento exigem migração compatível e teste de backup/restauração. Não confunda testes simulados com evidência de coleta real.
