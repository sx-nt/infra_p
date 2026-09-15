# Regras de negócio (RN)

As regras de negócio definem as restrições e condições lógicas que o sistema
deve respeitar durante o cadastro, a geração e a publicação das grades.

| Código | Regra | Descrição |
| --- | --- | --- |
| **RN01** | Limite de carga horária | Uma disciplina deve ser alocada exatamente conforme sua carga horária semanal configurada. A grade não pode ficar abaixo ou acima desse total. |
| **RN02** | Conflito de agendas | Um professor não pode ser alocado para duas turmas ou disciplinas diferentes no mesmo bloco de horário. |
| **RN03** | Respeito às restrições | O algoritmo não pode alocar uma aula em um horário marcado como ocupado ou restrito pelo professor, seja por integração com o Google Calendar ou por bloqueio manual. |
| **RN04** | Perfil de acesso | Apenas usuários com perfil de Coordenador/Administrador podem gerar, editar ou aprovar a grade final. |
| **RN05** | Autenticação institucional | Professores e administradores devem se autenticar usando o provedor externo aprovado pela instituição, como uma conta Google. |
| **RN06** | Professor habilitado | Uma disciplina só pode ser atribuída a um professor associado e habilitado para lecioná-la. |
| **RN07** | Integridade da publicação | Apenas uma grade validada e aprovada pode ser publicada para consulta dos professores. |
| **RN08** | Rastreabilidade | Aprovações, publicações, exclusões e alterações críticas devem registrar usuário, data, operação e entidade afetada. |

## Prioridade das regras

As regras de conflito, indisponibilidade e permissão são impeditivas: caso uma
delas seja violada, o sistema deve impedir a gravação ou publicação da grade e
informar o motivo ao coordenador.

## Critérios de validação

Antes da aprovação, o sistema deve verificar pelo menos:

- a carga horária total de cada disciplina;
- conflitos de professor no mesmo bloco;
- conflitos com restrições manuais e eventos sincronizados;
- existência de professor habilitado para cada disciplina;
- permissão do usuário que está executando a operação.
