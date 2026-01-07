# Documentação

## Dependências

- Fastapi : framework web
- uvicorn : servidor ASGI(Asynchronous Server Gateway Interface)
- python-dotenv : gerenciamento de variáveis de ambiente
- pandas : manipulação e análise dos dados

## Estrutura

A estrutura do projeto visa serparar as partes ao organizar em:

- Domain : regras de dados e estruturas dos objetos
- Repositories : acesso aos dados
- Services : lógica de negócio e análises
- api : rotas e endpoints
- utils : funções ou módulos com código reutilizável

## Services

### Snapshot_services

Objetivo de processar e analisar os snapshots

Métodos:

- **calcular_engajamento_rate**:
  Calcula a taxa de engajamento.
  Fórmula: (likes + comments) / followers \* 100
  Args:
  likes: Número de curtidas
  comments: Número de comentários
  followers_count: Número de seguidores
  Se followers_count == 0, retorna 0.
  Se não, retorna a taxa de engajamento em porcentagem
