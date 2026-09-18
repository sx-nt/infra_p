# Diagramas de blocos

Os diagramas abaixo representam uma proposta de arquitetura AWS para o
Classly. A proposta mantém o escopo documentado: aplicação web
cliente-servidor, backend em nuvem, persistência dos dados e integrações com
autenticação, Google Calendar e provedor de e-mail.

## 1. Arquitetura AWS em blocos — MVP econômico

```mermaid
flowchart LR
    subgraph usuarios ["Usuários"]
        navegador["Navegador web"]
    end

    subgraph frontend ["Frontend AWS"]
        cloudFront["Amazon CloudFront"]
        s3["Amazon S3: frontend estático"]
    end

    subgraph backend ["Backend AWS"]
        apiGateway["Amazon API Gateway"]
        lambda["AWS Lambda: API, domínio e geração"]
    end

    subgraph dados ["Persistência AWS"]
        rds["Amazon RDS for PostgreSQL"]
    end

    subgraph observabilidade ["Operação AWS"]
        cloudWatch["Amazon CloudWatch"]
    end

    subgraph externos ["Integrações externas"]
        cognito["Amazon Cognito"]
        googleOAuth["Google OAuth"]
        googleCalendar["Google Calendar"]
        ses["Amazon SES"]
    end

    navegador -->|"HTTPS: conteúdo web"| cloudFront
    cloudFront -->|"Entrega aplicação"| s3
    navegador -->|"HTTPS: API REST"| apiGateway
    navegador -.->|"Login federado"| cognito
    cognito -.->|"IdP externo"| googleOAuth
    apiGateway -->|"Rotas autenticadas"| lambda
    lambda -->|"Lê e grava"| rds
    lambda -.->|"Importa restrições"| googleCalendar
    lambda -.->|"Envia e-mail"| ses
    lambda -.->|"Logs e métricas"| cloudWatch
```
### Serviços AWS representados

| Bloco | Serviço | Responsabilidade |
| --- | --- | --- |
| Frontend | Amazon S3 + CloudFront | Hospedar e entregar a aplicação web estática. |
| Entrada | Amazon API Gateway | Expor a API HTTPS para o frontend. |
| Autenticação | Amazon Cognito + Google OAuth | Autenticar usuários e fornecer tokens para a API. |
| Computação | AWS Lambda | Executar API, domínio, geração, validação e notificações em uma função inicial. |
| Banco | Amazon RDS for PostgreSQL | Persistir usuários, estrutura curricular, grades, alocações e auditoria. |
| E-mail | Amazon SES | Enviar a comunicação de publicação da grade. |
| Observabilidade | Amazon CloudWatch | Centralizar logs, métricas e falhas operacionais. |



## 2. Fluxo principal de geração e publicação

```mermaid
flowchart LR
    inicio(["Acesso ao sistema"])
    login["Autenticar usuário"]
    perfil{"Perfil de acesso?"}
    professorFluxo["Sincronizar agenda e consultar grade"]
    preparar["Cadastrar dados curriculares e restrições"]
    gerar["Gerar proposta de grade"]
    validar["Validar carga horária, conflitos e habilitação"]
    conflitos{"Há conflitos impeditivos?"}
    ajustar["Ajustar manualmente"]
    aprovar["Aprovar grade"]
    publicar["Publicar nova versão"]
    notificar["Notificar professores"]
    consultar["Consultar horários publicados"]

    inicio --> login
    login --> perfil
    perfil -->|"Professor"| professorFluxo
    professorFluxo --> consultar
    perfil -->|"Coordenador / Administrador"| preparar
    preparar --> gerar
    gerar --> validar
    validar --> conflitos
    conflitos -->|"Sim"| ajustar
    ajustar --> validar
    conflitos -->|"Não"| aprovar
    aprovar --> publicar
    publicar --> notificar
    notificar --> consultar
```
## 3. Ciclo de vida da grade

```mermaid
stateDiagram-v2
    direction LR

    [*] --> Rascunho
    Rascunho --> EmValidacao: enviar para validação
    EmValidacao --> Rascunho: corrigir dados ou ajustes
    EmValidacao --> Aprovada: aprovar sem conflitos impeditivos
    Aprovada --> Publicada: publicar
    Publicada --> Rascunho: abrir nova versão
    Publicada --> [*]
```

