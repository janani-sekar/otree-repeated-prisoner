import requests  
from pprint import pprint

GET = requests.get
POST = requests.post

DEV_SERVER_URL = 'http://localhost:8000'
PROD_SERVER_URL = 'https://repeated-prisoners-dilemma-1914240aa313.herokuapp.com/'
REST_KEY = 'repeatedpd2025'  

def call_api(method, *path_parts, **params) -> dict:
    path_parts = '/'.join(path_parts)
    url = f'{PROD_SERVER_URL}/api/{path_parts}/'
    resp = method(url, json=params, headers={'otree-rest-key': REST_KEY})
    if not resp.ok:
        msg = (
            f'Request to "{url}" failed '
            f'with status code {resp.status_code}: {resp.text}'
        )
        raise Exception(msg)
    return resp.json()

data = call_api(GET, 'otree_version')
data = call_api(GET, 'session_configs')
data = call_api(GET, 'rooms')
try:
    data = call_api(
        POST,
        'sessions',
        session_config_name='prolific_study',
        room_name='Prolific_1',
        num_participants=250,
    )
    pprint(data)
except Exception as e:
    print(f"Error: {e}")
