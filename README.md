# Classly
## Infraestrutura e Serviços em Nuvem 
Equipe: Isadora Soares Eidt e Sant Semeghini


Sistema web para planejamento, geração e publicação de grades de horários
institucionais, considerando carga horária, disponibilidade dos professores e
restrições importadas do Google Calendar.

## Documentação

| Documento | Conteúdo |
| --- | --- |
| [Requisitos funcionais](docs/requisitos-funcionais.md) | Funcionalidades que o sistema deve oferecer. |
| [Requisitos não funcionais](docs/requisitos-nao-funcionais.md) | Critérios de qualidade, desempenho, segurança e infraestrutura. |
| [Regras de negócio](docs/regras-de-negocios.md) | Restrições que devem ser respeitadas pela aplicação e pelo algoritmo. |
| [Casos de uso](docs/casos-de-uso.md) | Principais interações entre os atores e o sistema. |
| [Diagrama de Classe](docs/diagrama-classe.md) |Diagrama de Classe. | 
| [Diagrama de Atividade](docs/diagrama-atividade.md) |Fluxo principal do sistema, desde o cadastro até a publicação da grade. |
| [Diagramas de blocos](docs/diagramas-de-blocos.md) | Arquitetura lógica, fluxo principal e ciclo de vida da grade. |
| [Fluxogramas](docs/fluxogramas.md) | Processos de autenticação, sincronização, gestão acadêmica e publicação. |
| [API e modelo de dados](docs/api.md) | Contrato inicial dos endpoints serverless e tabelas DynamoDB. |

## Visão geral

O sistema atende dois perfis principais:

- **Professor:** autentica-se, sincroniza sua agenda e consulta os horários
  institucionais publicados.
- **Coordenador/Administrador:** gerencia a estrutura curricular, gera e
  valida a grade, faz ajustes manuais e publica a versão aprovada.

O fluxo principal é:

1. O usuário realiza login por um provedor externo aprovado.
2. O professor informa ou sincroniza suas restrições de horário.
3. A coordenação cadastra professores, disciplinas, turmas e associações.
4. O sistema gera uma proposta de grade respeitando as regras de negócio.
5. A coordenação valida, ajusta e aprova a grade.
6. Os professores recebem uma notificação com o resultado publicado.

## Escopo documentado

Esta documentação cobre:

- autenticação e perfis de acesso;
- integração com o Google Calendar;
- cadastro e persistência da estrutura curricular;
- geração, validação e publicação da grade;
- notificações e auditoria;
- requisitos de qualidade e infraestrutura.

## Infraestrutura

| Diretório | Uso |
| --- | --- |
| [`web/`](web) | Frontend React (Vite): telas da coordenação e do professor, login pelo Cognito. |
| [`aws-sam/`](aws-sam/README.md) | Desenvolvimento local: SAM + DynamoDB Local com as mesmas funções Lambda. |
| [`pulumi/`](pulumi/README.md) | Nuvem (stacks `dev` e `prod`): DynamoDB, Lambda, API Gateway, Cognito, S3, CloudFront, SES, certificado ACM e registros Route 53. |
| `docker/compose/` | Experimento introdutório da disciplina com Docker Compose. |

Em ambos os stacks o CloudFront é o único ponto de entrada, com HTTPS
obrigatório: `/` entrega o frontend guardado em um bucket S3 privado e
`/api/*` encaminha para o API Gateway → Lambda → DynamoDB. Em `prod`, o
certificado ACM é validado por DNS e o domínio aponta para a CDN por registros
alias na zona Route 53 do subdomínio `classly.negoci.online`, delegada pelo
professor (ver [pulumi/README.md](pulumi/README.md#primeira-implantação-do-prod-delegação-do-subdomínio)).

### Acesso e perfis

O login é feito pelo Amazon Cognito: cadastro por e-mail com código de
verificação enviado por e-mail, recuperação de senha e, opcionalmente, conta
Google. Toda rota da API, exceto `/health`, exige o token do Cognito. O perfil
de cada usuário fica na tabela de usuários do DynamoDB:

| Perfil | Como é atribuído | O que pode fazer |
| --- | --- | --- |
| Coordenação | E-mail em `classly:adminEmails` ou promovido por outro coordenador | Cadastros, habilitações, disponibilidade de todos, gerar, ajustar, validar, aprovar e publicar grades, reenviar e-mails, gerenciar usuários e consultar a auditoria. |
| Professor | Conta criada com o e-mail de um professor cadastrado | Informar a própria disponibilidade (ou importá-la do Google Calendar) e consultar grades publicadas. |
| Aguardando liberação | Demais contas | Nenhum acesso aos dados até a coordenação liberar. |

Ao publicar uma grade, cada professor recebe por e-mail (Amazon SES) os
próprios horários. O contrato da API está em [docs/api.md](docs/api.md).

A coordenação pode gerar uma proposta de grade automaticamente, ajustá-la e
levá-la pelo ciclo Rascunho → Em validação → Aprovada → Publicada; o professor
pode importar compromissos semanais do Google Calendar. Todas as operações
críticas ficam na **Auditoria**. A API está documentada em OpenAPI
([`docs/openapi.yaml`](docs/openapi.yaml)), visível em `/api-docs/index.html`
no site publicado.

## Como executar

Tudo é implantado por um único `pulumi up`: o programa compila o frontend,
empacota as funções e cria a infraestrutura completa. Leva de 5 a 10 minutos
na primeira vez (a maior parte é o CloudFront).

### 1. Pré-requisitos

- Conta AWS com um usuário IAM preparado conforme
  [Preparação do ambiente](#preparação-do-ambiente) e suas chaves exportadas
  (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION=sa-east-1`).
- Conta no Pulumi (`pulumi login` ou `PULUMI_ACCESS_TOKEN`).
- Ferramentas: `make install` instala AWS CLI, SAM CLI, Pulumi e uv. Também
  são necessários Node.js 22 e, para os testes de integração, Docker.

### 2. Implantar

```bash
git clone https://github.com/sx-nt/infra_p.git
cd infra_p/pulumi
pulumi stack init dev
pulumi config set classly:adminEmails "seu-email@exemplo.com"
pulumi config rm classly:senderEmail
pulumi up
```

- `pulumi stack init dev` cria o stack na organização Pulumi de quem executa,
  aproveitando as configurações de [`Pulumi.dev.yaml`](pulumi/Pulumi.dev.yaml).
- `classly:adminEmails` define quem entra como coordenação: use o seu e-mail
  para conseguir cadastrar dados.
- `classly:senderEmail` é o remetente das notificações. O valor versionado é
  da equipe; remova-o (como acima) ou troque pelo seu e-mail, que receberá um
  link de confirmação da AWS (de novo a cada vez que o stack for recriado do
  zero).

Ao final, `pulumi up` mostra a `url` do sistema (ex.:
`https://d1234abcd.cloudfront.net`).

### 3. Usar

1. Abra a `url`, clique em **Entrar com e-mail** e em **Criar uma conta** com o
   e-mail informado em `classly:adminEmails`.
2. Digite o código de verificação recebido por e-mail. Você entra como
   **Coordenação**.
3. Cadastre uma disciplina, um professor (com um e-mail que você acesse), uma
   turma e a habilitação do professor na disciplina.
4. Em **Grades → Nova grade**, escolha o período e clique em **Gerar proposta
   automaticamente** (ou monte as aulas à mão), **Valide** e **Salve o
   rascunho**. Depois **Envie para validação**, **Aprove** e **Publique**.
5. Em **Auditoria**, confira o registro de cada operação.
6. Em uma janela anônima, crie a conta com o e-mail do professor: ele entra
   direto como **Professor** e vê a grade publicada e a própria disponibilidade.

Com `classly:senderEmail` configurado e confirmado, o professor recebe os
horários por e-mail. Contas AWS novas ficam no *sandbox* do SES, que só entrega
para endereços verificados em **SES → Verified identities**.

### 4. Testes

```bash
make test
```

Executa os mesmos testes do CI:

| Alvo | O que testa |
| --- | --- |
| `make test-backend` | Testes unitários das regras e da autorização das Lambdas, com DynamoDB e SES simulados (moto). |
| `make test-integration` | Fluxo completo de um período letivo contra o DynamoDB Local (Docker), roteando cada requisição para a Lambda definida no `template.yaml`. |
| `make test-web` | Testes do frontend (login PKCE, tokens, cliente da API) e build. |
| `make test-infra` | Programa Pulumi com mocks: rotas protegidas, bucket privado, HTTPS, domínio, certificado e DKIM no prod. |

Depois de uma implantação, o teste de fumaça confere o ambiente publicado:

```bash
cd pulumi
CLASSLY_URL=$(pulumi stack output url) uv run pytest tests/deployed
```

### 5. CI/CD (GitHub Actions)

| Workflow | Quando roda | O que faz |
| --- | --- | --- |
| [`ci.yml`](.github/workflows/ci.yml) | Pull requests e pushes fora da `main` | Testes do backend (unitários e integração com DynamoDB Local), do frontend e da infraestrutura. |
| [`cd.yml`](.github/workflows/cd.yml) | Push na `main` → `dev`; tag `v*` → `prod`; ou manual | Roda o CI, executa `pulumi up` no stack e o teste de fumaça na URL publicada. |

Para o CD funcionar, cadastre em **Settings → Secrets and variables →
Actions** do repositório os secrets `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY` e `PULUMI_ACCESS_TOKEN`. Antes da primeira tag de
produção, a zona do subdomínio precisa ter sido criada e delegada (ver
[pulumi/README.md](pulumi/README.md#primeira-implantação-do-prod-delegação-do-subdomínio)).

### 6. Remover

```bash
pulumi destroy
```

Remove todos os recursos do stack (os serviços usados cobram por uso; parado,
o custo é praticamente zero).

## Preparação do ambiente

No IAM da conta AWS da equipe:

1. Criar um grupo e um usuário sem acesso ao console, associado ao grupo.
1. Criar a política [`iam-policy.json`](iam-policy.json) (IAM → Policies →
   Create policy → JSON) e associá-la ao grupo. Ela permite criar os papéis e
   os grupos de log das funções Lambda e gerenciar a zona Route 53 do
   subdomínio de produção.
1. Associar também as políticas gerenciadas `AmazonAPIGatewayAdministrator`,
   `AmazonDynamoDBFullAccess_v2`, `AWSLambda_FullAccess`,
   `CloudFrontFullAccess`, `AWSCertificateManagerFullAccess`,
   `AmazonCognitoPowerUser`, `AmazonS3FullAccess` e `AmazonSESFullAccess`.
   Somadas à política do passo anterior são 10, o limite da AWS por usuário
   ou grupo.
1. Criar uma chave de acesso para o usuário.

Variáveis de ambiente (ou secrets do Codespaces): `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION=sa-east-1` e
`PULUMI_ACCESS_TOKEN`.

```bash
make install
```
