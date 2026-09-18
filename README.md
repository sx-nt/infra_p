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

Detalhes de implementação, como stack tecnológica, modelo físico do banco e
contratos finais da API, devem ser adicionados quando forem definidos pelo
projeto.
