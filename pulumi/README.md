# Infraestrutura em nuvem do Classly (Pulumi)

Programa Pulumi em Python que publica o Classly na AWS: frontend, API,
autenticação e banco. As funções Lambda usam o mesmo código de
[`aws-sam/functions`](../aws-sam/functions), que também roda localmente com
SAM + DynamoDB Local; o frontend é o build de [`web/`](../web).

## Recursos

| Recurso | dev | prod |
| --- | --- | --- |
| DynamoDB: 8 tabelas sob demanda (professores, disciplinas, turmas, habilitações, disponibilidades, grades, usuários, auditoria) | ✓ | ✓ (com point-in-time recovery) |
| Lambda: uma função por domínio, com papel IAM próprio restrito às tabelas que usa | ✓ | ✓ |
| CloudWatch Logs: um grupo por função e o log de acesso da API (inclui requisições recusadas pelo autorizador), retenção de 14 dias | ✓ | ✓ |
| Lambda de auditoria de login (gatilho pós-autenticação do Cognito) | ✓ | ✓ |
| AWS Budgets: alerta mensal (US$ 5 por padrão; 50%, 80% e previsão de 100%) para os e-mails da coordenação | — | ✓ |
| API Gateway (HTTP API) com as rotas de [`docs/api.md`](../docs/api.md) e autorizador JWT (exceto `/health`) | ✓ | ✓ |
| Cognito: base de usuários por e-mail com verificação por código, login gerenciado em português e Google opcional | ✓ | ✓ (com proteção contra exclusão) |
| S3 privado com o build do frontend, lido só pelo CloudFront (OAC) | ✓ | ✓ |
| CloudFront: site em `/`, API em `/api/*` (sem cache), HTTPS obrigatório | domínio `*.cloudfront.net` | domínio próprio |
| SES: e-mail aos professores quando uma grade é publicada | se `classly:senderEmail` | domínio com DKIM |
| ACM: certificado em `us-east-1` validado por DNS | — | ✓ |
| Route 53: zona própria do subdomínio (protegida), validação do certificado, DKIM e alias `A`/`AAAA` para a CDN | — | ✓ |

O tráfego segue `navegador → CloudFront (HTTPS) → S3 (site) | API Gateway → Lambda → DynamoDB`.
O login acontece no domínio do Cognito (`login_url`), que devolve o navegador
ao site com um código trocado por tokens (PKCE); o frontend envia o ID token
em `Authorization: Bearer` e o API Gateway o valida antes de chamar a Lambda.

## Stacks e configuração

| Chave | Stack | Descrição |
| --- | --- | --- |
| `aws:region` | dev, prod | Região padrão (`sa-east-1`). |
| `classly:adminEmails` | dev, prod | E-mails (separados por vírgula) que entram como coordenação. |
| `classly:senderEmail` | dev (opcional) | Remetente das notificações; a AWS envia um link de confirmação para ele. |
| `classly:googleClientId` / `classly:googleClientSecret` | dev, prod (opcional) | Cliente OAuth do Google: habilita “Entrar com Google” e “Importar do Google Calendar” (o segredo com `--secret`). |
| `classly:monthlyBudgetUsd` | prod (opcional) | Limite do alerta de orçamento mensal (padrão `5`). |
| `classly:domain` | prod | Subdomínio público do sistema (`classly.negoci.online`). |

Antes do primeiro `up` de cada stack:

```bash
pulumi config set classly:adminEmails "pessoa1@exemplo.com,pessoa2@exemplo.com" -s dev
pulumi config set classly:adminEmails "pessoa1@exemplo.com,pessoa2@exemplo.com" -s prod
```

O `classly:domain` do prod já está em `Pulumi.prod.yaml`.

### Primeira implantação do prod (delegação do subdomínio)

O subdomínio `classly.negoci.online` fica em uma zona Route 53 da conta da
equipe; o professor, dono de `negoci.online`, delega essa zona apontando para
os servidores de nome (NS) dela. Por isso o prod sobe em duas etapas:

1. Criar só a zona e obter os NS:
   ```bash
   pulumi up -s prod --target 'urn:pulumi:prod::Infra::aws:route53/zone:Zone::classly-zone'
   pulumi stack output name_servers -s prod
   ```
2. Enviar os quatro NS e o nome `classly.negoci.online` ao professor e
   aguardar a confirmação da delegação. Para conferir:
   ```bash
   dig +short NS classly.negoci.online
   ```
3. Implantar o restante (o certificado só é validado depois da delegação):
   ```bash
   pulumi up -s prod
   ```

A zona tem `protect=True`: se ela fosse recriada, os NS mudariam e a
delegação deixaria de funcionar. Para remover o prod mantendo a zona, use
`pulumi destroy -s prod --exclude-protected`. Uma zona Route 53 custa
US$ 0,50 por mês.

Opcionais:

```bash
pulumi config set classly:senderEmail voce@exemplo.com -s dev
pulumi config set classly:googleClientId <id> -s prod
pulumi config set --secret classly:googleClientSecret <segredo> -s prod
```

No Google Cloud Console (APIs e serviços):

1. Ative a **Google Calendar API**.
2. Na **Tela de consentimento OAuth**, inclua o escopo
   `https://www.googleapis.com/auth/calendar.readonly` e, enquanto o app
   estiver em teste, os e-mails dos professores como usuários de teste.
3. Crie um **ID do cliente OAuth** do tipo "Aplicativo da Web" com:
   - Origens JavaScript autorizadas: a `url` do stack (ex.:
     `https://classly.negoci.online`), usada pela importação da agenda;
   - URI de redirecionamento autorizado: `<login_url>/oauth2/idpresponse`,
     usado pelo login com Google.

## Execução

Pré-requisitos: credenciais AWS e `PULUMI_ACCESS_TOKEN` (ver
[README principal](../README.md#preparação-do-ambiente)), `uv` e Node.js 22
(o programa roda `npm ci` e `npm run build` em `web/` a cada execução).

```bash
cd pulumi
pulumi stack select dev   # ou prod
pulumi preview
pulumi up
```

Teste rápido após a implantação:

```bash
curl "$(pulumi stack output url)/api/health"     # 200
curl -i "$(pulumi stack output url)/api/teachers" # 401 sem token
```

Depois abra `pulumi stack output url` no navegador, crie a conta com um dos
e-mails de `classly:adminEmails` e confirme o código recebido por e-mail.

Saídas: `url` (endereço HTTPS público), `login_url`, `user_pool_id`,
`web_client_id`, `sender_email`, `api_url` (endpoint direto do API Gateway),
`cdn_domain`, `tables` e `functions`.

## Observações

- A CDN usa as políticas gerenciadas `Managed-CachingDisabled` e
  `Managed-AllViewerExceptHostHeader`: as respostas da API são dinâmicas e
  dependem de cabeçalhos como `Authorization`.
- O CloudFront só aceita certificados ACM de `us-east-1`; por isso o
  certificado usa um provider dedicado nessa região, enquanto o restante fica
  em `sa-east-1`.
- O Cognito envia os e-mails de verificação pelo remetente padrão da AWS
  (limite de 50 por dia), suficiente para o volume do projeto.
- Enquanto a conta SES estiver em sandbox, só são entregues e-mails para
  endereços verificados no SES. Para notificar qualquer professor, solicite
  acesso de produção no console do SES.
- O `config.json` publicado no bucket traz os endereços reais do Cognito; o
  arquivo de `web/public/config.json` é usado só no desenvolvimento local.
