# Requisitos não funcionais (RNF)

Este documento define atributos de qualidade, operação e infraestrutura que o
sistema deve atender além das funcionalidades descritas nos requisitos
funcionais.

| Código | Categoria | Requisito | Critério de aceite |
| --- | --- | --- | --- |
| **RNF01** | Responsividade | O frontend deve funcionar em monitores desktop e dispositivos móveis. | Os fluxos principais devem permanecer utilizáveis sem rolagem horizontal ou perda de informação nos tamanhos de tela suportados. |
| **RNF02** | Desempenho | O backend deve responder com baixa latência e o algoritmo deve processar a geração de forma eficiente. | Consultas, índices e processamento devem ser monitorados e testados com uma carga representativa do projeto. |
| **RNF03** | Custos | A arquitetura em nuvem deve priorizar baixo custo, free tiers, recursos sob demanda ou arquitetura serverless quando adequados. | Os recursos utilizados devem possuir estimativa de custo e limites configurados para evitar consumo inesperado. |
| **RNF04** | Ambientes | Desenvolvimento e produção devem ser isolados. | Credenciais, bancos, variáveis e dados de teste não devem ser compartilhados com produção. |
| **RNF05** | Infraestrutura como código | O provisionamento de banco, aplicação e demais recursos deve ser automatizado por IaC, como Terraform ou CloudFormation. | Um ambiente novo deve poder ser reproduzido a partir dos arquivos versionados e de variáveis documentadas. |
| **RNF06** | CI/CD | O pipeline deve executar verificações automatizadas e implantar versões estáveis em produção. | Pull requests e implantações devem executar testes, validações e registrar o resultado do processo. |
| **RNF07** | Segurança | Tokens, credenciais e dados sensíveis não devem ser armazenados no código ou no repositório. | Segredos devem ser fornecidos por variáveis protegidas ou gerenciador de segredos, e o acesso deve seguir o princípio do menor privilégio. |
| **RNF08** | Disponibilidade e recuperação | Falhas de integração ou serviço não devem corromper grades já salvas. | Operações críticas devem ser transacionais quando possível e possuir logs suficientes para recuperação ou reprocessamento. |
| **RNF09** | Observabilidade | O sistema deve registrar erros, operações críticas e falhas de integrações externas. | Logs devem conter contexto suficiente para diagnóstico, sem expor tokens ou dados sensíveis desnecessários. |
| **RNF10** | Manutenibilidade | Código, configurações e documentação devem ser versionados e organizados de forma consistente. | Mudanças relevantes devem incluir testes ou atualização da documentação correspondente. |

## Segurança e privacidade

O sistema deve solicitar somente os escopos necessários do Google Calendar,
proteger tokens de acesso, limitar as informações exibidas por perfil e evitar
que dados de um professor sejam expostos a outro usuário sem autorização.

## Ambientes mínimos

- **Desenvolvimento:** usado para implementação, testes e dados não produtivos.
- **Produção:** usado pelos usuários finais, com credenciais, banco e
  configurações isolados do ambiente de desenvolvimento.
