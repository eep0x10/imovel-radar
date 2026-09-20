# Privacidade e publicação

Guarde chaves exclusivamente em `.env` ou variáveis de ambiente. Bancos SQLite, planilhas pessoais, configurações, backups, logs e exportações não pertencem ao Git. O frontend nunca recebe a chave Google Maps.

A auditoria `scripts/privacy_audit.py` verifica arquivos versionados e, com `--history`, todos os commits alcançáveis pelas referências locais. Detecta padrões de credenciais, caminhos pessoais e arquivos privados. É uma barreira adicional, não prova universal de ausência de dados sensíveis.

O histórico anterior foi substituído por uma base sanitizada após backup privado. Não mescle branches de clones antigos: elas podem reintroduzir dados removidos. Faça um clone novo ou porte somente patches revisados.

Reescrever referências não apaga cópias em outros clones nem caches e referências internas de pull requests no GitHub. Essas referências exigem tratamento pelo GitHub Support; uma chave anteriormente versionada não passa a ser inédita por reescrever o histórico. Consulte a [documentação oficial](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository).

A visibilidade do repositório não é alterada pela limpeza. Publicação do código não publica seu banco ou preferências. Exemplos e testes devem usar dados sintéticos.
