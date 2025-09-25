import os
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

from sqlalchemy import (
    create_engine, Column, Integer, BigInteger, String, Text, DateTime, Boolean
)
from sqlalchemy.orm import declarative_base, sessionmaker

from telegram import Update, File
from telegram.ext import (
    ApplicationBuilder, MessageHandler, ContextTypes, filters
)

# ---------- Env & Config ----------
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///telegram_backup.db")
MEDIA_BACKUP_DIR = Path(os.getenv("MEDIA_BACKUP_DIR", "telegram_media_backup"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN must be set in the .env file")

MEDIA_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler("telegram_backup_bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ],
)
logger = logging.getLogger("backup-bot")

# ---------- DB (SQLAlchemy 2.x style compatible) ----------
engine = create_engine(DATABASE_URL, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(BigInteger, index=True)
    user_id = Column(BigInteger, index=True)
    username = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    text = Column(Text, nullable=True)
    date = Column(DateTime, default=datetime.utcnow, index=True)
    message_id = Column(Integer)  # not unique globally across chats
    reply_to_message_id = Column(Integer, nullable=True)
    chat_type = Column(String, nullable=True)
    is_group = Column(Boolean, default=False)

class Media(Base):
    __tablename__ = "media"
    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, index=True)
    chat_id = Column(BigInteger, index=True)
    media_type = Column(String)
    file_name = Column(String)
    file_path = Column(String)

Base.metadata.create_all(bind=engine)

# ---------- Helpers ----------
def safe_full_name(first: str | None, last: str | None) -> str:
    """Build a readable full name from first/last names."""
    parts = [p for p in [first, last] if p]
    return " ".join(parts)

def file_basename(chat_id: int, message_id: int, tg_file: File, explicit_ext: str | None = None) -> str:
    """
    Build a deterministic filename for a Telegram file.
    Prefer Telegram's path extension if available, else fallback to provided explicit ext.
    """
    # Try to infer extension from Telegram's file_path
    ext = None
    if tg_file.file_path and "." in tg_file.file_path:
        ext = tg_file.file_path.rsplit(".", 1)[-1].lower()
    if not ext and explicit_ext:
        ext = explicit_ext.strip(".").lower()
    suffix = f".{ext}" if ext else ""
    return f"{chat_id}_{message_id}_{tg_file.file_unique_id}{suffix}"

# ---------- Handler ----------
async def backup_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Save message metadata to DB and download any attached media to disk.
    Works for text, photos, videos, documents, voice, audio, animations, stickers, etc.
    """
    try:
        msg = update.effective_message
        if not msg:
            return

        chat = msg.chat
        user = msg.from_user

        chat_id = chat.id
        user_id = user.id if user else None
        username = user.username if user else None
        full_name = safe_full_name(getattr(user, "first_name", None), getattr(user, "last_name", None))
        text = msg.text or msg.caption  # capture captions too
        date = msg.date
        message_id = msg.message_id
        reply_to_message_id = msg.reply_to_message.message_id if msg.reply_to_message else None
        chat_type = chat.type
        is_group = chat_type in ("group", "supergroup")

        with SessionLocal() as db:
            db_msg = Message(
                chat_id=chat_id,
                user_id=user_id,
                username=username,
                full_name=full_name,
                text=text,
                date=date,
                message_id=message_id,
                reply_to_message_id=reply_to_message_id,
                chat_type=chat_type,
                is_group=is_group,
            )
            db.add(db_msg)
            db.flush()  # allocate db_msg.id if needed later

            # --- Media detection (one primary per message) ---
            tg_file: File | None = None
            media_type: str | None = None

            if msg.photo:
                # largest photo size is at the end
                tg_file = await msg.photo[-1].get_file()
                media_type = "photo"
            elif msg.video:
                tg_file = await msg.video.get_file()
                media_type = "video"
            elif msg.document:
                tg_file = await msg.document.get_file()
                media_type = "document"
            elif msg.voice:
                tg_file = await msg.voice.get_file()
                media_type = "voice"
            elif msg.audio:
                tg_file = await msg.audio.get_file()
                media_type = "audio"
            elif msg.animation:
                tg_file = await msg.animation.get_file()
                media_type = "animation"
            elif msg.sticker:
                tg_file = await msg.sticker.get_file()
                media_type = "sticker"

            if tg_file and media_type:
                # Build a stable filename and download via official PTB helper
                fname = file_basename(chat_id, message_id, tg_file)
                dest_path = MEDIA_BACKUP_DIR / fname
                await tg_file.download_to_drive(custom_path=str(dest_path))

                db_media = Media(
                    message_id=message_id,
                    chat_id=chat_id,
                    media_type=media_type,
                    file_name=fname,
                    file_path=str(dest_path),
                )
                db.add(db_media)

            db.commit()

    except Exception as e:
        logger.exception(f"Error while processing message: {e}")

# ---------- App ----------
def main() -> None:
    """
    Build the Telegram application and start polling.
    """
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Catch all user-generated content except commands; adapt if you want to log commands too.
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, backup_message))

    logger.info("Starting polling…")
    app.run_polling(close_loop=False)

if __name__ == "__main__":
    main()
