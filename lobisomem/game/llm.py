"""
Clientes de LLM com uma interface única.

O LLMAgent não sabe qual IA está do outro lado: ele só chama
`client.call_tool(system, prompt, tool)` e recebe de volta os argumentos que
o modelo passou para a ferramenta (um dict) ou None se algo deu errado.

Isso é o padrão "adapter": cada provedor tem uma API diferente, e cada classe
aqui traduz a nossa interface simples para a API dele.

    AnthropicClient → API do Claude (precisa de ANTHROPIC_API_KEY)
    OllamaClient    → modelo rodando no seu computador (precisa do Ollama aberto)
    FakeClient      → para testes; não chama nenhuma IA
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolSpec:
    """Uma "ferramenta" que o modelo pode chamar, descrita com JSON Schema."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema de um objeto


class LLMClient(Protocol):
    def call_tool(self, system: str, prompt: str, tool: ToolSpec) -> dict[str, Any] | None:
        """Pede ao modelo que chame `tool`. Devolve os argumentos, ou None em caso de falha."""
        ...


# --------------------------------------------------------------------------- #
# Claude (API da Anthropic)
# --------------------------------------------------------------------------- #

# Modelos que aceitam o fallback automático do servidor: se o modelo recusar
# um pedido por política de segurança, a API tenta de novo com outro modelo
# dentro da mesma chamada.
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}


class AnthropicClient:
    def __init__(self, model: str = "claude-opus-5-5", effort: str = "low", max_tokens: int = 4000) -> None:
        import anthropic  # importado aqui para os testes não dependerem do pacote

        self._anthropic = anthropic
        try:
            self.client = anthropic.Anthropic()  # lê ANTHROPIC_API_KEY do ambiente
        except TypeError as exc:  # o SDK levanta TypeError quando não acha credenciais
            raise RuntimeError(
                "Nenhuma chave da API da Anthropic encontrada. Copie o .env.example para .env "
                "e preencha ANTHROPIC_API_KEY (ou use LLM_PROVIDER=ollama)."
            ) from exc
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens

    def call_tool(self, system: str, prompt: str, tool: ToolSpec) -> dict[str, Any] | None:
        tool_param = {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.parameters,
            # strict: a API garante que os argumentos seguem o schema
            # (inclusive o enum com os nomes válidos de jogadores).
            "strict": True,
        }
        kwargs: dict[str, Any] = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            tools=[tool_param],
            # "effort" controla o quanto o modelo pensa antes de responder.
            # Para um jogo de conversa, "low" é rápido e barato.
            output_config={"effort": self.effort},
        )
        if self.model in _FALLBACK_MODELS:
            kwargs.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")

        a = self._anthropic
        try:
            response = self.client.beta.messages.create(**kwargs)
        except a.AuthenticationError:
            logger.error("ANTHROPIC_API_KEY ausente ou inválida.")
            raise  # erro de configuração: melhor parar do que jogar no aleatório
        except a.RateLimitError:
            logger.warning("Limite de requisições atingido; jogada aleatória no lugar.")
            return None
        except (a.APIStatusError, a.APIConnectionError) as exc:
            logger.warning("Falha na API do Claude: %s", exc)
            return None

        if response.stop_reason == "refusal":
            logger.warning("O modelo recusou o pedido.")
            return None
        for block in response.content:
            if block.type == "tool_use" and block.name == tool.name:
                return dict(block.input)
        return None  # o modelo respondeu sem chamar a ferramenta


# --------------------------------------------------------------------------- #
# Ollama (modelo local)
# --------------------------------------------------------------------------- #


class OllamaClient:
    """
    Fala com o Ollama pela API HTTP local (http://localhost:11434/api/chat).
    Usa só a biblioteca padrão do Python, sem dependências extras.
    """

    def __init__(self, model: str = "llama3.1", url: str = "http://localhost:11434", timeout: float = 120) -> None:
        self.model = model
        self.url = url.rstrip("/")
        self.timeout = timeout

    def call_tool(self, system: str, prompt: str, tool: ToolSpec) -> dict[str, Any] | None:
        body = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {"name": tool.name, "description": tool.description, "parameters": tool.parameters},
                }
            ],
        }
        request = urllib.request.Request(
            f"{self.url}/api/chat",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                data = json.load(resp)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            logger.warning("Falha ao chamar o Ollama: %s", exc)
            return None

        for call in data.get("message", {}).get("tool_calls") or []:
            fn = call.get("function", {})
            if fn.get("name") == tool.name:
                args = fn.get("arguments")
                # Alguns modelos devolvem os argumentos como string JSON.
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        return None
                return args if isinstance(args, dict) else None
        return None


# --------------------------------------------------------------------------- #
# Fake (testes)
# --------------------------------------------------------------------------- #


@dataclass
class FakeClient:
    """
    Cliente de mentira para testes. `responder` recebe (system, prompt, tool)
    e devolve os argumentos. Guarda todas as chamadas em `calls` para que os
    testes possam inspecionar o prompt que foi montado.
    """

    responder: Callable[[str, str, ToolSpec], dict[str, Any] | None]
    calls: list[tuple[str, str, ToolSpec]] = field(default_factory=list)

    def call_tool(self, system: str, prompt: str, tool: ToolSpec) -> dict[str, Any] | None:
        self.calls.append((system, prompt, tool))
        return self.responder(system, prompt, tool)


# --------------------------------------------------------------------------- #
# Fábrica
# --------------------------------------------------------------------------- #


def get_client() -> LLMClient:
    """Cria o cliente a partir das configurações do Django (settings.py / .env)."""
    from django.conf import settings

    provider = settings.LLM_PROVIDER
    if provider == "anthropic":
        return AnthropicClient(model=settings.LLM_MODEL or "claude-opus-5-5", effort=settings.LLM_EFFORT)
    if provider == "ollama":
        return OllamaClient(model=settings.LLM_MODEL or "llama3.1", url=settings.OLLAMA_URL)
    raise ValueError(f"LLM_PROVIDER desconhecido: {provider!r} (use 'anthropic' ou 'ollama').")
