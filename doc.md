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

### Snapshot_services.py

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

## Schemas

### Snapshot_schemas.py

Schema Pydantic para validação e tipificação dos dados.
Nesse schema vou utilizar a biblioteca **Pydantic** para validação de dados em tempo de execução, mais especificamente as classes: **BaseModel** que permite validação automática de tipos, conversão dos dados e tratamento de erros; **Field** para configurar cada campo do modelo, defininfo valor padrão, restrição de valores, descrição e etc.

- **Class PostInsights(BaseModel)**:
  Classe para tipagem dos insights dos posts no json. Likes, reach, saved, shares, comments e total interactions são int, o views é Optional[int] pois somente posts do tipo video tem view
- **Class PostData(BaseModel)**:
  Tipagem de todos os dados do json de posts.
  Id, url, type,caption, shortCode, timestamp e ownerUsername são strings(str). isVideo é Boolean(bool). likesCount e commentsCount são int. Insights é do tipo PostInsights, comments é uma lista de Comment Data. E por fim, Hashtags e mentions são listas de str com Field(default_factory=list).

  **Field(default_factory=list)** garante que cada campo seja uma lista vazia, ou seja, uma nova lista vazia para cada instancia.

  **Metodos auxiliares**:

  - caption_lenght(self) -> int : metodo para retornar o tamanho da legenda
  - hashtags_count(self) -> int : metodo para retornar a quantidade de hashtags
  - mentions_count(self) -> int : metodo para retornar a quantidade de menções

- **Class CommentData(BaseModel)**:
  Classe para tipagem dos dados de comentários de um post. id, text, username e timestamp são str, e like_count é int

- **Class ProfileData(BaseModel)**:
  Classe para tipagem dos dados do perfil do usuário. name e biography são str, website é Optional[str], mediacount, follows_count e followers_count são int.

- **Class SnapshotsData(BaseModel)**:
