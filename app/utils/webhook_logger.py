"""
Utilitário de logging especializado para webhooks do Instagram.
Fornece logging estruturado e rotação de logs.
"""

import logging, sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional


def setup_webhook_logger(
    name: str = "webhook",
    log_file: Optional[str] = None,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
    log_level: int = logging.INFO
) -> logging.Logger:
    """
    Configura o logger.
    
    Args:
        name: Nome do logger
        log_file: Caminho para arquivo de log (opcional)
        max_bytes: Tamanho máximo do arquivo de log antes da rotação
        backup_count: Número de arquivos de backup a manter
        log_level: Nível de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        
    Returns:
        Logger configurado
    """
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    
    # Evitar duplicação de handlers
    if logger.handlers:
        return logger
    
    # Formato detalhado para logs
    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler para console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Handler para arquivo (se especificado)
    if log_file:
        # Criar diretório se não existir
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Handler com rotação
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def log_webhook_event(
    logger: logging.Logger,
    event_type: str,
    account_id: str,
    details: Optional[dict] = None
) -> None:
    """
    Log de um event de forma estruturada.
    
    Args:
        logger: Logger a ser utilizado
        event_type: Tipo do evento
        account_id: ID da conta do Instagram
        details: Detalhes adicionais do evento
    """
    message = f"Webhook Event - Type: {event_type}, Account: {account_id}"
    
    if details:
        # Adicionar detalhes relevantes
        if 'verb' in details:
            message += f", Action: {details['verb']}"
        if 'object_id' in details:
            message += f", Object: {details['object_id']}"
        if 'comment_id' in details:
            message += f", Comment: {details['comment_id']}"
        if 'media_id' in details:
            message += f", Media: {details['media_id']}"
    
    logger.info(message)


def log_webhook_error(
    logger: logging.Logger,
    error_type: str,
    error_message: str,
    payload: Optional[dict] = None
) -> None:
    """
    Log de erro de webhook.
    
    Args:
        logger: Logger a ser utilizado
        error_type: Tipo do erro (validation, processing, storage, etc.)
        error_message: Mensagem de erro
        payload: Payload que causou o erro
    """
    message = f"Webhook Error - Type: {error_type}, Message: {error_message}"
    
    if payload:
        # Incluir informações básicas do payload sem expor dados sensíveis
        obj_type = payload.get('object', 'unknown')
        entry_count = len(payload.get('entry', []))
        message += f", ObjectType: {obj_type}, Entries: {entry_count}"
    
    logger.error(message)


# Configuração padrão do logger de webhooks
webhook_logger = setup_webhook_logger(
    name="webhook",
    log_file="data/logs/webhooks.log",
    log_level=logging.INFO
)
