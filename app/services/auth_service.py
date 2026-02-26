import requests
from urllib.parse import urlencode, parse_qs
from dotenv import load_dotenv
import os

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

FB_APP_ID = os.getenv('META_APP_ID')
FB_APP_SECRET = os.getenv('META_APP_SECRET')

IG_APP_ID = os.getenv('IG_APP_ID')
IG_APP_SECRET = os.getenv("IG_APP_SECRET")

FB_SCOPES = 'instagram_basic,instagram_manage_insights,instagram_manage_comments,pages_show_list,pages_read_engagement'
IG_SCOPES = 'instagram_business_basic,instagram_business_manage_messages,instagram_business_manage_comments,instagram_business_content_publish,instagram_business_manage_insights'

REDIRECT_URI = os.getenv('REDIRECT_URI')
GRAPH_API_VERSION = 'v25.0'

### >> Generate Auth URLs << ###

def generate_fb_auth_url() -> str:
    params = {
        'client_id': FB_APP_ID,
        'redirect_uri': REDIRECT_URI,
        'scope': FB_SCOPES,
        'response_type': 'code',
        'display': 'page'
    }
    fb_auth_url = f'https://www.facebook.com/{GRAPH_API_VERSION}/dialog/oauth?{urlencode(params)}'
    logging.info(f'URL de Autorização: {fb_auth_url}')
    return fb_auth_url

def generate_ig_auth_url() -> str:
    params = {
        'force_reauth': 'true',
        'client_id': IG_APP_ID,
        'redirect_uri': REDIRECT_URI,
        'response_type': 'code',
        'scope': IG_SCOPES,
    }
    ig_auth_url = f'https://www.instagram.com/oauth/authorize?{urlencode(params)}'
    logging.info(f'URL de Autorização: {ig_auth_url}')
    return ig_auth_url


### >> Exchange code for short lived token << ###

def code_to_short_lived_token(code: str, is_instagram_only: bool = False) -> str | None:
    if is_instagram_only:
        base_url = 'https://api.instagram.com/oauth/access_token'
        params = {
            'client_id': IG_APP_ID,
            'client_secret': IG_APP_SECRET,
            'grant_type': 'authorization_code',
            'redirect_uri': REDIRECT_URI,
            'code': code,
        }
        response = requests.post(base_url, data=params)
    else:
        base_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/oauth/access_token"  # FIX: era string comum, não f-string
        params = {
            'client_id': FB_APP_ID,
            'client_secret': FB_APP_SECRET,
            'redirect_uri': REDIRECT_URI,
            'code': code
        }
        response = requests.post(base_url, params=params)
    if response.status_code == 200:
        data = response.json()
        logging.info(f'Short-Lived Token obtido com sucesso.')
        return data['access_token']

    logging.error(f'Erro ao obter Short-Lived Token: {response.text}')
    return None

### >> Exchange short lived for long lived token << ###

def short_to_long_lived_token(short_tk: str, is_instagram_only: bool = False) -> str | None:
    if is_instagram_only:
        base_url = 'https://graph.instagram.com/access_token'
        params = {
            'grant_type': 'ig_exchange_token',
            'client_secret': IG_APP_SECRET,
            'access_token': short_tk
        }
        response = requests.get(base_url, params=params)
    else:
        base_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/oauth/access_token"
        params = {
            'grant_type': 'fb_exchange_token',
            'client_secret': FB_APP_SECRET,
            'access_token': short_tk
        }
        response = requests.get(base_url, params=params)

    if response.status_code == 200:
        data = response.json()
        logging.info(f'Long-Lived Token obtido com sucesso.')
        return data['access_token']

    logging.error(f'Erro ao obter Long-Lived Token: {response.text}')
    return None


### >> Refresh long-lived Instagram token (evita expiração após ~60 dias) << ###

def refresh_ig_token(long_lived_token: str) -> str | None:
    """
    Com base na documentação https://developers.facebook.com/docs/instagram-platform/reference/refresh_access_token
    """
    base_url = 'https://graph.instagram.com/refresh_access_token'
    params = {
        'grant_type': 'ig_refresh_token',
        'access_token': long_lived_token
    }
    response = requests.get(base_url, params=params)

    if response.status_code == 200:
        data = response.json()
        logging.info(f'Token IG renovado com sucesso. Expira em: {data.get("expires_in")} segundos.')
        return data['access_token']

    logging.error(f'Erro ao renovar token IG: {response.text}')
    return None


### >> Validate token (verifica se o token ainda é válido) << ###

def validate_token(user_token: str) -> dict | None:
    """
    Com base na documentação https://developers.facebook.com/docs/graph-api/reference/v25.0/debug_token
    """
    base_url = f'https://graph.facebook.com/{GRAPH_API_VERSION}/debug_token'
    params = {
        'input_token': user_token
    }
    response = requests.get(base_url, params=params)

    if response.status_code == 200:
        data = response.json().get('data', {})
        is_valid = data.get('is_valid', False)
        logging.info(f'Validação do token: is_valid={is_valid}, expira em={data.get("expires_at")}')
        return {
            'is_valid': is_valid,
            'expires_at': data.get('expires_at'),
            'scopes': data.get('scopes', []),
            'user_id': data.get('user_id'),
        }

    logging.error(f'Erro ao validar token: {response.text}')
    return None