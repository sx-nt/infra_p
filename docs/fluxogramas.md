# Fluxogramas do sistema

Os fluxogramas detalham os principais processos do Classly conforme os casos
de uso e as regras de negócio documentados.

## 1. Fluxograma de autenticação

```mermaid
flowchart LR
    inicio(["Início"])
    acessar["Acessar aplicação web"]
    redirecionar["Redirecionar para o provedor de autenticação"]
    autenticar["Validar credenciais"]
    credenciais{"Autenticação aprovada?"}
    negar["Negar acesso e registrar falha"]
    identificar["Identificar perfil do usuário"]
    painel{"Qual é o perfil?"}
    painelProfessor["Exibir painel do professor"]
    painelCoordenacao["Exibir painel da coordenação"]
    fim(["Fim"])

    inicio --> acessar
    acessar --> redirecionar
    redirecionar --> autenticar
    autenticar --> credenciais
    credenciais -->|"Não"| negar
    negar --> fim
    credenciais -->|"Sim"| identificar
    identificar --> painel
    painel -->|"Professor"| painelProfessor
    painelProfessor --> fim
    painel -->|"Coordenador / Administrador"| painelCoordenacao
    painelCoordenacao --> fim
```

## 2. Fluxograma de sincronização do Google Calendar

```mermaid
flowchart LR
    inicio(["Início"])
    painel["Abrir painel de disponibilidade"]
    periodo["Selecionar período"]
    autorizar["Solicitar autorização do Google Calendar"]
    permitido{"Permissão concedida?"}
    informarPermissao["Informar que a autorização é necessária"]
    consultar["Consultar eventos do período"]
    resposta{"Consulta realizada?"}
    informarFalha["Informar indisponibilidade da API"]
    eventos{"Há eventos no período?"}
    converter["Converter eventos em restrições"]
    registrarVazio["Registrar período sem eventos"]
    salvar["Salvar ou atualizar restrições"]
    resultado["Exibir resultado da sincronização"]
    fim(["Fim"])

    inicio --> painel
    painel --> periodo
    periodo --> autorizar
    autorizar --> permitido
    permitido -->|"Não"| informarPermissao
    informarPermissao --> fim
    permitido -->|"Sim"| consultar
    consultar --> resposta
    resposta -->|"Não"| informarFalha
    informarFalha --> fim
    resposta -->|"Sim"| eventos
    eventos -->|"Não"| registrarVazio
    registrarVazio --> resultado
    eventos -->|"Sim"| converter
    converter --> salvar
    salvar --> resultado
    resultado --> fim
```

## 3. Fluxograma de geração, validação e publicação

```mermaid
flowchart LR
    inicio(["Início"])
    selecionar["Selecionar semestre ou período"]
    conferirDados["Conferir dados curriculares e restrições"]
    dadosValidos{"Dados suficientes?"}
    corrigirDados["Corrigir professores, disciplinas, turmas ou restrições"]
    gerar["Gerar proposta de grade"]
    validar["Validar carga horária, habilitação e conflitos"]
    conflito{"Há conflito impeditivo?"}
    exibirConflitos["Exibir conflitos não resolvidos"]
    ajustar["Ajustar horários manualmente"]
    salvarRascunho["Salvar versão como rascunho"]
    aprovar["Aprovar grade"]
    auditar["Registrar aprovação e publicação na auditoria"]
    publicar["Publicar grade aprovada"]
    notificar["Enviar notificação aos professores"]
    consultar["Disponibilizar consulta da grade"]
    fim(["Fim"])

    inicio --> selecionar
    selecionar --> conferirDados
    conferirDados --> dadosValidos
    dadosValidos -->|"Não"| corrigirDados
    corrigirDados --> conferirDados
    dadosValidos -->|"Sim"| gerar
    gerar --> validar
    validar --> conflito
    conflito -->|"Sim"| exibirConflitos
    exibirConflitos --> ajustar
    ajustar --> validar
    conflito -->|"Não"| salvarRascunho
    salvarRascunho --> aprovar
    aprovar --> auditar
    auditar --> publicar
    publicar --> notificar
    notificar --> consultar
    consultar --> fim
```

## 4. Fluxograma de gestão da estrutura curricular

```mermaid
flowchart LR
    inicio(["Início"])
    acessar["Coordenador acessa a gestão acadêmica"]
    selecionar["Selecionar entidade"]
    entidade{"O que será gerenciado?"}
    professor["Cadastrar ou alterar professor"]
    disciplina["Cadastrar ou alterar disciplina e carga horária"]
    turma["Cadastrar ou alterar turma e período"]
    habilitacao["Associar professor à disciplina"]
    permitido{"Operação permitida?"}
    salvar["Salvar alteração"]
    auditar["Registrar alteração crítica"]
    informar["Informar falta de permissão"]
    fim(["Fim"])

    inicio --> acessar
    acessar --> selecionar
    selecionar --> entidade
    entidade -->|"Professor"| professor
    entidade -->|"Disciplina"| disciplina
    entidade -->|"Turma"| turma
    entidade -->|"Habilitação"| habilitacao
    professor --> permitido
    disciplina --> permitido
    turma --> permitido
    habilitacao --> permitido
    permitido -->|"Não"| informar
    informar --> fim
    permitido -->|"Sim"| salvar
    salvar --> auditar
    auditar --> fim
```
