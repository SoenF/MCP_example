"""
OpenRouter + MCP datagouv — boucle agentique manuelle
=====================================================
OpenRouter ne supporte pas le MCP Connector natif d'Anthropic.
On gère donc la boucle nous-mêmes :
  1. Connexion au serveur MCP → liste des outils
  2. Conversion MCP tools → format OpenAI function-calling
  3. Appel LLM → si tool_calls → exécution MCP → loop
  4. Jusqu'à finish_reason == "stop"

Modèles gratuits recommandés sur OpenRouter :
  - meta-llama/llama-3.3-70b-instruct:free  (meilleur tool calling)
  - mistralai/mistral-small-3.1-24b-instruct:free
  - google/gemma-3-27b-it:free

Usage :
    python openrouter_mcp_datagouv.py
    python openrouter_mcp_datagouv.py "Cherche des données sur le chômage"
"""

import asyncio
import json
import logging
import os
import sys
from typing import Any

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from openai import OpenAI

load_dotenv()

# ─────────────────────────── Config ────────────────────────────

DATAGOUV_MCP_URL = "https://mcp.data.gouv.fr/mcp"
MODEL = "meta-llama/llama-3.3-70b-instruct:free"
MAX_TOKENS = 4096
MAX_TURNS = 10  # garde-fou contre les boucles infinies

DEFAULT_QUERY = (
    "Cherche des datasets sur la qualité de l'air en France. "
    "Donne-moi les 3 plus pertinents avec leur description et leur organisation."
)

# ─────────────────────────── Logging ───────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

DIVIDER = "─" * 70


# ─────────────────────────── Helpers ───────────────────────────

def _truncate(text: str, max_len: int = 400) -> str:
    return text if len(text) <= max_len else text[:max_len] + "…"


def _mcp_tool_to_openai(tool: Any) -> dict:
    """Convertit un outil MCP (ListToolsResult) en format OpenAI function calling."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema or {"type": "object", "properties": {}},
        },
    }


# ─────────────────────────── Core ──────────────────────────────

async def run(query: str) -> str:
    log.info(DIVIDER)
    log.info("  OpenRouter + datagouv MCP (boucle manuelle)")
    log.info(DIVIDER)
    log.info(f"  Model      : {MODEL}")
    log.info(f"  MCP server : {DATAGOUV_MCP_URL}")
    log.info(f"  Query      : {query}")
    log.info(DIVIDER)

    # ── Connexion MCP (session unique pour tout le run) ──────────
    async with streamablehttp_client(DATAGOUV_MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            log.info("  [MCP] Session initialisée")

            # ── Découverte des outils ────────────────────────────
            tools_result = await session.list_tools()
            openai_tools = [_mcp_tool_to_openai(t) for t in tools_result.tools]
            tool_names = [t.name for t in tools_result.tools]
            log.info(f"  [MCP] {len(tool_names)} outils disponibles : {tool_names}")
            log.info(DIVIDER)

            # ── Initialisation des messages ──────────────────────
            messages: list[dict] = [{"role": "user", "content": query}]
            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=os.environ["OPENROUTER_API_KEY"],
            )

            final_text = ""

            # ── Boucle agentique ─────────────────────────────────
            for turn in range(1, MAX_TURNS + 1):
                log.info(f"  [TURN {turn}][→ LLM] messages en cours : {len(messages)}")

                response = client.chat.completions.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    messages=messages,
                    tools=openai_tools,
                    tool_choice="auto",
                )

                choice = response.choices[0]
                msg = choice.message
                finish = choice.finish_reason

                log.info(
                    f"  [TURN {turn}][← LLM] finish_reason={finish!r}  "
                    f"prompt_tokens={response.usage.prompt_tokens}  "
                    f"completion_tokens={response.usage.completion_tokens}"
                )

                if msg.content:
                    log.info(f"  [TURN {turn}][← LLM TEXT] {_truncate(msg.content)}")
                    final_text = msg.content

                # Ajouter la réponse du LLM au contexte
                messages.append(msg.model_dump(exclude_unset=False))

                # ── Fin de la boucle ─────────────────────────────
                if finish == "stop" or not msg.tool_calls:
                    log.info(f"  [TURN {turn}] Fin de la boucle agentique.")
                    break

                # ── Exécution des appels d'outils ────────────────
                for tc in msg.tool_calls:
                    fn_name = tc.function.name
                    fn_args = json.loads(tc.function.arguments)

                    log.info(f"  [TURN {turn}][→ MCP CALL ] tool={fn_name!r}")
                    log.info(f"               args={json.dumps(fn_args, ensure_ascii=False)}")

                    mcp_result = await session.call_tool(fn_name, fn_args)

                    # Extraire le texte du résultat MCP
                    result_content = ""
                    if mcp_result.content:
                        first = mcp_result.content[0]
                        result_content = (
                            first.text if getattr(first, "type", "") == "text"
                            else json.dumps(first, default=str)
                        )

                    is_error = getattr(mcp_result, "isError", False)
                    status = "ERROR" if is_error else "OK"
                    log.info(f"  [TURN {turn}][← MCP RESULT] tool={fn_name!r}  status={status}")
                    log.info(f"               {_truncate(result_content, 300)}")

                    # Retourner le résultat au LLM
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result_content,
                    })

            else:
                log.warning(f"  Limite de {MAX_TURNS} tours atteinte.")

    log.info(DIVIDER)
    return final_text


# ─────────────────────────── Entry point ───────────────────────

if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else DEFAULT_QUERY
    answer = asyncio.run(run(query))
    print("\n" + "=" * 70)
    print("RÉPONSE FINALE")
    print("=" * 70)
    print(answer)
