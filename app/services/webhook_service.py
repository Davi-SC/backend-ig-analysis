"""
Service para processar e validar eventos de webhook do Instagram.
Implementa validação de assinatura SHA256 e processamento assincrono dos events
"""

from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime
import logging, hashlib, hmac
import json


from app.domain.schemas.webhook_schemas import WebhookVerificationRequest, WebhookPayload, WebhookEntry, WebhookChange

#configurar logger
logger = logging.getLogger(__name__)

class WebhookService:
    
    def __init__(self, app_secret: str, store_payloads:bool=True):
        self.app_secret = app_secret
        self.store_payloads = store_payloads
        self.storage_path = Path("data/webhooks")
        
        if not self.storage_path.exists():
            self.storage_path.mkdir(parents=True, exist_ok=True)
    
    def validate_signature(self, payload: bytes, signature: str) -> bool:
        try:
            if signature.startswith("sha256="):
                signature = signature[7:]
            
            expected_signature = hmac.new(
                key = self.app_secret.encode('utf-8'),
                msg = payload,
                digestmod = hashlib.sha256
            ).hexdigest()

            is_valid = hmac.compare_digest(expected_signature, signature)
            
            if not is_valid:
                logger.warning("Assinatura de webhook invalida")
            
            return is_valid

        except Exception as e:
            logger.error(f"Erro ao validar assinatura: {e}")
            return False
        
    async def _process_entry(self, entry: WebhookEntry) -> None:
        logger.info(f"Processando entrada para a conta ID: {entry.id}")

        for change in entry.changes:
            await self._process_change(change)

    async def _process_change(self, change: WebhookChange, account_id: str) -> None:
        field = change.field
        value = change.value
        
        logger.info(f"Processando mudança no campo '{field}' para conta {account_id}")
        
        # Exemplos de processamento por tipo de evento (pode expandir conforme necessidade)
        
        if field == "comments":
            await self._handle_comment_event(account_id, value)
        elif field == "mentions":
            await self._handle_mention_event(account_id, value)
        elif field == "media":
            await self._handle_media_event(account_id, value)
        elif field == "story_insights":
            await self._handle_story_insights_event(account_id, value)
        else:
            logger.info(f"Tipo de evento não processado: {field}")

#                      Handle de eventos                      #

    async def _handle_comment_event(self, account_id: str, value: Dict[str, Any]) -> None:
        verb = value.get("verb")
        comment_id = value.get("comment_id")
        text = value.get("text", "")
        
        logger.info(f"Comentário {verb}: {comment_id} - {text[:50]}...")
        
        # TODO: Implementar lógica customizada, como:
        # - Salvar comentário no banco de dados
        # - Enviar notificação
        # - Análise de sentimento
        # - Moderação automática
        pass

    async def _handle_mention_event(self, account_id: str, value: Dict[str, Any]) -> None:
        media_id = value.get("media_id")
        logger.info(f"Menção detectada na mídia: {media_id}")
        
        # TODO: Implementar lógica customizada
        # Exemplos:
        # - Notificar sobre menção
        # - Coletar informações da mídia mencionada
        # - Rastrear menções da marca
        pass
    
    async def _handle_media_event(self, account_id: str, value: Dict[str, Any]) -> None:
        media_id = value.get("media_id")
        logger.info(f"Atualização de mídia: {media_id}")
        
        # TODO: Implementar lógica customizada
        # Exemplos:
        # - Buscar detalhes da nova mídia via API
        # - Atualizar cache local
        # - Iniciar coleta de insights
        pass
    
    async def _handle_story_insights_event(self, account_id: str, value: Dict[str, Any]) -> None:
        media_id = value.get("media_id")
        impressions = value.get("impressions")
        reach = value.get("reach")
        
        logger.info(f"Story insights - Mídia: {media_id}, Impressões: {impressions}, Alcance: {reach}")
        
        # TODO: Implementar lógica customizada
        # Exemplos:
        # - Salvar métricas em banco de dados
        # - Atualizar dashboard em tempo real
        # - Gerar alertas para performance alta/baixa
        pass
    
#                      Armazenamento                      #
    
    async def store_webhook_payload(self, payload: Dict[str, Any]) -> Optional[str]:
        if not self.store_payloads:
            return None
        
        try:
            # Gerar nome do arquivo com timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            event_type = payload.get("object", "unknown")
            
            # Tentar identificar o tipo específico do primeiro evento
            if "entry" in payload and len(payload["entry"]) > 0:
                first_entry = payload["entry"][0]
                if "changes" in first_entry and len(first_entry["changes"]) > 0:
                    field = first_entry["changes"][0].get("field", "unknown")
                    event_type = f"{event_type}_{field}"
            
            filename = f"webhook_{timestamp}_{event_type}.json"
            filepath = self.storage_path / filename
            
            # Salvar payload em JSON
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Payload armazenado em: {filepath}")
            return str(filepath)
            
        except Exception as e:
            logger.error(f"Erro ao armazenar payload: {e}")
            return None