# Infraestrutura em nuvem do Classly (Pulumi)

Programa Pulumi em Python que publica o backend do Classly na AWS. As funções
Lambda usam o mesmo código de [`aws-sam/functions`](../aws-sam/functions), que
também roda localmente com SAM + DynamoDB Local.

## Recursos

| Recurso | dev | prod |
| --- | --- | --- |
| DynamoDB: 6 tabelas sob demanda (professores, disciplinas, turmas, habilitações, disponibilidades, grades) | ✓ | ✓ (com point-in-time recovery) |
| Lambda: uma função por domínio, com papel IAM próprio restrito às tabelas que usa | ✓ | ✓ |
| CloudWatch Logs: um grupo por função, retenção de 14 dias | ✓ | ✓ |
| API Gateway (HTTP API) com as rotas de [`docs/api.md`](../docs/api.md) | ✓ | ✓ |
| CloudFront na frente da API, HTTPS obrigatório, sem cache | domínio `*.cloudfront.net` | domínio próprio |
| ACM: certificado em `us-east-1` validado por DNS | — | ✓ |
| Route 53: registro de validação e alias `A`/`AAAA` para a CDN | — | ✓ (zona compartilhada) |

O tráfego segue `navegador → CloudFront (HTTPS) → API Gateway → Lambda → DynamoDB`.

## Stacks e configuração

| Chave | Stack | Descrição |
| --- | --- | --- |
| `aws:region` | dev, prod | Região padrão (`sa-east-1`). |
| `classly:domain` | prod | Domínio público do sistema. |
| `classly:zoneId` | prod | Hosted zone do domínio no Route 53. |
| `classly:route53RoleArn` | prod | Papel assumido para gravar registros na zona, que pertence a outra conta. |
| `classly:route53ExternalId` | prod | External ID exigido pelo papel acima. |

Antes do primeiro `up` em produção:

```bash
pulumi config set classly:domain <dominio> -s prod
```

## Execução

Pré-requisitos: credenciais AWS e `PULUMI_ACCESS_TOKEN` (ver
[README principal](../README.md#preparação-do-ambiente)) e `uv`.

```bash
cd pulumi
pulumi stack select dev   # ou prod
pulumi preview
pulumi up
```

Teste rápido após a implantação:

```bash
curl "$(pulumi stack output url)/health"
curl "$(pulumi stack output url)/teachers"
```

Saídas: `url` (endereço HTTPS público), `api_url` (endpoint direto do API
Gateway), `cdn_domain`, `tables` e `functions`.

## Observações

- A CDN usa as políticas gerenciadas `Managed-CachingDisabled` e
  `Managed-AllViewerExceptHostHeader`: as respostas da API são dinâmicas e
  dependem de cabeçalhos como `Authorization`.
- O CloudFront só aceita certificados ACM de `us-east-1`; por isso o
  certificado usa um provider dedicado nessa região, enquanto o restante fica
  em `sa-east-1`.
- As rotas ainda não exigem autenticação; isso entra com Cognito na sprint de
  autenticação. Não use dados reais até lá.
