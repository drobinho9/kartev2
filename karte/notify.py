"""Obavijesti na mobitel preko Telegram bota (besplatno).

Postavljanje (jednom):
  1. U Telegramu otvori @BotFather → /newbot → dobiješ token (npr. 123456:ABC...). Upiši ga u .env kao TELEGRAM_BOT_TOKEN.
  2. Pošalji svom botu bilo koju poruku (npr. /start).
  3. `karte telegram --chat-id` ispiše tvoj chat id → upiši ga u .env kao TELEGRAM_CHAT_ID.
  4. `karte telegram --test` pošalje probnu poruku.
Za GitHub Actions oba podatka idu u Settings → Secrets and variables → Actions.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from karte.net import ProviderError, user_agent

API = "https://api.telegram.org/bot{token}/{method}"
MAX_LEN = 4000  # Telegram dopušta 4096 znakova po poruci


def _hide(text: str, token: str) -> str:
    return text.replace(token, "***") if token else text


def _call(token: str, method: str, payload: dict | None = None, timeout: float = 20.0) -> dict:
    if not token or not re.fullmatch(r"\d+:[\w-]{20,}", token.strip()):
        raise ProviderError("TELEGRAM_BOT_TOKEN nije postavljen ili nije ispravan (oblik 123456:ABC…, dobiješ ga od @BotFather).")
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(API.format(token=token.strip(), method=method), data=data,
                                 headers={"Content-Type": "application/json", "User-Agent": user_agent()})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("description", "")
        except Exception:  # noqa: BLE001
            pass
        raise ProviderError(_hide(f"Telegram {method}: HTTP {exc.code} {detail}".strip(), token)) from None
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise ProviderError(_hide(f"Telegram {method}: {exc}", token)) from None
    if not body.get("ok"):
        raise ProviderError(_hide(f"Telegram {method}: {body.get('description', 'greška')}", token))
    return body


def split_messages(blocks: list[str], limit: int = MAX_LEN) -> list[str]:
    """Spoji blokove (jedna obavijest = jedan blok) u što manje poruka do limita."""
    out: list[str] = []
    current = ""
    for block in blocks:
        block = block[:limit]
        if current and len(current) + 2 + len(block) > limit:
            out.append(current)
            current = block
        else:
            current = f"{current}\n\n{block}" if current else block
    if current:
        out.append(current)
    return out


def telegram_send(token: str, chat_id: str, text: str) -> None:
    if not chat_id:
        raise ProviderError("TELEGRAM_CHAT_ID nije postavljen – pokreni: karte telegram --chat-id")
    _call(token, "sendMessage", {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True})


def telegram_chats(token: str) -> list[tuple[str, str]]:
    """(chat id, naziv) iz zadnjih poruka botu – za otkrivanje TELEGRAM_CHAT_ID."""
    body = _call(token, "getUpdates", {"limit": 50})
    found: dict[str, str] = {}
    for upd in body.get("result") or []:
        msg = upd.get("message") or upd.get("channel_post") or upd.get("my_chat_member") or {}
        chat = msg.get("chat") or {}
        if chat.get("id") is not None:
            name = chat.get("title") or " ".join(x for x in (chat.get("first_name"), chat.get("last_name")) if x) or chat.get("username") or ""
            found[str(chat["id"])] = name
    return list(found.items())
