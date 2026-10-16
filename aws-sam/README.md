# Backend AWS SAM do Classly

O template provisiona uma API Gateway REST, funções Lambda separadas por domínio e seis tabelas
DynamoDB. Para modelo de dados e contrato das rotas, consulte
[`docs/api.md`](../docs/api.md).

## Executar localmente

Requisitos: Docker, AWS CLI, AWS SAM CLI e tmux.

```sh
make
```

O comando abre um painel tmux, sobe DynamoDB Local, cria as tabelas e inicia a
API SAM em `http://127.0.0.1:3000`. Para cadastrar um professor de exemplo ou
consultar o estado da função:

```sh
make teacher
make teachers
make health
```

Também é possível iniciar os serviços separadamente com `make up`, `make
api`, e encerrar com `make stop`. As credenciais AWS exportadas pelo Makefile
são valores locais de teste para o DynamoDB Local.

## Implantação

`sam build` e `sam deploy --guided` usam DynamoDB AWS e os recursos definidos
no `template.yaml`. Configure uma conta e região AWS antes da implantação.
As rotas ainda não têm authorizer de login institucional: use somente dados de
desenvolvimento até integrar autenticação e autorização por perfil.
