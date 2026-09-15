# Requisitos funcionais (RF)

Este documento descreve as funcionalidades que o sistema deve oferecer para
gerenciar e publicar grades de horários.

| Código | Requisito | Critério de aceite |
| --- | --- | --- |
| **RF01** | Arquitetura web | O sistema deve funcionar como uma aplicação cliente-servidor, com frontend executado no navegador e backend disponibilizado em ambiente de nuvem. |
| **RF02** | Autenticação externa | O acesso de professores e coordenadores deve ser controlado exclusivamente por um provedor externo aprovado, como Google OAuth. |
| **RF03** | Integração com calendário | O sistema deve consultar a API do Google Calendar para identificar eventos que representem indisponibilidade de cada professor. |
| **RF04** | Gestão de dados | O sistema deve permitir o cadastro, consulta, alteração e exclusão, conforme as permissões, de professores, disciplinas, cargas horárias e turmas. |
| **RF05** | Geração de grade | O sistema deve gerar uma proposta de grade cruzando carga horária, disponibilidade, habilitação dos professores e restrições cadastradas. |
| **RF06** | Validação da grade | O sistema deve detectar e apresentar conflitos antes que a grade seja aprovada ou publicada. |
| **RF07** | Ajuste manual | O coordenador deve poder ajustar uma proposta manualmente, mantendo as validações das regras de negócio. |
| **RF08** | Aprovação e publicação | O coordenador deve poder aprovar e publicar uma grade validada, alterando seu status e disponibilizando-a para consulta. |
| **RF09** | Notificações | O sistema deve enviar e-mails ou notificações automáticas aos professores quando a grade for finalizada e aprovada. |
| **RF10** | Auditoria | O sistema deve registrar operações críticas, como aprovação da grade, publicação, exclusão de disciplinas e falhas de login. |
| **RF11** | Consulta pelo professor | O professor deve conseguir visualizar suas restrições e os horários institucionais da grade publicada. |
| **RF12** | Documentação técnica | O projeto deve disponibilizar documentação da arquitetura, da modelagem de dados e dos endpoints da API REST, preferencialmente em OpenAPI/Swagger. |

## Dados mínimos

Para gerar uma grade, o sistema deve dispor de:

- professores e seus perfis de acesso;
- disciplinas e respectivas cargas horárias semanais;
- turmas e período letivo;
- associações entre professores e disciplinas;
- blocos de horário disponíveis;
- restrições manuais e restrições sincronizadas do calendário.

## Requisitos de erro

Quando uma operação não puder ser concluída, o sistema deve informar uma
mensagem compreensível, preservar os dados já válidos e registrar o erro
quando ele estiver relacionado a uma operação crítica ou integração externa.
