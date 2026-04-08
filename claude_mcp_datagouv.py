"""
Claude API + MCP Connector natif → data.gouv.fr
================================================
Claude gère la boucle outil <-> MCP côté serveur Anthropic.
Le beta header `mcp-client-2025-11-20` active le feature.

Usage :
    python claude_mcp_datagouv.py
    python claude_mcp_datagouv.py "Cherche des données sur le chômage en France"
"""

import json
import logging
import os
import sys
from typing import Any

import anthropic
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────── Config ────────────────────────────

DATAGOUV_MCP_URL = "https://mcp.data.gouv.fr/mcp"
MODEL = "claude-opus-4-6"
MAX_TOKENS = 4096

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


def _log_content_block(block: Any) -> None:
    """Logge chaque bloc de contenu de la réponse avec son type."""
    btype = getattr(block, "type", "unknown")

    if btype == "text":
        log.info(f"  [← LLM TEXT] {_truncate(block.text)}")

    elif btype == "mcp_tool_use":
        log.info(f"  [→ MCP CALL ] tool={block.name!r}  server={block.server_name!r}")
        log.info(f"               input={json.dumps(block.input, ensure_ascii=False)}")

    elif btype == "mcp_tool_result":
        content_text = ""
        if block.content:
            first = block.content[0]
            content_text = first.text if getattr(first, "type", "") == "text" else repr(first)
        status = "ERROR" if getattr(block, "is_error", False) else "OK"
        log.info(f"  [← MCP RESULT] id={block.tool_use_id}  status={status}")
        log.info(f"               {_truncate(content_text, 300)}")

    else:
        log.info(f"  [BLOCK] type={btype}")


# ─────────────────────────── Core ──────────────────────────────

def run(query: str) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    log.info(DIVIDER)
    log.info("  Claude API + datagouv MCP Connector")
    log.info(DIVIDER)
    log.info(f"  Model      : {MODEL}")
    log.info(f"  MCP server : {DATAGOUV_MCP_URL}")
    log.info(f"  Query      : {query}")
    log.info(DIVIDER)

    log.info("  [→ LLM] Envoi de la requête…")

    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": query}],
        mcp_servers=[
            {
                "type": "url",
                "url": DATAGOUV_MCP_URL,
                "name": "datagouv",
                # Pas de token requis pour data.gouv.fr (serveur public)
            }
        ],
        tools=[
            {
                "type": "mcp_toolset",
                "mcp_server_name": "datagouv",
            }
        ],
        betas=["mcp-client-2025-11-20"],
    )

    log.info(DIVIDER)
    log.info(f"  [← LLM] stop_reason={response.stop_reason!r}  "
             f"input_tokens={response.usage.input_tokens}  "
             f"output_tokens={response.usage.output_tokens}")
    log.info(DIVIDER)

    # Le connector gère la boucle MCP en interne ; tous les blocs
    # (tool_use, tool_result, text final) arrivent dans response.content
    for block in response.content:
        _log_content_block(block)

    final_text = "\n\n".join(
        block.text for block in response.content
        if getattr(block, "type", "") == "text"
    )

    log.info(DIVIDER)
    return final_text


# ─────────────────────────── Entry point ───────────────────────

if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else DEFAULT_QUERY
    answer = run(query)
    print("\n" + "=" * 70)
    print("RÉPONSE FINALE")
    print("=" * 70)
    print(answer)
