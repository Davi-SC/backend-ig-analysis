# Instagram Analytics — Backend API

Pipeline ELT de dados do Instagram com FastAPI, Apache Airflow e MongoDB Atlas.

Desenvolvido como parte de pesquisa PIBIC sobre métricas de engajamento em perfis Instagram Business.

---

## Índice

1. [Visão Geral](#visão-geral)
2. [Arquitetura](#arquitetura)
3. [Pré-requisitos](#pré-requisitos)
4. [Configuração do Ambiente](#configuração-do-ambiente)
5. [Executando o Projeto](#executando-o-projeto)
6. [Pipeline ELT](#pipeline-elt)
7. [Endpoints da API](#endpoints-da-api)
8. [Collections do MongoDB](#collections-do-mongodb)
9. [Métricas Calculadas](#métricas-calculadas)
10. [Estrutura de Arquivos](#estrutura-de-arquivos)
11. [Fluxo de Autenticação OAuth](#fluxo-de-autenticação-oauth)

---

## Visão Geral

O backend é responsável por:

- **Autenticar** perfis Instagram Business via OAuth 2.0 (Meta Graph API)
- **Coletar** posts, snapshots diários, insights de posts, comentários e métricas de perfil
- **Transformar** dados brutos em métricas analíticas de engajamento
- **Orquestrar** o pipeline ELT com Apache Airflow (coleta diária e semanal)
- **Expor** dados processados via FastAPI para consumo do frontend

### Stack técnica

| Componente | Tecnologia |
|------------|-----------|
| API REST | FastAPI + Uvicorn |
| Orquestração ELT | Apache Airflow 2.x |
| Banco de Dados | MongoDB Atlas |
| Driver Python MongoDB | PyMongo |
| Fonte de dados | Meta Graph API v25.0 |
| Runtime | Python 3.11+ |

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Meta Graph API v25.0                         │
└────────────────────────────┬────────────────────────────────────────┘
                             │ HTTPS / OAuth 2.0
              ┌──────────────▼──────────────┐
              │          Backend             │
              │                              │
              │  ┌─────────────────────────┐ │
              │  │       FastAPI             │ │  ← /oauth, /collect,
              │  │   (Uvicorn server)       │ │    /data, /analytics
              │  └───────────┬─────────────┘ │
              │              │               │
              │  ┌───────────▼─────────────┐ │
              │  │    Apache Airflow        │ │
              │  │   DAG diário  DAG semanal│ │
              │  │   (ELT)       (insights) │ │
              │  └───────────┬─────────────┘ │
              │              │               │
              │  ┌───────────▼─────────────┐ │
              │  │      Services Layer      │ │
              │  │  profile │ media │ snap  │ │
              │  │  insights│ comments      │ │
              │  │  engagement│ growth      │ │
              │  └───────────┬─────────────┘ │
              │              │               │
              │  ┌───────────▼─────────────┐ │
              │  │    MongoRepository       │ │
              │  │   (singleton global)     │ │
              │  └───────────┬─────────────┘ │
              └──────────────┼───────────────┘
                             │ PyMongo
              ┌──────────────▼──────────────┐
              │         MongoDB Atlas        │
              │   social-data-lab cluster    │
              └─────────────────────────────┘
```

### Fluxo de dados

```
Login OAuth
    └─→ /oauth/fb/save ou /oauth/callback
         └─→ oauth_tokens (MongoDB)

Coleta inicial (POST /collect/initial)
    ├─→ profile_service      → ig_profiles
    ├─→ media_discovery      → posts
    ├─→ snapshot_service     → profile_snapshots + post_snapshots
    ├─→ insights_service     → post_insights
    ├─→ comments_service     → comments
    ├─→ engagement_service   → engagement_metrics
    └─→ video_metrics        → (post_insights com campos de vídeo)

Airflow @daily (dag_instagram_elt)
    [Extract + Load — dados brutos]
    ├─→ extract_load_profile          → ig_profiles (refresh)
    ├─→ extract_load_media_discovery  → posts (novos posts)
    ├─→ extract_load_snapshot         → profile_snapshots + post_snapshots
    ├─→ extract_load_post_insights    → post_insights
    ├─→ extract_load_comments         → comments
    [Transform — lê do MongoDB, grava em coleções derivadas]
    ├─→ transform_engagement          → engagement_metrics
    └─→ transform_video_metrics       → engagement_metrics (vídeos)

Airflow @weekly (dag_weekly_insights)
    ├─→ extract_load_profile_insights → profile_insights
    └─→ transform_growth              → profile_snapshots (campo growth — ⚠️ exceção ELT)
```

---

## Pré-requisitos

- Python 3.11 ou superior
- Conta no [MongoDB Atlas](https://cloud.mongodb.com) (cluster gratuito M0 é suficiente)
- App registrado no [Meta for Developers](https://developers.facebook.com)
  - Produto: **Instagram Basic Display API** ou **Instagram Business Login**
  - Permissões: `instagram_basic`, `instagram_manage_insights`, `instagram_manage_comments`, `pages_show_list`, `pages_read_engagement`
- Apache Airflow 2.x instalado localmente (`pip install apache-airflow`)

---

## Configuração do Ambiente

### 1. Clone o repositório

```bash
git clone <repo-url>
cd backend-ig-analysis
```

### 2. Crie e ative o ambiente virtual

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Configure o `.env`

Copie o arquivo de exemplo e preencha as variáveis:

```bash
cp .env.example .env
```

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `META_APP_ID` | App ID do app Meta (Facebook Login) | `859402103106794` |
| `META_APP_SECRET` | App Secret do app Meta | `28688f7...` |
| `IG_APP_ID` | App ID para Instagram Business Login | `1346553...` |
| `IG_APP_SECRET` | App Secret para Instagram Business Login | `adc6321...` |
| `REDIRECT_URI` | URI de callback para fluxo Instagram | `https://seu-dominio.com/dashboard` |
| `FB_REDIRECT_URI` | URI de callback para fluxo Facebook | `https://seu-dominio.com/auth/fb/callback` |
| `MONGO_URI` | URI de conexão MongoDB Atlas | `mongodb+srv://user:pass@cluster.mongodb.net/` |
| `DB_NAME` | Nome do banco de dados MongoDB | `social-data-lab` |
| `WEBHOOK_VERIFY_TOKEN` | Token de verificação do webhook Meta | qualquer string secreta |
| `AIRFLOW_HOME` | Diretório home do Airflow | `C:/Users/seu-usuario/airflow` |

> **Segurança:** nunca comite o `.env` com credenciais reais. O `.gitignore` já está configurado para excluí-lo.

### 5. Configure o Airflow

```bash
# Inicializa o banco de dados do Airflow
airflow db init

# Copia os DAGs para o diretório do Airflow
cp app/dags/*.py $AIRFLOW_HOME/dags/

# Cria as variáveis necessárias
airflow variables set ig_profile_id <seu-profile-id>

# Cria a conexão MongoDB
airflow connections add mongo_default \
  --conn-type mongo \
  --conn-host "mongodb+srv://..." \
  --conn-schema social-data-lab
```

---

## Executando o Projeto

### Iniciar a API FastAPI

```bash
uvicorn app.main:app --reload --port 8000
```

Acesse a documentação interativa em: **http://localhost:8000/docs**

### Iniciar o Airflow

```bash
# Em dois terminais separados:
airflow webserver --port 8080   # Interface web do Airflow
airflow scheduler               # Orquestrador de tarefas

# Ou com o modo standalone (desenvolvimento):
airflow standalone
```

Interface Airflow: **http://localhost:8080**

### Rodar um DAG manualmente (sem Airflow)

```bash
python -c "
from app.services.media_discovery_service import run_media_discovery_service
result = run_media_discovery_service('<seu-profile-id>')
print(result)
"
```

---

## Pipeline ELT

O sistema segue o padrão **ELT** (Extract → Load → Transform): os dados são extraídos da
Meta Graph API e carregados **brutos** no MongoDB; as transformações rodam depois, lendo do
próprio MongoDB e gravando em coleções derivadas (`engagement_metrics`, `audience_qualification`).

### DAG Diário — `dag_instagram_elt`

Executado diariamente (`@daily`). Extrai/carrega dados brutos e transforma métricas de posts.

```
extract_load_profile
  → extract_load_media_discovery
  → extract_load_snapshot
  → extract_load_post_insights
  → extract_load_comments
  → transform_engagement
  → transform_video_metrics
```

| Task | Service | Descrição |
|------|---------|-----------|
| `extract_load_profile` | `profile_service` | Atualiza dados básicos do perfil (followers, bio, nome) |
| `extract_load_media_discovery` | `media_discovery_service` | Descobre novos posts via `/me/media` |
| `extract_load_snapshot` | `snapshot_service` | Snapshot diário de followers + likes/comments por post |
| `extract_load_post_insights` | `insights_service` | Métricas lifetime de cada post (reach, saves, shares) |
| `extract_load_comments` | `comments_service` | Coleta comentários de todos os posts |
| `transform_engagement` | `engagement_service` | Calcula métricas de ER, velocidade, amplification |
| `transform_video_metrics` | `video_metrics_service` | Métricas específicas de Reels (watch_time, play_count) |

### DAG Semanal — `dag_weekly_insights`

Executado toda segunda-feira às 03:00 UTC. Coleta métricas de conta e crescimento.

```
extract_load_profile_insights
    └─→ transform_growth
```

| Task | Service | Descrição |
|------|---------|-----------|
| `extract_load_profile_insights` | `insights_service` | Métricas do perfil (reach, accounts_engaged, demográficos) |
| `transform_growth` | `growth_service` | Calcula crescimento de seguidores nos últimos 7 dias |

> [!WARNING]
> **Exceção ao padrão ELT (débito técnico conhecido):** o `growth_service` grava o resultado
> no campo `growth` **dentro de `profile_snapshots`**, que é uma coleção de dados brutos.
> As demais transformações gravam em coleções próprias.
>
> **Melhoria futura:** criar a coleção `growth_metrics` (índice único `(profile_id, date)`),
> trocar o `update_one` por upsert nela, ajustar as rotas que leem `profile_snapshots.growth`
> e migrar/remover os campos `growth` antigos. Detalhes em `app/services/growth_service.py`.

---

## Endpoints da API

A documentação completa e interativa está disponível em `/docs` (Swagger UI) quando o servidor estiver rodando.

### OAuth — `/oauth`

> Não requerem `X-Profile-ID`. Gerenciam o ciclo de autenticação OAuth.

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `GET` | `/oauth/fb/url` | Gera URL de autorização OAuth do Facebook |
| `GET` | `/oauth/ig/url` | Gera URL de autorização OAuth do Instagram |
| `GET` | `/oauth/callback` | Troca o `code` OAuth por long-lived token |
| `POST` | `/oauth/fb/save` | Salva token do fluxo Facebook implicit |
| `GET` | `/oauth/validate` | Valida se um token ainda é válido via `/debug_token` |
| `GET` | `/oauth/refresh` | Renova um long-lived token do Instagram |

### Coleta On-demand — `/collect`

> Requerem header `X-Profile-ID`. Permitem disparar a coleta manualmente.

| Método | Endpoint | Descrição |
|--------|----------|-----------|
| `POST` | `/collect/initial` | Pipeline completo: perfil → posts → snapshots → insights → comentários → engajamento |
| `POST` | `/collect/refresh` | Atualização rápida: snapshots → insights → engajamento (sem redescoberta de posts) |

**Exemplo de resposta:**
```json
{
  "status": "ok",
  "profile_id": "17841400000000000",
  "steps": [
    { "service": "profile_service", "status": "ok", "message": "Perfil atualizado" },
    { "service": "media_discovery_service", "status": "ok", "message": "47 posts descobertos" },
    { "service": "engagement_service", "status": "ok", "message": "42 posts com métricas calculadas" }
  ],
  "message": "Coleta completa: 7/7 etapas concluídas com sucesso."
}
```

### Dados Brutos — `/data`

> Requerem header `X-Profile-ID`.

| Método | Endpoint | Parâmetros | Descrição |
|--------|----------|-----------|-----------|
| `GET` | `/data/profile` | — | Dados estáticos do perfil (username, followers, bio) |
| `GET` | `/data/snapshots` | `days=30` | Série temporal de followers/media_count |
| `GET` | `/data/posts` | `limit=20` | Lista de posts com último snapshot inline |
| `GET` | `/data/engagement/{post_id}` | — | Histórico completo de engagement_metrics do post |
| `GET` | `/data/insights/account` | `limit=12` | Profile insights semanais (reach, demographics) |
| `GET` | `/data/comments/{post_id}` | `limit=50` | Comentários de um post específico |

### Analytics — `/analytics`

> Requerem header `X-Profile-ID`. Retornam agregações computadas via MongoDB pipelines.

| Método | Endpoint | Parâmetros | Descrição |
|--------|----------|-----------|-----------|
| `GET` | `/analytics/top-posts` | `metric=er_simple`, `limit=10` | Ranking de posts pela métrica escolhida |
| `GET` | `/analytics/best-hours` | — | Melhores horários por ER Simples médio |
| `GET` | `/analytics/by-format` | — | Engajamento médio por tipo de mídia |
| `GET` | `/analytics/engagement-trend` | `days=30` | Série temporal de ER Simples médio diário |

**Métricas disponíveis para `top-posts`:**
`er_simple`, `er_reach`, `er_followers`, `er_views`, `amplification_rate`, `relative_reach`

**Exemplo de resposta — `/analytics/best-hours`:**
```json
{
  "profile_id": "17841400000000000",
  "count": 8,
  "data": [
    { "hour": 19, "avg_er_simple": 0.041230, "post_count": 7 },
    { "hour": 12, "avg_er_simple": 0.038450, "post_count": 5 },
    { "hour": 8,  "avg_er_simple": 0.031100, "post_count": 3 }
  ]
}
```

### Autenticação

Todos os endpoints de `/collect`, `/data` e `/analytics` requerem o header:

```
X-Profile-ID: <profile_id>
```

O `profile_id` é retornado pelo backend após o fluxo OAuth. O `access_token` **nunca** é enviado ao frontend — ele fica armazenado apenas no MongoDB (collection `oauth_tokens`).

---

## Collections do MongoDB

### `oauth_tokens`
Token de acesso OAuth do perfil. Gerenciado pelo `oauth_service`.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `profile_id` | String (unique) | ID do usuário Instagram |
| `username` | String | Nome de usuário no Instagram |
| `long_lived_token` | String (unique) | Token de longa duração (~60 dias) |
| `auth_method` | String | `"instagram"` ou `"facebook"` |
| `is_valid` | Boolean | Flag de validade do token |
| `expires_at` | DateTime | Data de expiração do token |
| `created_at` | DateTime | Data de criação |

### `ig_profiles`
Dados estáticos do perfil Instagram. Atualizado diariamente pelo `profile_service`.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `profile_id` | String (unique) | ID do usuário Instagram |
| `username` | String | Nome de usuário |
| `name` | String | Nome de exibição |
| `biography` | String | Biografia do perfil |
| `followers_count` | Int | Número de seguidores |
| `follows_count` | Int | Número de contas seguidas |
| `media_count` | Int | Total de posts publicados |
| `profile_picture_url` | String | URL da foto de perfil |
| `website` | String | Link do site na bio |
| `collected_at` | DateTime | Data/hora da última coleta |

### `profile_snapshots`
Série temporal diária do perfil. Índice único: `(profile_id, date)`.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `profile_id` | String | ID do perfil |
| `date` | String (ISO) | Data do snapshot (YYYY-MM-DD) |
| `followers_count` | Int | Seguidores neste dia |
| `follows_count` | Int | Seguindo neste dia |
| `media_count` | Int | Total de posts neste dia |
| `growth` | Object | Crescimento 7d (preenchido pelo weekly DAG — ⚠️ dado derivado em coleção bruta, ver exceção ELT) |
| `growth.followers_growth_7d` | Int | Delta absoluto de seguidores (7 dias) |
| `growth.followers_growth_7d_pct` | Float | Delta percentual de seguidores |
| `growth.media_growth_7d` | Int | Posts publicados na semana |

### `posts`
Metadados imutáveis dos posts. Write-once na primeira descoberta.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `post_id` | String (unique) | ID do post na API do Instagram |
| `profile_id` | String | ID do perfil dono do post |
| `media_type` | String | `IMAGE`, `CAROUSEL_ALBUM` ou `VIDEO` |
| `caption` | String | Legenda do post |
| `permalink` | String | URL pública do post |
| `thumbnail_url` | String | URL da thumbnail |
| `published_at` | DateTime | Data/hora de publicação |
| `discovered_at` | DateTime | Data/hora da primeira descoberta pelo ELT |

### `post_snapshots`
Série temporal diária de cada post. Índice único: `(post_id, date)`.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `post_id` | String | ID do post |
| `profile_id` | String | ID do perfil |
| `date` | String (ISO) | Data do snapshot |
| `like_count` | Int | Curtidas neste dia |
| `comments_count` | Int | Comentários neste dia |
| `collected_at` | DateTime | Timestamp da coleta |

### `post_insights`
Métricas de lifetime de cada post (append-only). Cresce diariamente para análise de curva de crescimento.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `post_id` | String | ID do post |
| `profile_id` | String | ID do perfil |
| `media_type` | String | Tipo de mídia |
| `collected_at` | DateTime | Timestamp da coleta |
| `reach` | Int | Contas únicas que viram o post |
| `saved` | Int | Saves no post |
| `shares` | Int | Compartilhamentos |
| `total_interactions` | Int | Likes + Comments + Saves + Shares |
| `views` | Int | Total de visualizações (substitui impressions desde v22) |
| `ig_reels_avg_watch_time` | Float | Tempo médio de visualização (Reels) |
| `ig_reels_video_view_total_time` | Int | Tempo total assistido (Reels) |

### `comments`
Comentários dos posts. Insert-only com deduplicação por `comment_id`.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `comment_id` | String (unique) | ID do comentário |
| `post_id` | String | ID do post pai |
| `profile_id` | String | ID do perfil dono do post |
| `text` | String | Texto do comentário |
| `username` | String | Autor do comentário |
| `timestamp` | DateTime | Data/hora do comentário |
| `replies` | Array | Replies embutidas |

### `engagement_metrics`
Métricas calculadas pelo `engagement_service`. Índice único: `(post_id, date)`.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `post_id` | String | ID do post |
| `profile_id` | String | ID do perfil |
| `date` | String (ISO) | Data do cálculo |
| `er_simple` | Float | Taxa de engajamento simples |
| `er_reach` | Float | Taxa de engajamento por alcance |
| `er_followers` | Float | Total de interações / seguidores |
| `er_views` | Float | Total de interações / views |
| `relative_reach` | Float | Alcance / seguidores |
| `amplification_rate` | Float | Shares / alcance |
| `velocity_likes_24h` | Int | Delta de likes em 24h |
| `velocity_comments_24h` | Int | Delta de comentários em 24h |
| `days_since_published` | Int | Dias desde a publicação |
| `calculated_at` | DateTime | Timestamp do cálculo |

### `profile_insights`
Métricas semanais do perfil. Índice único: `(profile_id, period_until)`.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `profile_id` | String | ID do perfil |
| `period_since` | String (ISO) | Início do período |
| `period_until` | String (ISO) | Fim do período |
| `reach` | Int | Contas únicas alcançadas |
| `accounts_engaged` | Int | Contas que interagiram |
| `views` | Int | Visualizações do perfil |
| `profile_views` | Int | Visualizações da página de perfil |
| `total_interactions` | Int | Total de interações |
| `follows_and_unfollows` | Int | Saldo de follows (somente fluxo Facebook) |
| `audience_country` | Object | Distribuição de seguidores por país |
| `audience_city` | Object | Distribuição por cidade |
| `audience_age` | Object | Distribuição por faixa etária |
| `audience_gender` | Object | Distribuição por gênero |

---

## Métricas Calculadas

Todas as métricas são calculadas pelo `engagement_service` com base nos dados coletados.

### Taxa de Engajamento (ER)

| Métrica | Fórmula | Referência |
|---------|---------|-----------|
| `er_simple` | `(likes + comments) / followers` | Fórmula clássica de engajamento |
| `er_reach` | `total_interactions / reach` | Engajamento relativo ao alcance real |
| `er_followers` | `total_interactions / followers` | Total de interações por seguidor |
| `er_views` | `total_interactions / views` | Engajamento por visualização (Hootsuite) |

> `total_interactions` = likes + comments + saves + shares

### Alcance e Difusão

| Métrica | Fórmula | Interpretação |
|---------|---------|--------------|
| `relative_reach` | `reach / followers` | % dos seguidores que viram o post |
| `amplification_rate` | `shares / reach` | Taxa de e-WOM — conteúdo repassado |

### Velocidade de Engajamento

| Métrica | Descrição |
|---------|-----------|
| `velocity_likes_24h` | Delta de curtidas entre ontem e hoje |
| `velocity_comments_24h` | Delta de comentários entre ontem e hoje |
| `days_since_published` | Dias desde a publicação do post |

---

## Estrutura de Arquivos

```
backend-ig-analysis/
├── app/
│   ├── api/
│   │   └── routes/
│   │       ├── analytics.py      # GET /analytics/* (agregações)
│   │       ├── collect.py        # POST /collect/initial, /collect/refresh
│   │       ├── data.py           # GET /data/* (dados brutos)
│   │       ├── oauth.py          # GET|POST /oauth/* (autenticação)
│   │       └── webhooks.py       # POST /webhook (Meta webhook)
│   ├── config/
│   │   ├── cors_config.py        # Configuração de CORS
│   │   └── settings.py           # Leitura de variáveis de ambiente
│   ├── dags/
│   │   ├── dag_instagram_elt.py  # DAG diário (posts + engajamento)
│   │   └── dag_weekly_insights.py# DAG semanal (insights de perfil)
│   ├── domain/
│   │   └── schemas/
│   │       └── oauth_schemas.py  # Pydantic schemas para OAuth
│   ├── repositories/
│   │   └── mongo_repository.py   # Singleton de acesso ao MongoDB
│   ├── services/
│   │   ├── comments_service.py   # Coleta de comentários
│   │   ├── engagement_service.py # Cálculo de métricas de engajamento
│   │   ├── growth_service.py     # Crescimento de seguidores (semanal)
│   │   ├── insights_service.py   # Post insights + Profile insights
│   │   ├── media_discovery_service.py # Descoberta de posts
│   │   ├── oauth_service.py      # Gerenciamento de tokens OAuth
│   │   ├── profile_service.py    # Coleta de dados do perfil
│   │   ├── sentiment_service.py  # [Desabilitado] Análise de sentimento
│   │   ├── snapshot_service.py   # Snapshots diários
│   │   └── video_metrics_service.py # Métricas de Reels/vídeos
│   ├── utils/
│   │   ├── auth.py               # FastAPI Dependency (X-Profile-ID)
│   │   └── webhook_logger.py     # Logger de payloads do webhook
│   └── main.py                   # Ponto de entrada FastAPI
├── .env                          # Variáveis de ambiente (não commitar!)
├── .env.example                  # Template das variáveis
├── requirements.txt              # Dependências Python
└── README.md                     # Este arquivo
```

---

## Fluxo de Autenticação OAuth

### Fluxo Instagram Business Login (recomendado)

```
1. Frontend chama GET /oauth/ig/url
   └─→ Backend gera URL de autorização com IG_APP_ID + escopos

2. Usuário autoriza no Instagram → redirect para REDIRECT_URI?code=...

3. Frontend passa o code para GET /oauth/callback?code=...&is_instagram_only=true
   ├─→ Backend troca code por short-lived token (Graph API)
   ├─→ Backend troca short-lived por long-lived token (~60 dias)
   ├─→ Backend busca profile_id e username na Graph API
   ├─→ Backend salva em oauth_tokens (MongoDB)
   └─→ Retorna { user_id: "...", access_token: "..." } (token NÃO vai para sessionStorage)

4. Frontend salva apenas o profile_id em sessionStorage
   └─→ Todas as chamadas subsequentes usam X-Profile-ID: {profile_id}
```

### Fluxo Facebook Login

```
1. Frontend chama GET /oauth/fb/url
   └─→ Redireciona usuário ao Facebook

2. Facebook retorna token no hash da URL → FbCallback.js processa

3. FbCallback chama POST /oauth/fb/save com { access_token, user_id, username }
   └─→ Backend salva em oauth_tokens

4. FbCallback salva profile_id em sessionStorage (token NÃO persiste no cliente)
```

### Segurança

- O `long_lived_token` **nunca** é enviado ao frontend após o OAuth
- O frontend autentica chamadas usando apenas o `profile_id` (header `X-Profile-ID`)
- O backend valida o `profile_id` consultando `oauth_tokens` a cada requisição
- Tokens expirados retornam HTTP 401 com mensagem para refazer o login
