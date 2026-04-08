# Lexique — Interactions avec l'API Claude

---

## `stop_reason` — Pourquoi Claude a arrêté de générer

| Valeur | Signification |
|---|---|
| `end_turn` | Claude a estimé sa réponse **complète** et s'est arrêté naturellement |
| `max_tokens` | La limite `max_tokens` a été atteinte — réponse **coupée** en plein milieu |
| `tool_use` | Claude veut appeler un outil — il attend le résultat avant de continuer (boucle manuelle uniquement) |
| `stop_sequence` | Une séquence d'arrêt personnalisée a été détectée (ex: `"###"`) |
| `pause_turn` | Streaming uniquement — tour mis en pause, peut reprendre |

> Avec le **MCP Connector natif** (claude_mcp_datagouv.py), tu ne verras jamais `tool_use` — Anthropic gère la boucle en interne et retourne directement `end_turn`.
> Avec la **boucle manuelle** (openrouter_mcp_datagouv.py), tu verras `tool_use` / `tool_calls` à chaque appel d'outil.

---

## `type` — Types de blocs dans `response.content`

| Valeur | Qui l'émet | Signification |
|---|---|---|
| `text` | Claude | Texte généré — réponse narrative, raisonnement, synthèse |
| `tool_use` | Claude | Claude veut appeler un outil classique (non-MCP) — contient `name` + `input` |
| `tool_result` | Toi (client) | Résultat d'un outil classique que tu renvoies à Claude |
| `mcp_tool_use` | Claude | Claude appelle un outil MCP — contient `name`, `server_name`, `input` |
| `mcp_tool_result` | Anthropic | Résultat de l'appel MCP — contient `content` + `is_error` |
| `thinking` | Claude | Raisonnement interne (extended thinking activé) — non affiché par défaut |

---

## `finish_reason` — Équivalent OpenAI (OpenRouter)

| Valeur | Signification |
|---|---|
| `stop` | Réponse complète, équivalent de `end_turn` |
| `tool_calls` | Le modèle veut appeler un ou plusieurs outils |
| `length` | Limite `max_tokens` atteinte, équivalent de `max_tokens` |
| `content_filter` | Réponse bloquée par un filtre de contenu |

---

## `role` — Rôles dans la conversation

| Valeur | Qui parle |
|---|---|
| `user` | Toi — questions, instructions, résultats d'outils |
| `assistant` | Claude — réponses, appels d'outils |
| `tool` | Résultat d'outil (format OpenAI/OpenRouter uniquement) |

---

## Tokens — Ce qui est compté

| Champ | Signification |
|---|---|
| `input_tokens` | Tokens consommés en entrée : system prompt + historique + outils + query |
| `output_tokens` | Tokens générés par Claude |
| `cache_read_input_tokens` | Tokens lus depuis le cache (prompt caching) — facturés moins cher |
| `cache_creation_input_tokens` | Tokens écrits dans le cache — facturés un peu plus cher à la création |

---

## Pourquoi `input_tokens` est souvent élevé

À chaque appel, Anthropic injecte automatiquement dans le contexte :
- Les descriptions de tous les outils MCP (noms, paramètres, schémas JSON)
- L'historique de la conversation
- Le system prompt (si défini)

C'est pour ça que 7400 tokens pour une simple query — la majorité vient des définitions d'outils, pas de ta question.
