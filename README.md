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
| [`aws-sam/`](aws-sam/README.md) | Desenvolvimento local: SAM + DynamoDB Local com as mesmas funções Lambda. |
| [`pulumi/`](pulumi/README.md) | Nuvem (stacks `dev` e `prod`): DynamoDB, Lambda, API Gateway, CloudFront, certificado ACM e registros Route 53. |
| `docker/compose/` | Experimento introdutório da disciplina com Docker Compose. |

Em ambos os stacks a API é publicada atrás do CloudFront com HTTPS
obrigatório (`navegador → CloudFront → API Gateway → Lambda → DynamoDB`). Em
`prod`, o certificado ACM é validado por DNS e o domínio aponta para a CDN por
registros alias na zona compartilhada do Route 53.

O contrato da API está em [docs/api.md](docs/api.md). Login federado, chamada
direta ao Google Calendar, algoritmo automático de geração,
aprovação/publicação com controle de acesso e notificações ficam para as
próximas sprints; a API atual aceita restrições fornecidas pelo cliente e
valida/salva rascunhos de grade.

## Preparação do ambiente

No IAM da conta AWS da equipe:

1. Criar um grupo e um usuário sem acesso ao console, associado ao grupo.
1. Associar ao grupo a política [`iam-policy.json`](iam-policy.json), que
   permite criar os papéis das funções Lambda e assumir o papel
   `route53-rr-role` da zona compartilhada.
1. Para o ambiente de **desenvolvimento**, associar também as políticas
   gerenciadas `AmazonAPIGatewayAdministrator`, `AmazonDynamoDBFullAccess_v2`,
   `AWSLambda_FullAccess`, `CloudFrontFullAccess`,
   `AWSCertificateManagerFullAccess` e `CloudWatchLogsFullAccess`.
1. Criar uma chave de acesso para o usuário.

Variáveis de ambiente (ou secrets do Codespaces): `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION=sa-east-1` e
`PULUMI_ACCESS_TOKEN`.

```bash
make install
```
