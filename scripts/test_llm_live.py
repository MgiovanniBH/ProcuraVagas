"""Test live LLM connectivity using keys from .env.

Usage:
    pwsh -c .venv\\Scripts\\python.exe scripts/test_llm_live.py
"""

from __future__ import annotations

import sys

from job_scout.config import get_settings
from job_scout.llm import get_chat_model, get_nvidia_client


def main() -> int:
    settings = get_settings()
    model_name = settings.scout_model
    print("=" * 60)
    print("Testando conexão LLM ao vivo...")
    print(f"Modelo configurado (SCOUT_MODEL): {model_name}")
    print("=" * 60)

    # 1. Test via LangChain / get_chat_model
    print("\n[1/2] Testando via LangChain (get_chat_model)...")
    try:
        model = get_chat_model(model_name, temperature=0.7)
        response = model.invoke("Diga 'Conexao com a NVIDIA API realizada com sucesso!' em portugues.")
        print(f"-> Resposta recebida:\n{response.content}\n")
    except Exception as exc:
        print(f"-> ERRO ao invocar LangChain: {type(exc).__name__}: {exc}")
        return 1

    # 2. If NVIDIA, test direct client with streaming
    if "nvidia" in model_name or settings.has_nvidia:
        print("[2/2] Testando streaming e reasoning via OpenAI Client (get_nvidia_client)...")
        try:
            client = get_nvidia_client()
            actual_model = model_name.removeprefix("nvidia:")
            completion = client.chat.completions.create(
                model=actual_model,
                messages=[{"role": "user", "content": "Gere uma frase curta motivacional em portugues do Brasil."}],
                temperature=1.0,
                top_p=0.95,
                max_tokens=1024,
                extra_body={"chat_template_kwargs": {"enable_thinking": True}, "reasoning_budget": 1024},
                stream=True,
            )

            has_reasoning = False
            content_chunks = []
            for chunk in completion:
                if not chunk.choices:
                    continue
                reasoning = getattr(chunk.choices[0].delta, "reasoning_content", None)
                if reasoning:
                    if not has_reasoning:
                        print("-> Pensamento (Thinking/Reasoning):")
                        has_reasoning = True
                    print(reasoning, end="", flush=True)
                content = chunk.choices[0].delta.content
                if content is not None:
                    content_chunks.append(content)

            if has_reasoning:
                print("\n")
            print(f"-> Resposta final (Content):\n{''.join(content_chunks)}")
        except Exception as exc:
            print(f"-> ERRO no client direto: {type(exc).__name__}: {exc}")
            return 1

    print("\n" + "=" * 60)
    print(" Sucesso! Sua chave de API e modelo estao funcionando perfeitamente.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
