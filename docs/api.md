# API e modelo de dados

A API REST é exposta pelo API Gateway e encaminhada a funções Lambda separadas
por domínio (`aws-sam/functions/`). Em desenvolvimento local, as funções rodam
com SAM (`aws-sam/template.yaml`) e DynamoDB Local
(`aws-sam/docker-compose.yaml`). Na nuvem, o Pulumi (`pulumi/__main__.py`)
publica as mesmas funções em um HTTP API atrás do CloudFront.

A especificação completa está em [`openapi.yaml`](openapi.yaml) (OpenAPI 3.0) e
pode ser explorada no navegador em `https://classly.negoci.online/api-docs/index.html`
(Swagger UI publicado junto com o site).

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
| `SchedulesTable` | `scheduleId` | — | Grade versionada por período: alocações, estado, histórico de transições, aprovação, publicação e resultado das notificações. |
| `UsersTable` | `userId` | — | Usuário do Cognito (`sub`): e-mail, nome, perfil (`COORDINATOR`, `TEACHER`, `PENDING`) e professor vinculado. |
| `AuditTable` | `auditId` | — | Registro de operações críticas: quando, quem, ação, entidade e detalhes. O `auditId` começa pelo horário (microssegundos), o que ordena os registros. |

Os nomes acima são os usados localmente; na nuvem o Pulumi cria
`classly-<domínio>-<sufixo>` e informa o nome às funções pelas variáveis
`TEACHERS_TABLE`, `SUBJECTS_TABLE` etc.

As tabelas usam cobrança sob demanda. Horários são semanais, em dias `MON`,
`TUE`, `WED`, `THU`, `FRI`, `SAT`, `SUN`, e no formato de 24 horas `HH:MM`.

## Autenticação e perfis

Na nuvem, todas as rotas exceto `GET /health` exigem
`Authorization: Bearer <ID token do Cognito>`; o API Gateway rejeita com `401`
tokens ausentes, expirados ou de outro cliente. A função identifica o usuário
pelo `sub` do token e cria seu registro em `UsersTable` no primeiro acesso.
Localmente, `LOCAL_DEV_USER` (`aws-sam/env.json`) substitui o token.

| Perfil | Acesso |
| --- | --- |
| `COORDINATOR` | Todas as rotas. |
| `TEACHER` | Leitura de professores, disciplinas, turmas e habilitações; leitura e escrita da própria disponibilidade; leitura de grades publicadas. |
| `PENDING` | Apenas `GET /me`. |

Operações fora do perfil retornam `403`.

## Endpoints

Todas as rotas usam JSON. Erros de validação retornam `{ "message": "..." }`;
uma grade inválida retorna `422` com a lista `errors`.

| Método e rota | Descrição |
| --- | --- |
| `GET /health` | Verifica se a função responde (pública). |
| `GET /me` | Usuário autenticado, perfil e professor vinculado. |
| `GET /users` | Lista usuários (coordenação). |
| `GET /audit` | Auditoria, mais recentes primeiro; filtros `entity`, `action`, `email` e `limit` (coordenação). |
| `PUT /users/{userId}/role` | Altera o perfil (`role`) de um usuário (coordenação). |
| `GET /teachers` e `GET /teachers/{teacherId}` | Lista professores ou consulta um professor. |
| `POST /teachers` e `PUT /teachers/{teacherId}` | Cadastra ou substitui professor (`name`, `email`; `teacherId` opcional no cadastro). |
| `DELETE /teachers/{teacherId}` | Remove professor. |
| `GET /subjects` e `GET /subjects/{subjectId}` | Lista disciplinas ou consulta uma disciplina. |
| `POST /subjects` e `PUT /subjects/{subjectId}` | Cadastra ou substitui disciplina (`code`, `name`, `weeklyHours`; `subjectId` opcional no cadastro). |
| `DELETE /subjects/{subjectId}` | Remove disciplina sem turmas associadas. |
| `GET /classes` e `GET /classes/{classId}` | Lista turmas ou consulta uma turma. |
| `POST /classes` e `PUT /classes/{classId}` | Cadastra ou substitui turma (`code`, `term`, `subjectId`; `classId` opcional no cadastro). |
| `DELETE /classes/{classId}` | Remove turma. |
| `GET /qualifications` | Lista habilitações. |
| `PUT /teachers/{teacherId}/subjects/{subjectId}` | Cria/atualiza habilitação (`enabled`, padrão `true`). |
| `DELETE /teachers/{teacherId}/subjects/{subjectId}` | Remove habilitação. |
| `GET /teachers/{teacherId}/availability` | Lista restrições do professor. |
| `POST /teachers/{teacherId}/availability/google` | Importa do Google Calendar (`accessToken` com escopo `calendar.readonly`) os compromissos que se repetem nas próximas 4 semanas como bloqueios `origin: GOOGLE`, mantendo os manuais. O token não é guardado. |
| `PUT /teachers/{teacherId}/availability` | Substitui a lista de horários: `{ "availability": [{"day":"MON","start":"08:00","end":"10:00","type":"BLOCKED","origin":"MANUAL"}] }`. `type` aceita `BLOCKED` ou `AVAILABLE`; a validação de grade considera bloqueios. |
| `POST /schedules/validate` | Valida `allocations` sem salvar a grade. |
| `POST /schedules/generate` | Gera uma proposta automática para o período (`term`; opcionais `days` e `slots`), com `allocations`, `unresolved` (turmas que não couberam) e `errors`. Não salva. |
| `GET /schedules` | Lista grades (coordenação: todas; professor: publicadas). |
| `POST /schedules` | Valida e salva rascunho (`term`, `allocations`) com a próxima versão do período. |
| `GET /schedules/{scheduleId}` | Consulta uma grade (professor: só publicadas). |
| `PUT /schedules/{scheduleId}` | Ajusta as alocações de um rascunho (revalida). |
| `DELETE /schedules/{scheduleId}` | Exclui um rascunho. |
| `POST /schedules/{scheduleId}/submit` | Rascunho → Em validação (revalida). |
| `POST /schedules/{scheduleId}/approve` | Em validação → Aprovada (revalida). |
| `POST /schedules/{scheduleId}/reject` | Em validação ou Aprovada → Rascunho, com `reason`. |
| `POST /schedules/{scheduleId}/publish` | Aprovada → Publicada: revalida, arquiva a versão publicada anterior do período e envia e-mail a cada professor com seus horários (`notification`). |
| `POST /schedules/{scheduleId}/notify` | Reenvia os e-mails que falharam (ou todos, com `{"all": true}`). |

### Ciclo de vida da grade

`Rascunho (DRAFT)` → `Em validação (IN_REVIEW)` → `Aprovada (APPROVED)` →
`Publicada (PUBLISHED)` → `Arquivada (ARCHIVED)` quando uma nova versão do
mesmo período é publicada. Em validação ou aprovada, a grade pode ser
devolvida ao rascunho com um motivo. Só rascunhos podem ser ajustados ou
excluídos: a grade publicada nunca muda silenciosamente. Cada transição fica
no `history` da grade e na auditoria.

### Auditoria

Ficam registrados: logins (gatilho pós-autenticação do Cognito), primeiro
acesso e mudanças de perfil, cadastros, alterações e exclusões, importações
do Google Calendar, cada transição da grade e o resultado dos e-mails.
Tentativas recusadas por falta de token válido não chegam às funções: ficam
no log de acesso do API Gateway (CloudWatch), com status e erro do autorizador.

Cada alocação contém `classId`, `teacherId`, `subjectId`, `day`, `start` e
`end`. A validação verifica entidades existentes, disciplina da turma,
habilitação do professor, carga horária semanal e sobreposição de horários
por professor/turma, incluindo restrições bloqueadas.

## Observações

- Em sandbox, o SES só entrega e-mails a endereços verificados; a resposta da
  publicação informa cada envio que falhar, e eles podem ser reenviados.
- A importação do Google Calendar e o login com Google exigem um cliente
  OAuth configurado em `classly:googleClientId` (ver `pulumi/README.md`).
