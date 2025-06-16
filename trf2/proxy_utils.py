import os
import logging
from dotenv import load_dotenv
import requests

load_dotenv()

API_URL_DEFAULT = "https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=3&page_size=100"
API_URL = os.getenv("WEBSHARE_PROXY_URL", API_URL_DEFAULT)
API_KEY = os.getenv("WEBSHARE_API_KEY")


def carregar_proxies(api_url: str = API_URL, api_key: str = API_KEY):
    """Fetch proxy list from Webshare API and return list of proxy URLs."""
    proxies = []
    if not api_key:
        logging.warning("WEBSHARE_API_KEY not set. No proxies will be used.")
        return proxies
    try:
        response = requests.get(api_url, headers={"Authorization": api_key})
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and "results" in data:
            data = data["results"]
        for proxy in data:
            if isinstance(proxy, dict) and proxy.get("valid"):
                ip = proxy.get("proxy_address")
                port = proxy.get("port")
                user = proxy.get("username")
                pwd = proxy.get("password")
                proxies.append(f"http://{user}:{pwd}@{ip}:{port}")
    except requests.RequestException as exc:
        logging.error(f"Erro ao buscar proxies da API: {exc}")
    return proxies
