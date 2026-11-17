# API e modelo de dados

A API REST é exposta pelo API Gateway e encaminhada a funções Lambda separadas
por domínio (`aws-sam/functions/`). Em desenvolvimento local, as funções rodam
com SAM (`aws-sam/template.yaml`) e DynamoDB Local
(`aws-sam/docker-compose.yaml`). Na nuvem, o Pulumi (`pulumi/__main__.py`)
publica as mesmas funções em um HTTP API atrás do CloudFront.

## Endereços

| Ambiente | URL base |
| --- | --- |
| Local (SAM) | `http://127.0.0.1:3000` |
| dev | `https://<distribuição>.cloudfront.net` (`pulumi stack output url -s dev`) |
| prod | `https://<classly:domain>` (`pulumi stack output url -s prod`) |

Na nuvem o CloudFront redireciona HTTP para HTTPS, não guarda respostas em
cache e repassa cabeçalhos, query string e corpo ao API Gateway. As rotas não
têm prefixo de estágio (estágio `$default`).

## Modelo DynamoDB

| Tabela | Chave primária | Chave de ordenação | Uso |
| --- | --- | --- | --- |
| `TeachersTable` | `teacherId` | — | Nome e e-mail do professor. |
| `SubjectsTable` | `subjectId` | — | Código, nome e carga horária semanal. |
| `ClassesTable` | `classId` | — | Código, período letivo e disciplina associada. |
| `QualificationsTable` | `teacherId` | `subjectId` | Habilitação do professor para lecionar a disciplina. |
| `AvailabilityTable` | `teacherId` | `availabilityId` | Intervalos semanais disponíveis ou bloqueados. `origin` pode ser `MANUAL` ou `GOOGLE`. |
| `SchedulesTable` | `scheduleId` | — | Rascunho versionado com alocações e estado. |

Os nomes acima são os usados localmente; na nuvem o Pulumi cria
`classly-<domínio>-<sufixo>` e informa o nome às funções pelas variáveis
`TEACHERS_TABLE`, `SUBJECTS_TABLE` etc.

As tabelas usam cobrança sob demanda. Horários são semanais, em dias `MON`,
`TUE`, `WED`, `THU`, `FRI`, `SAT`, `SUN`, e no formato de 24 horas `HH:MM`.

## Endpoints

Todas as rotas usam JSON. Erros de validação retornam `{ "message": "..." }`;
uma grade inválida retorna `422` com a lista `errors`.

| Método e rota | Descrição |
| --- | --- |
| `GET /health` | Verifica se a função responde. |
| `GET /teachers` e `GET /teachers/{teacherId}` | Lista professores ou consulta um professor. |
| `POST /teachers` e `PUT /teachers/{teacherId}` | Cadastra ou substitui professor (`name`, `email`; `teacherId` opcional no cadastro). |
| `DELETE /teachers/{teacherId}` | Remove professor. |
| `GET /subjects` e `GET /subjects/{subjectId}` | Lista disciplinas ou consulta uma disciplina. |
| `POST /subjects` e `PUT /subjects/{subjectId}` | Cadastra ou substitui disciplina (`code`, `name`, `weeklyHours`; `subjectId` opcional no cadastro). |
| `DELETE /subjects/{subjectId}` | Remove disciplina sem turmas associadas. |
| `GET /classes` e `GET /classes/{classId}` | Lista turmas ou consulta uma turma. |
| `POST /classes` e `PUT /classes/{classId}` | Cadastra ou substitui turma (`code`, `term`, `subjectId`; `classId` opcional no cadastro). |
| `DELETE /classes/{classId}` | Remove turma. |
| `PUT /teachers/{teacherId}/subjects/{subjectId}` | Cria/atualiza habilitação (`enabled`, padrão `true`). |
| `DELETE /teachers/{teacherId}/subjects/{subjectId}` | Remove habilitação. |
| `GET /teachers/{teacherId}/availability` | Lista restrições do professor. |
| `PUT /teachers/{teacherId}/availability` | Substitui a lista de horários: `{ "availability": [{"day":"MON","start":"08:00","end":"10:00","type":"BLOCKED","origin":"MANUAL"}] }`. `type` aceita `BLOCKED` ou `AVAILABLE`; a validação de grade considera bloqueios. |
| `POST /schedules/validate` | Valida `allocations` sem salvar a grade. |
| `POST /schedules` | Valida e salva rascunho (`term`, `allocations`). |
| `GET /schedules/{scheduleId}` | Consulta rascunho salvo. |

Cada alocação contém `classId`, `teacherId`, `subjectId`, `day`, `start` e
`end`. A validação verifica entidades existentes, disciplina da turma,
habilitação do professor, carga horária semanal e sobreposição de horários
por professor/turma, incluindo restrições bloqueadas.

## Limites desta entrega

- `origin: GOOGLE` identifica a origem dos intervalos recebidos, mas o backend
  ainda não realiza OAuth nem consulta a API Google Calendar.
- O login institucional, autorização por perfil e restrição das rotas a
  coordenadores ainda precisam de provedor/authorizer configurado. Não envie
  esta API a produção com dados reais antes de habilitar essa proteção.
- A API valida e persiste uma proposta enviada pelo cliente; ela ainda não
  calcula automaticamente uma grade, aprova/publica versões, notifica
  professores nem grava trilha de auditoria.
- As tabelas atuais não armazenam tokens de provedores externos. Integrações
  futuras devem usar armazenamento de segredos apropriado, nunca atributos
  em texto aberto.
