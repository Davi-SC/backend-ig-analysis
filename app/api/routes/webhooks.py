"""
Rotas de API para webhooks do Instagram.
Implementa verificação e recebimento de eventos da Meta.
"""

import os
from fastapi import APIRouter, Request, Response, HTTPException, Query, status
from typing import Dict, Any
import logging

from app.domain.schemas.webhook_schemas import WebhookPayload
from app.services.webhook_service import WebhookService
from app.utils.webhook_logger import webhook_logger, log_webhook_event, log_webhook_error

# Configurar logger
logger = logging.getLogger(__name__)

# Criar router
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# Inicializar serviço de webhook
webhook_service = None


def get_webhook_service() -> WebhookService:
    """
    Obtém a instância do serviço de webhook.
    Inicializa na primeira chamada com variáveis de ambiente.
    """
    global webhook_service
    
    if webhook_service is None:
        app_secret = os.getenv("META_APP_SECRET")
        store_payloads = os.getenv("WEBHOOK_STORE_PAYLOADS", "true").lower() == "true"
        
        if not app_secret:
            raise ValueError("META_APP_SECRET não configurado nas variáveis de ambiente")
        
        webhook_service = WebhookService(
            app_secret=app_secret,
            store_payloads=store_payloads
        )
    
    return webhook_service


@router.get("/instagram", summary="Verificação de webhook", status_code=200)
async def verify_webhook(
    hub_mode: str = Query(..., alias="hub.mode", description="Modo de operação (sempre 'subscribe')"),
    hub_challenge: str = Query(..., alias="hub.challenge", description="Challenge a ser retornado"),
    hub_verify_token: str = Query(..., alias="hub.verify_token", description="Token de verificação")
) -> Response:
    """
    Endpoint de verificação do webhook.
    
    A Meta envia uma requisição GET para verificar se o endpoint está configurado corretamente.
    Este endpoint deve:
    1. Validar que hub.verify_token corresponde ao token configurado
    2. Retornar hub.challenge se válido
    3. Retornar erro 403 se inválido
    
    Documentação: https://developers.facebook.com/docs/instagram-platform/webhooks#verification-requests
    
    Args:
        hub_mode: Modo da requisição (sempre "subscribe")
        hub_challenge: Valor a ser retornado
        hub_verify_token: Token para validação
        
    Returns:
        Response com hub.challenge em texto plano
        
    Raises:
        HTTPException: 403 se o token de verificação não corresponder
    """
    try:
        # Obter token configurado
        verify_token = os.getenv("WEBHOOK_VERIFY_TOKEN")
        
        if not verify_token:
            webhook_logger.error("WEBHOOK_VERIFY_TOKEN não configurado")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Configuração de webhook incompleta"
            )
        
        # Validar token
        if hub_verify_token != verify_token:
            webhook_logger.warning(
                f"Token de verificação inválido. Esperado: {verify_token[:5]}..., "
                f"Recebido: {hub_verify_token[:5]}..."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token de verificação inválido"
            )
        
        # Validar modo
        if hub_mode != "subscribe":
            webhook_logger.warning(f"Modo de hub inválido: {hub_mode}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Modo de hub inválido"
            )
        
        webhook_logger.info(f"Verificação de webhook bem-sucedida. Challenge: {hub_challenge}")
        
        # Retornar challenge em texto plano
        return Response(content=hub_challenge, media_type="text/plain")
        
    except HTTPException:
        raise
    except Exception as e:
        webhook_logger.error(f"Erro na verificação do webhook: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro interno ao verificar webhook"
        )


@router.post("/instagram", summary="Receber eventos de webhook", status_code=200)
async def receive_webhook(request: Request) -> Dict[str, str]:
    """
    Endpoint para receber notificações de eventos do Instagram.
    
    A Meta envia requisições POST quando eventos ocorrem (comentários, menções, etc.).
    Este endpoint deve:
    1. Validar a assinatura SHA256 no header X-Hub-Signature-256
    2. Processar o evento de forma assíncrona
    3. Armazenar o payload (se configurado)
    4. Retornar 200 OK imediatamente
    
    Documentação: https://developers.facebook.com/docs/instagram-platform/webhooks#event-notifications
    
    Args:
        request: Objeto Request do FastAPI contendo o payload e headers
        
    Returns:
        Dicionário com status de sucesso
        
    Raises:
        HTTPException: 403 se a assinatura for inválida
    """
    try:
        # Obter payload bruto e headers
        body = await request.body()
        signature = request.headers.get("X-Hub-Signature-256", "")
        
        webhook_logger.info("Recebendo evento de webhook do Instagram")
        
        # Validar assinatura
        service = get_webhook_service()
        
        if signature and not service.validate_signature(body, signature):
            log_webhook_error(
                webhook_logger,
                "validation",
                "Assinatura SHA256 inválida"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Assinatura inválida"
            )
        
        # Parse do JSON
        payload_dict = await request.json()
        
        # Validar estrutura com Pydantic
        try:
            payload = WebhookPayload(**payload_dict)
        except Exception as e:
            log_webhook_error(
                webhook_logger,
                "validation",
                f"Estrutura de payload inválida: {e}",
                payload_dict
            )
            # Ainda retornamos 200 OK para evitar reenvios
            return {"status": "accepted", "warning": "payload structure invalid"}
        
        # Armazenar payload
        if service.store_payloads:
            await service.store_webhook_payload(payload_dict)
        
        # Logar informações básicas
        for entry in payload.entry:
            for change in entry.changes:
                log_webhook_event(
                    webhook_logger,
                    event_type=change.field,
                    account_id=entry.id,
                    details=change.value
                )
        
        # Processar evento de forma assíncrona
        await service.process_webhook_event(payload)
        
        webhook_logger.info("Evento de webhook processado com sucesso")
        
        # Sempre retornar 200 OK rapidamente
        return {"status": "received"}
        
    except HTTPException:
        raise
    except Exception as e:
        # Logar erro mas ainda retornar 200 OK para evitar reenvios
        log_webhook_error(
            webhook_logger,
            "processing",
            f"Erro ao processar webhook: {e}"
        )
        webhook_logger.error(f"Erro ao processar webhook: {e}", exc_info=True)
        
        # Retornar 200 OK mesmo com erro para evitar que a Meta reenvie
        # O erro foi logado e pode ser investigado
        return {"status": "error", "message": "internal processing error"}


# ==================== ENDPOINT DE TESTE (OPCIONAL) ====================
# Útil para testar o endpoint localmente sem precisar da Meta

@router.post("/instagram/test", summary="Testar endpoint de webhook (desenvolvimento)", include_in_schema=True)
async def test_webhook(payload: Dict[str, Any]) -> Dict[str, str]:
    """
    Endpoint de teste para desenvolvimento.
    Permite testar o processamento de webhooks sem validação de assinatura.
    
    Args:
        payload: Payload de teste no formato do webhook
        
    Returns:
        Status do processamento
    """
    try:
        # Validar estrutura
        webhook_payload = WebhookPayload(**payload)
        
        # Obter serviço
        service = get_webhook_service()
        
        # Armazenar payload de teste
        if service.store_payloads:
            await service.store_webhook_payload(payload)
        
        # Processar evento
        await service.process_webhook_event(webhook_payload)
        
        return {"status": "test_successful"}
        
    except Exception as e:
        logger.error(f"Erro no teste de webhook: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Erro ao processar payload de teste: {str(e)}"
        )
