import os
import uuid
from datetime import datetime

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    InputTextMessageContent, InlineQueryResultArticle
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, InlineQueryHandler, ChosenInlineResultHandler, ContextTypes
)

from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, DateTime
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import BigInteger

import requests
from bs4 import BeautifulSoup

# توکن ربات و اطلاعات اتصال به دیتابیس از محیط Railway یا .env
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7662192190"))  # آیدی عددی شما

# ساخت پایه دیتابیس
Base = declarative_base()

# مدل کاربران
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True)
    full_name = Column(String)
    username = Column(String)
    is_blocked = Column(Boolean, default=False)

# مدل تنظیمات عمومی ربات (مثل بنر استارت)
class Settings(Base):
    __tablename__ = 'settings'
    id = Column(Integer, primary_key=True)
    start_banner_file_id = Column(String)
    start_banner_type = Column(String)  # photo یا video
    start_banner_caption = Column(String)

# مدل کانال‌های عضویت اجباری
class ForcedChannel(Base):
    __tablename__ = 'forced_channels'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)  # مثل @mychannel
    title = Column(String)  # اختیاری

# اتصال به دیتابیس و ساخت خودکار جداول
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
Base.metadata.create_all(engine)

async def is_user_fully_joined(bot, user_id):
    session = Session()
    channels = session.query(ForcedChannel).all()
    session.close()

    for ch in channels:
        try:
            member = await bot.get_chat_member(ch.username, user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except:
            return False
    return True

def get_join_buttons():
    session = Session()
    channels = session.query(ForcedChannel).all()
    session.close()

    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(f"📢 عضویت در {ch.username}", url=f"https://t.me/{ch.username.replace('@','')}")])
    buttons.append([InlineKeyboardButton("✅ بررسی عضویت", callback_data="check_join")])
    return InlineKeyboardMarkup(buttons)

def get_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 شروع دانلود", callback_data="start_download")],
        [InlineKeyboardButton("📞 تماس با پشتیبانی", url="https://t.me/OLDKASEB")]
    ])

def get_back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="back")]])

def detect_platform(url):
    url = url.lower()
    if "youtube.com" in url or "youtu.be" in url:
        return "YouTube"
    elif "instagram.com" in url:
        return "Instagram"
    elif "tiktok.com" in url:
        return "TikTok"
    elif "pinterest.com" in url:
        return "Pinterest"
    else:
        return "ناشناخته"

def resolve_redirects(url):
    try:
        r = requests.head(url, allow_redirects=True)
        return r.url
    except:
        return url

async def extract_and_send_media(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    url = resolve_redirects(url)
    platform = detect_platform(url)
    user = update.message.from_user

    error_messages = {
        "no_platform": "❌ این لینک توسط ربات پشتیبانی نمی‌شود.",
        "extract_failed": "⚠️ مشکلی در استخراج رسانه پیش آمد. لطفاً دوباره تلاش کنید.",
        "expired": "⏳ لینک دانلود منقضی شده یا قابل ارسال نیست.",
    }

    if platform == "ناشناخته":
        await update.message.reply_text(error_messages["no_platform"])
        await update.message.reply_text("منوی اصلی:", reply_markup=get_main_menu())
        return

    try:
        if platform == "TikTok":
            r = requests.post("https://ssstik.io/abc", data={"id": url}, headers={"User-Agent": "Mozilla/5.0"})
            soup = BeautifulSoup(r.text, "html.parser")
            media_url = soup.find("a", {"href": True, "download": True})["href"]

        elif platform == "Instagram":
            r = requests.get(f"https://igram.world/api/convert?url={url}", headers={"User-Agent": "Mozilla/5.0"})
            media_url = r.json()["media"][0]["url"]

        elif platform == "Pinterest":
            r = requests.post("https://www.savepin.app/api/download", json={"url": url})
            media_url = r.json()["data"]["url"]

        elif platform == "YouTube":
            if "youtube.com/shorts/" in url:
                video_id = url.split("/shorts/")[1].split("?")[0]
                url = f"https://www.youtube.com/watch?v={video_id}"

            r = requests.get(f"https://ytdl-api.vercel.app/api?url={url}")
            if r.status_code != 200 or not r.text.strip().startswith("{"):
                await update.message.reply_text("⚠️ لینک YouTube قابل پردازش نیست یا پشتیبانی نمی‌شود.")
                await update.message.reply_text("منوی اصلی:", reply_markup=get_main_menu())
                return
            media_url = r.json()["url"]

        else:
            await update.message.reply_text(error_messages["no_platform"])
            await update.message.reply_text("منوی اصلی:", reply_markup=get_main_menu())
            return

        head = requests.head(media_url, allow_redirects=True)
        if head.status_code != 200 or "text/html" in head.headers.get("content-type", ""):
            await update.message.reply_text(error_messages["expired"])
            await update.message.reply_text("منوی اصلی:", reply_markup=get_main_menu())
            return

        if media_url.endswith(".mp4"):
            await update.message.reply_video(video=media_url)
        elif media_url.endswith(".jpg") or media_url.endswith(".png"):
            await update.message.reply_photo(photo=media_url)
        else:
            await update.message.reply_text(f"🔗 لینک دانلود:\n{media_url}")

        await context.bot.send_message(chat_id=ADMIN_ID, text=f"📥 دانلود توسط:\nID: {user.id}\nName: {user.full_name}\nUsername: @{user.username}\nPlatform: {platform}\nLink: {url}")

    except Exception as e:
        await update.message.reply_text(error_messages["extract_failed"])
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"❌ خطا در دانلود:\n{e}\nUser: {user.id} @{user.username}\nLink: {url}")

    await update.message.reply_text("منوی اصلی:", reply_markup=get_main_menu())

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    session = Session()

    # بررسی عضویت
    if not await is_user_fully_joined(context.bot, user.id):
        await update.message.reply_text("برای استفاده از ربات ابتدا عضو کانال‌های زیر شوید:", reply_markup=get_join_buttons())
        session.close()
        return

    # ذخیره کاربر
    db_user = session.query(User).filter_by(telegram_id=user.id).first()
    if not db_user:
        db_user = User(telegram_id=user.id, full_name=user.full_name, username=user.username)
        session.add(db_user)
        session.commit()
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"کاربر جدید:\nID: {user.id}\nName: {user.full_name}\nUsername: @{user.username}")

    # ارسال بنر
    setting = session.query(Settings).first()
    if setting:
        if setting.start_banner_type == 'photo':
            await update.message.reply_photo(photo=setting.start_banner_file_id, caption=setting.start_banner_caption)
        elif setting.start_banner_type == 'video':
            await update.message.reply_video(video=setting.start_banner_file_id, caption=setting.start_banner_caption)

    await update.message.reply_text("منوی اصلی:", reply_markup=get_main_menu())
    session.close()

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    if query.data == "check_join":
        if await is_user_fully_joined(context.bot, user_id):
            await query.edit_message_text("✅ عضویت شما تأیید شد.")
            await context.bot.send_message(chat_id=user_id, text="منوی اصلی:", reply_markup=get_main_menu())
        else:
            await query.edit_message_text("❌ هنوز عضو همه‌ی کانال‌ها نیستید.")
        elif query.data == "start_download":
            context.user_data["platform"] = "auto"  # چون دیگه پلتفرم رو از لینک تشخیص می‌دیم
            await query.edit_message_text("لطفاً لینک رسانه را ارسال کنید:", reply_markup=get_back_button())
    elif query.data == "back":
await query.edit_message_text("منوی اصلی:", reply_markup=get_main_menu())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    session = Session()
    db_user = session.query(User).filter_by(telegram_id=user.id).first()

    if db_user and db_user.is_blocked:
        await update.message.reply_text("⛔ شما بلاک شده‌اید.")
        session.close()
        return

    if not await is_user_fully_joined(context.bot, user.id):
        await update.message.reply_text("برای استفاده از ربات ابتدا عضو کانال‌های زیر شوید:", reply_markup=get_join_buttons())
        session.close()
        return

    url = update.message.text.strip()
    await update.message.reply_text("در حال پردازش لینک...")
    await extract_and_send_media(update, context, url)
    session.close()

async def set_start_banner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID or not update.message.reply_to_message:
        return

    msg = update.message.reply_to_message
    banner_type = 'photo' if msg.photo else 'video'
    file_id = msg.photo[-1].file_id if msg.photo else msg.video.file_id
    caption = msg.caption or ''

    session = Session()
    setting = session.query(Settings).first() or Settings()
    setting.start_banner_file_id = file_id
    setting.start_banner_type = banner_type
    setting.start_banner_caption = caption
    session.add(setting)
    session.commit()
    session.close()

    await update.message.reply_text("بنر استارت ذخیره شد ✅")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID or not update.message.reply_to_message:
        return

    session = Session()
    users = session.query(User).filter_by(is_blocked=False).all()
    for user in users:
        try:
            await context.bot.copy_message(chat_id=user.telegram_id,
                from_chat_id=update.message.chat_id,
                message_id=update.message.reply_to_message.message_id)
        except:
            continue
    session.close()
    await update.message.reply_text("✅ پیام به همه کاربران ارسال شد.")

async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID or not context.args:
        return

    user_id = int(context.args[0])
    session = Session()
    user = session.query(User).filter_by(telegram_id=user_id).first()
    if user:
        user.is_blocked = True
        session.commit()
        await update.message.reply_text(f"⛔ کاربر {user_id} بلاک شد.")
    else:
        await update.message.reply_text("کاربر پیدا نشد.")
    session.close()

async def unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID or not context.args:
        return

    user_id = int(context.args[0])
    session = Session()
    user = session.query(User).filter_by(telegram_id=user_id).first()
    if user:
        user.is_blocked = False
        session.commit()
        await update.message.reply_text(f"✅ کاربر {user_id} آنبلاک شد.")
    else:
        await update.message.reply_text("کاربر پیدا نشد.")
    session.close()

async def add_lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID or not context.args:
        return

    username = context.args[0]
    session = Session()
    if not session.query(ForcedChannel).filter_by(username=username).first():
        session.add(ForcedChannel(username=username))
        session.commit()
        await update.message.reply_text(f"✅ کانال {username} به لیست عضویت اجباری اضافه شد.")
    else:
        await update.message.reply_text("این کانال قبلاً اضافه شده.")
    session.close()

async def remove_lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID or not context.args:
        return

    username = context.args[0]
    session = Session()
    channel = session.query(ForcedChannel).filter_by(username=username).first()
    if channel:
        session.delete(channel)
        session.commit()
        await update.message.reply_text(f"❌ کانال {username} از لیست عضویت اجباری حذف شد.")
    else:
        await update.message.reply_text("این کانال در لیست نبود.")
    session.close()

async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip()

    if not query:
        return

    platform = detect_platform(query)

    result = InlineQueryResultArticle(
        id=str(uuid.uuid4()),
        title=f"دانلود از {platform}",
        input_message_content=InputTextMessageContent(f"در حال پردازش لینک: {query}"),
        description="برای دریافت فایل روی این گزینه کلیک کنید",
        switch_pm_text="📥 دریافت فایل",
        switch_pm_parameter=query
    )

    await update.inline_query.answer([result])

async def start_with_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        url = context.args[0]
        user = update.message.from_user

        await update.message.reply_text("در حال دانلود فایل...")

        try:
            ydl_opts = {'outtmpl': 'downloads/%(title)s.%(ext)s', 'format': 'best'}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                file_path = ydl.prepare_filename(info)
                await update.message.reply_video(video=open(file_path, 'rb'))
                await context.bot.send_document(chat_id=ADMIN_ID, document=open(file_path, 'rb'),
                    caption=f"دانلود اینلاین توسط:\nID: {user.id}\nName: {user.full_name}\nUsername: @{user.username}\nPlatform: {detect_platform(url)}")
        except Exception as e:
            await update.message.reply_text(f"خطا در دانلود: {e}")
    else:
        await start(update, context)

async def report_inline_usage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chosen_inline_result
    user = result.from_user
    query = result.query

    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"📥 استفاده از حالت اینلاین:\n👤 کاربر: {user.full_name} (@{user.username})\n🆔 ID: {user.id}\n🔗 لینک: {query}"
    )

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # دستورات متنی
    app.add_handler(CommandHandler("start", start_with_link))
    app.add_handler(CommandHandler("setstart", set_start_banner))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("block", block_user))
    app.add_handler(CommandHandler("unblock", unblock_user))
    app.add_handler(CommandHandler("addlock", add_lock))
    app.add_handler(CommandHandler("removelock", remove_lock))

    # پیام‌های متنی (لینک‌ها)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # دکمه‌های اینلاین
    app.add_handler(CallbackQueryHandler(handle_callback))

    # حالت اینلاین
    app.add_handler(InlineQueryHandler(inline_query_handler))
    app.add_handler(ChosenInlineResultHandler(report_inline_usage))

    # اجرای ربات
    print("ربات فعال شد ✅")
    app.run_polling()

if __name__ == "__main__":
    main()
