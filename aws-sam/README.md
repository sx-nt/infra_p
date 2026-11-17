# Backend AWS SAM do Classly

O template provisiona uma API Gateway REST, funções Lambda separadas por domínio e sete tabelas
DynamoDB (incluindo a base de usuários). Para modelo de dados e contrato das rotas, consulte
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

Localmente não há Cognito: `LOCAL_DEV_USER` em [`env.json`](env.json) define
o e-mail do usuário de desenvolvimento, que é coordenador por estar também em
`ADMIN_EMAILS`. Para testar a visão do professor, troque `LOCAL_DEV_USER` pelo
e-mail de um professor cadastrado e reinicie `make api`.

Com a API no ar, o frontend roda com:

```sh
cd ../web
npm install
npm run dev
```

O Vite encaminha `/api/*` para `http://127.0.0.1:3000`, como o CloudFront faz
na nuvem.

## Implantação

A implantação em nuvem é feita pelo Pulumi ([`pulumi/`](../pulumi/README.md)),
que publica estas mesmas funções com autorizador JWT do Cognito. Este template
serve ao desenvolvimento local.
