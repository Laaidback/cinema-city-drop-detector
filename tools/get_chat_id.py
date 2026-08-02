"""Wypisuje TELEGRAM_CHAT_ID. Wymaga wcześniejszego napisania czegokolwiek do bota."""

import os
import sys

import requests

if __name__ == "__main__":
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit("Ustaw TELEGRAM_BOT_TOKEN przed uruchomieniem")

    updates = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=30).json()
    chats = {
        str(u["message"]["chat"]["id"]): u["message"]["chat"].get("first_name", "")
        for u in updates.get("result", [])
        if "message" in u
    }
    if not chats:
        sys.exit("Brak wiadomości. Napisz cokolwiek do swojego bota i spróbuj ponownie.")
    for chat_id, name in chats.items():
        print(f"{chat_id}  {name}")
