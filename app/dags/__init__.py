"""
Pacote de DAGs Airflow — Instagram Analytics ETL.

Cada DAG corresponde a uma fase do pipeline ETL:

Extract DAGs (coleta da API do Instagram):
    dag_daily_snapshot.py    -> roda diariamente às 03:00
    dag_media_discovery.py   -> roda diariamente às 02:00
    dag_comments.py          -> roda diariamente às 04:00
    dag_post_insights.py     -> roda diariamente às 05:00
    dag_account_insights.py  -> roda semanalmente (domingo às 03:00)

Transform DAGs (processamento interno):
    dag_engagement_processing.py -> após dag_daily_snapshot
    dag_sentiment_processing.py  -> após dag_comments
    dag_qualification.py         -> semanal (domingo às 06:00)
"""
