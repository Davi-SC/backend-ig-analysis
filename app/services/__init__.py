"""
Pacote de serviços ETL — Instagram Analytics.

Services disponíveis (serão implementados nas próximas etapas):

Extract Layer (coleta da API):
    profile_service       → busca dados estáticos do perfil → accounts
    media_discovery_service → descobre posts novos → posts
    snapshot_service      → fotografia diária → post_snapshots, account_snapshots
    comments_service      → coleta comentários e replies → comments
    insights_service      → métricas da API → post_insights, account_insights

Transform Layer (processamento interno):
    engagement_service    → calcula ER, velocity, loyalty → engagement_metrics
    sentiment_service     → análise de sentimento → atualiza comments
    qualification_service → scoring de audiência → audience_profiles
"""
