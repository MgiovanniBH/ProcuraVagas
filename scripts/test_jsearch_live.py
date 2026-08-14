"""Test live JSearch API connectivity using JSEARCH_API_KEY from .env.

Usage:
    pwsh -c .venv\\Scripts\\python.exe scripts/test_jsearch_live.py
"""

from __future__ import annotations

import json
import sys

import requests

from job_scout.config import get_settings


def main() -> int:
    settings = get_settings()
    api_key = settings.jsearch_api_key.get_secret_value()

    print("=" * 60)
    print("Testando conexão ao vivo com a API JSearch (RapidAPI)...")
    print("=" * 60)

    if not api_key:
        print("\n[ERRO] JSEARCH_API_KEY não foi encontrada no seu arquivo .env!")
        print("Adicione a chave no arquivo .env:")
        print("JSEARCH_API_KEY=sua-chave-do-rapidapi-aqui\n")
        return 1

    print(f"-> Chave detectada: {api_key[:6]}...{api_key[-4:] if len(api_key) > 10 else ''}")

    # 1. Test using RapidAPI endpoint (as per user specification)
    url = "https://jsearch.p.rapidapi.com/search-v2"
    querystring = {
        "query": "developer jobs in chicago",
        "num_pages": "1",
        "country": "us",
        "date_posted": "all",
    }
    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": "jsearch.p.rapidapi.com",
        "Content-Type": "application/json",
    }

    print(f"\n[1/2] Enviando requisição GET para {url}...")
    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=15)
        print(f"-> Status Code HTTP: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            jobs = data.get("data", [])
            print(f"-> Sucesso! Total de vagas retornadas: {len(jobs)}")
            if jobs:
                print("\nExemplo da primeira vaga encontrada:")
                first = jobs[0] if isinstance(jobs, list) else jobs.get("jobs", [{}])[0]
                print(f"  - Título: {first.get('job_title')}")
                print(f"  - Empresa: {first.get('employer_name')}")
                print(f"  - Local: {first.get('job_city')}, {first.get('job_country')}")
                print(f"  - Link: {first.get('job_apply_link')}")
            print("\nResposta completa (JSON truncado):")
            print(json.dumps(data, indent=2)[:500] + "\n...")
        elif response.status_code == 401 or response.status_code == 403:
            print("-> [ERRO DE AUTENTICAÇÃO] A chave fornecida foi rejeitada pelo RapidAPI.")
            print(f"Detalhes: {response.text}")
            return 1
        elif response.status_code == 429:
            print("-> [LIMITE EXCEDIDO] Cota de requisições do RapidAPI esgotada para esta chave (HTTP 429).")
            print(f"Detalhes: {response.text}")
            return 1
        else:
            print(f"-> Resposta com erro: {response.text}")
            return 1

    except Exception as exc:
        print(f"\n-> ERRO na requisição: {type(exc).__name__}: {exc}")
        return 1

    print("\n" + "=" * 60)
    print(" Conexão com JSearch / RapidAPI validada com sucesso!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
