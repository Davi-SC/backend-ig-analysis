"""
Pacote de DAGs Airflow — Instagram Analytics ETL.

DAGs disponíveis:

    dag_instagram_etl.py
        Pipeline diário de Extract (coleta de dados) + Transform (métricas de posts).
        Schedule padrão: @daily (03:00) — altere SCHEDULE_INTERVAL no arquivo.

        Tasks de Extração:
            extract_profile >> extract_media_discovery >> extract_snapshot
            >> extract_post_insights >> extract_comments

        Tasks de Transformação (posts):
            >> transform_engagement >> transform_video_metrics >> transform_sentiment

    dag_weekly_insights.py
        Pipeline semanal de métricas de conta + crescimento de perfil.
        Schedule: domingos às 04:00 (cron: 0 4 * * 0).

        Tasks de Extração:
            extract_profile_insights   (reach, accounts_engaged, views, demographics)

        Tasks de Transformação (perfil):
            >> transform_growth        (followers_growth_7d + loyalty_rate)
            >> transform_qualification (placeholder — aguarda qualification_service 2.5)
"""
