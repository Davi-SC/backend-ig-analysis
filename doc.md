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

- **filtrar_posts_por_data**:
  Filtra os posts por intervalo de data.
  Args:
  posts: lista de posts
  data_inicio: data inicial no formato "YYYY-MM-DD"
  data_fim: data final no formato "YYYY-MM-DD"
  Retorna os posts filtrados
  Lógica: extrair o timestamp do post(2025-11-17T18:45:30+0000), usar um split para separar o T, se o post estiver entre as datas de inicio e final adiciona a uma lista de posts filtrados.

## Schemas

### Snapshot_schemas.py

Schema Pydantic para validação e tipificação dos dados.
Nesse schema vou utilizar a biblioteca **Pydantic** para validação de dados em tempo de execução, mais especificamente as classes: **BaseModel** que permite validação automática de tipos, conversão dos dados e tratamento de erros; **Field** para configurar cada campo do modelo, defininfo valor padrão, restrição de valores, descrição e etc.

- **Class PostInsights(BaseModel)**:
  Classe para tipagem dos insights dos posts no json. Likes, reach, saved, shares, comments e total interactions são int, o views é Optional[int] pois somente posts do tipo video tem view
- **Class PostData(BaseModel)**:
  Tipagem de todos os dados do json de posts.
  Id, url, type,caption, shortCode, timestamp e ownerUsername são strings(str). isVideo é Boolean(bool). likesCount e commentsCount são int. Insights é do tipo PostInsights, comments é uma lista de Comment Data. E por fim, Hashtags e mentions são listas de str com Field(default_factory=list). **Field(default_factory=list)** garante que cada campo seja uma lista vazia, ou seja, uma nova lista vazia para cada instancia.

  **Metodos auxiliares**:

  - caption_lenght(self) -> int : metodo para retornar o tamanho da legenda
  - hashtags_count(self) -> int : metodo para retornar a quantidade de hashtags
  - mentions_count(self) -> int : metodo para retornar a quantidade de menções

- **Class CommentData(BaseModel)**:
  Classe para tipagem dos dados de comentários de um post. id, text, username e timestamp são str, e like_count é int

- **Class ProfileData(BaseModel)**:
  Classe para tipagem dos dados do perfil do usuário. name e biography são str, website é Optional[str], mediacount, follows_count e followers_count são int.

- **Class SnapshotsData(BaseModel)**:
  Classe para tipagem dos dados especificos do snapshot. username e collected_at são str, profile é ProfileData, posts é List[PostData] e total_posts é int.

## Webhook

### domain/schemas/webhook_schemas.py

Schemas Pydantic para validação de webhooks do IG. Baseado na documentação https://developers.facebook.com/docs/instagram-platform/webhooks

- **class WebhookVerificationRequest(BaseModel)**: Modelo de requisição de verificação do webhook.
- **class WebhookChange(BaseModel)**: Modelo para a mudança no webhook.
- **class WebhookEntry(BaseModel)** : Modelo para entrada de evento do webhook
- **class Webhookpayload(BaseModel)**: Modelo para o payload completo do webhook.

### services/webhook_services.py

Processamento e validação dos eventos recebidos. Implementa validação de assinatura SHA256 e processamento assíncrono de eventos.

- **class WebhookService**: Service para gerenciar webhooks do IG

  - **validate_signature**: Valida a assinatura SHA256 do payload, a meta envia um header X-Hub-Signature-256 com o formato sha256=<hash>. O metodo recebe o Payload bruto em bytes(_payload_) e a assinatura do header X-Hub-Signature-256(_signature_) e retorna true se a assinatura for válida.
  - **process_webhook_event**: Metodo assincrono que processa os eventos de webhook
  - **\_process_entry**:processa uma entrada individual do webhook de forma assincrona.
  - **\_process_change**: processa mudança individual de forma assincrona. Recebe id da conta(account_id) e a mudança detectada(change).
  - **\_handle_comment_event**: handle para eventos de comentários, recebe account_id e um value(dicionario com os dados do comentario) Exemplo de value:
    {
    "verb": "add", # ou "edited", "removed"
    "object_id": "post-id",
    "comment_id": "comment-id",
    "text": "Nice photo!",
    "from": {"id": "user-id", "username": "username"}
    }
  - **\_handle_mention_event**: handle para eventos de menções, recebe account_id e um value(dicionario com os dados da menção). Exemplo de value:
    {
    "verb": "add",
    "media_id": "media-id",
    "comment_id": "comment-id" # onde a menção ocorreu
    }
  - **\_handle_media_event**: handle para eventos de mídia, recebe account_id e um value(dicionario com os dados da mídia). Exemplo de value:
    {
    "verb": "update",
    "media_id": "media-id"
    }
  - **\_handle_story_insights_event**: handle para eventos de insights de histórias, recebe account_id e um value(dicionario com os dados do insight). Exemplo de value:
    {
    "media_id": "media-id",
    "impressions": 1234,
    "reach": 567
    }
  - **store_webhook_payload**:armazena o payload do webhook em arquivo JSON. Recebe o payload completo e retorna o caminho salvo ou none se armazenar estiver desabilitado(store_payloads)

### utils/webhook_logger.py

-

### api/routes/webhooks.py

Rotas de API para webhooks do IG. O arquivo implementa a verificação e recebimento de eventos da Meta API.
