# Telegram Backup Bot

Back up messages and media from Telegram chats to a local folder and a SQLite database using the asynchronous `python-telegram-bot` API.

## Features
- Stores message meta (chat, user, text/caption, reply, timestamps) in SQLite
- Downloads media (photos, videos, documents, voice, audio, animations, stickers) to a local directory
- Simple, environment-driven configuration
- Clean SQLAlchemy schema, minimal dependencies

## Requirements
- Python 3.10+
- See `requirements.txt`

## Setup

1. **Clone & create venv**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Windows: .venv\Scripts\activate
   pip install -r requirements.txt



### 📦 About the migration
This repository was migrated as part of my Portfolio Refresh.
Originally developed locally; during migration I added README, .env.example, Docker/CI, and minor improvements.
