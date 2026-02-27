import requests
from urllib.parse import urlencode, parse_qs
from dotenv import load_dotenv
import os

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

FB_OAUTH_APP_ID = os.getenv('META_APP_ID')
FB_OAUTH_APP_SECRET = os.getenv('META_APP_SECRET')

IG_OAUTH_APP_ID = os.getenv('IG_APP_ID')
IG_OAUTH_APP_SECRET = os.getenv("IG_APP_SECRET")

FB_OAUTH_SCOPES = 'instagram_basic,instagram_manage_insights,instagram_manage_comments,pages_show_list,pages_read_engagement'
IG_OAUTH_SCOPES = 'instagram_business_basic,instagram_business_manage_messages,instagram_business_manage_comments,instagram_business_content_publish,instagram_business_manage_insights'

OAUTH_REDIRECT_URI = os.getenv('REDIRECT_URI')
GRAPH_API_VERSION = 'v25.0'


### >> Generate OAuth URLs << ###

def generate_fb_oauth_url() -> str:
    params = {
        'client_id': FB_OAUTH_APP_ID,
        'redirect_uri': OAUTH_REDIRECT_URI,
        'scope': FB_OAUTH_SCOPES,
        'response_type': 'code',
        'display': 'page'
    }
    fb_oauth_url = f'https://www.facebook.com/{GRAPH_API_VERSION}/dialog/oauth?{urlencode(params)}'
    logging.info(f'URL de Autorização OAuth FB: {fb_oauth_url}')
    return fb_oauth_url

def generate_ig_oauth_url() -> str:
    params = {
        'force_reauth': 'true',
        'client_id': IG_OAUTH_APP_ID,
        'redirect_uri': OAUTH_REDIRECT_URI,
        'response_type': 'code',
        'scope': IG_OAUTH_SCOPES,
    }
    ig_oauth_url = f'https://www.instagram.com/oauth/authorize?{urlencode(params)}'
    logging.info(f'URL de Autorização OAuth IG: {ig_oauth_url}')
    return ig_oauth_url


### >> Exchange code for short lived token << ###

def oauth_code_to_short_lived_token(code: str, is_instagram_only: bool = False) -> dict | None:
    """
    Retorna dict com 'access_token' e opcionalmente 'user_id' (apenas no fluxo Instagram).
    """
    if is_instagram_only:
        base_url = 'https://api.instagram.com/oauth/access_token'
        params = {
            'client_id': IG_OAUTH_APP_ID,
            'client_secret': IG_OAUTH_APP_SECRET,
            'grant_type': 'authorization_code',
            'redirect_uri': OAUTH_REDIRECT_URI,
            'code': code,
        }
        response = requests.post(base_url, data=params)
    else:
        base_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/oauth/access_token"
        params = {
            'client_id': FB_OAUTH_APP_ID,
            'client_secret': FB_OAUTH_APP_SECRET,
            'redirect_uri': OAUTH_REDIRECT_URI,
            'code': code
        }
        response = requests.post(base_url, params=params)

    if response.status_code == 200:
        data = response.json()
        logging.info('OAuth Short-Lived Token obtido com sucesso.')
        result = {'access_token': data['access_token']}
        # O Instagram retorna user_id junto com o short-lived token
        if is_instagram_only and 'user_id' in data:
            result['user_id'] = str(data['user_id'])
        return result

    logging.error(f'Erro ao obter OAuth Short-Lived Token: {response.text}')
    return None


### >> Exchange short lived for long lived token << ###

def oauth_short_to_long_lived_token(short_tk: str, is_instagram_only: bool = False) -> str | None:
    if is_instagram_only:
        base_url = 'https://graph.instagram.com/access_token'
        params = {
            'grant_type': 'ig_exchange_token',
            'client_secret': IG_OAUTH_APP_SECRET,
            'access_token': short_tk
        }
        response = requests.get(base_url, params=params)
    else:
        base_url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/oauth/access_token"
        params = {
            'grant_type': 'fb_exchange_token',
            'client_secret': FB_OAUTH_APP_SECRET,
            'access_token': short_tk
        }
        response = requests.get(base_url, params=params)

    if response.status_code == 200:
        data = response.json()
        logging.info('OAuth Long-Lived Token obtido com sucesso.')
        return data['access_token']

    logging.error(f'Erro ao obter OAuth Long-Lived Token: {response.text}')
    return None


### >> Refresh long-lived Instagram OAuth token << ###

def refresh_ig_oauth_token(long_lived_token: str) -> str | None:
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
        logging.info(f'OAuth Token IG renovado com sucesso. Expira em: {data.get("expires_in")} segundos.')
        return data['access_token']

    logging.error(f'Erro ao renovar OAuth token IG: {response.text}')
    return None


### >> Validate OAuth token << ###

def validate_oauth_token(user_token: str) -> dict | None:
    """
    Com base na documentação https://developers.facebook.com/docs/graph-api/reference/v25.0/debug_token
    """
    base_url = f'https://graph.facebook.com/{GRAPH_API_VERSION}/debug_token'
    app_token = f"{FB_OAUTH_APP_ID}|{FB_OAUTH_APP_SECRET}"
    params = {
        'input_token': user_token,
        'access_token': app_token
    }
    response = requests.get(base_url, params=params)

    if response.status_code == 200:
        data = response.json().get('data', {})
        is_valid = data.get('is_valid', False)
        logging.info(f'Validação OAuth token: is_valid={is_valid}, expira em={data.get("expires_at")}')
        return {
            'is_valid': is_valid,
            'expires_at': data.get('expires_at'),
            'scopes': data.get('scopes', []),
            'user_id': data.get('user_id'),
        }

    logging.error(f'Erro ao validar OAuth token: {response.text}')
    return None
