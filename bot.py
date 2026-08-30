import json
import os
import random
import time
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import requests
import hashlib
from dotenv import load_dotenv

# Загружаем переменные из .env
load_dotenv()

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфиг из .env
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env файле!")

DATA_FILE = "data/accounts.json"
PROXY_FILE = "proxies.txt"
SETTINGS_FILE = "data/settings.json"

# Создаем папку data
os.makedirs("data", exist_ok=True)

# Загрузка настроек
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"delay": 500, "max_retries": 3}

def save_settings(settings):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)

# Загрузка аккаунтов
def load_accounts():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"guest": [], "facebook": []}

def save_accounts(accounts):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(accounts, f, indent=4, ensure_ascii=False)

# Загрузка прокси
def load_proxies():
    if os.path.exists(PROXY_FILE):
        with open(PROXY_FILE, 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip()]
    return []

# API запрос к Free Fire
def send_like_request(uid, count, account_type, account_data, proxy=None):
    settings = load_settings()
    retries = settings.get("max_retries", 3)
    
    for attempt in range(retries):
        try:
            url = "https://api.dictech.dev/freefire/like"
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Content-Type": "application/json"
            }
            
            payload = {
                "uid": uid,
                "count": count,
                "type": account_type,
                "account": account_data
            }
            
            if proxy:
                proxies = {"http": proxy, "https": proxy}
                response = requests.post(url, json=payload, headers=headers, proxies=proxies, timeout=10)
            else:
                response = requests.post(url, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                logger.warning(f"Attempt {attempt+1} failed: {response.status_code}")
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"Attempt {attempt+1} error: {e}")
            time.sleep(2)
    
    return {"success": False, "error": "Все попытки отправки не удались"}

# Генерация гостевого аккаунта
def generate_guest_account():
    import uuid
    guest_id = str(uuid.uuid4()).replace("-", "")[:16]
    token = hashlib.md5(f"{guest_id}_freefire".encode()).hexdigest()
    return {"guest_id": guest_id, "token": token}

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *FreeFire Like Bot*\n\n"
        "Доступные команды:\n"
        "/like `<ID>` `<кол-во>` - отправить лайки\n"
        "/status - статус бота\n"
        "/add_guest - добавить гостевой аккаунт\n"
        "/add_fb - добавить Facebook аккаунт\n"
        "/settings - настройки\n"
        "/help - помощь\n\n"
        "Пример: `/like 123456789 50`",
        parse_mode="Markdown"
    )

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Помощь*\n\n"
        "🔹 `/like <ID> <кол-во>`\n"
        "   Отправить лайки игроку\n\n"
        "🔹 `/status`\n"
        "   Показать статус бота\n\n"
        "🔹 `/add_guest`\n"
        "   Добавить гостевой аккаунт\n\n"
        "🔹 `/add_fb`\n"
        "   Добавить Facebook аккаунт (токен)\n\n"
        "🔹 `/settings`\n"
        "   Настроить задержку и кол-во попыток\n\n"
        "🔹 `/proxies`\n"
        "   Управление прокси\n\n"
        "🔹 `/stats`\n"
        "   Статистика отправленных лайков",
        parse_mode="Markdown"
    )

# Команда /like
async def like_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text("❌ Использование: `/like <ID> <кол-во>`", parse_mode="Markdown")
        return
    
    uid = args[0]
    try:
        count = int(args[1])
        if count < 1 or count > 500:
            await update.message.reply_text("❌ Количество должно быть от 1 до 500")
            return
    except ValueError:
        await update.message.reply_text("❌ Количество должно быть числом")
        return
    
    status_msg = await update.message.reply_text(f"⏳ Отправка {count} лайков игроку {uid}...")
    
    accounts = load_accounts()
    
    if not accounts["guest"] and not accounts["facebook"]:
        await status_msg.edit_text("❌ Нет доступных аккаунтов. Добавьте через /add_guest или /add_fb")
        return
    
    all_accs = []
    for acc in accounts["guest"]:
        all_accs.append({"type": "guest", "data": acc})
    for acc in accounts["facebook"]:
        all_accs.append({"type": "facebook", "data": acc})
    
    if not all_accs:
        await status_msg.edit_text("❌ Нет доступных аккаунтов")
        return
    
    total_sent = 0
    settings = load_settings()
    delay = settings.get("delay", 500) / 1000
    proxies = load_proxies()
    
    for i, acc in enumerate(all_accs):
        if total_sent >= count:
            break
            
        remaining = count - total_sent
        send_count = min(50, remaining)
        
        proxy = proxies[i % len(proxies)] if proxies else None
        
        result = send_like_request(
            uid, 
            send_count, 
            acc["type"], 
            acc["data"], 
            proxy
        )
        
        if result["success"]:
            total_sent += send_count
            await status_msg.edit_text(
                f"✅ Отправлено {total_sent}/{count} лайков игроку {uid}\n"
                f"📊 Аккаунтов использовано: {i+1}"
            )
        else:
            logger.warning(f"Failed with account {i+1}: {result.get('error')}")
        
        time.sleep(delay)
    
    if total_sent > 0:
        # Сохраняем статистику
        stats_file = "data/stats.json"
        stats = {}
        if os.path.exists(stats_file):
            with open(stats_file, 'r', encoding='utf-8') as f:
                stats = json.load(f)
        
        stats['total_likes'] = stats.get('total_likes', 0) + total_sent
        stats['total_players'] = stats.get('total_players', 0) + 1
        stats['last_date'] = datetime.now().strftime('%d.%m.%Y %H:%M')
        
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=4, ensure_ascii=False)
        
        await status_msg.edit_text(
            f"✅ *Готово!*\n"
            f"👤 Игрок: `{uid}`\n"
            f"❤️ Отправлено: {total_sent}/{count}\n"
            f"📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            parse_mode="Markdown"
        )
    else:
        await status_msg.edit_text("❌ Не удалось отправить ни одного лайка. Проверьте аккаунты.")

# Команда /status
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    accounts = load_accounts()
    settings = load_settings()
    proxies = load_proxies()
    
    text = f"""
📊 *Статус бота*

👥 Аккаунты:
  • Гостевые: {len(accounts['guest'])}
  • Facebook: {len(accounts['facebook'])}
  • Всего: {len(accounts['guest']) + len(accounts['facebook'])}

⚙️ Настройки:
  • Задержка: {settings.get('delay', 500)} мс
  • Попытки: {settings.get('max_retries', 3)}

🌐 Прокси: {'✅ ' + str(len(proxies)) + ' шт' if proxies else '❌ не используются'}

📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}
"""
    await update.message.reply_text(text, parse_mode="Markdown")

# Команда /add_guest
async def add_guest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    accounts = load_accounts()
    
    new_guest = generate_guest_account()
    accounts["guest"].append(new_guest)
    save_accounts(accounts)
    
    await update.message.reply_text(
        f"✅ Добавлен гостевой аккаунт:\n"
        f"🆔 ID: `{new_guest['guest_id']}`\n"
        f"🔑 Токен: `{new_guest['token'][:8]}...`",
        parse_mode="Markdown"
    )

# Команда /add_fb
async def add_fb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    
    if len(args) < 1:
        await update.message.reply_text("❌ Использование: `/add_fb <токен>`", parse_mode="Markdown")
        return
    
    fb_token = args[0]
    accounts = load_accounts()
    accounts["facebook"].append({"fb_token": fb_token})
    save_accounts(accounts)
    
    await update.message.reply_text("✅ Facebook аккаунт добавлен")

# Команда /settings
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    settings = load_settings()
    
    keyboard = [
        [InlineKeyboardButton(f"⏱ Задержка: {settings.get('delay', 500)} мс", callback_data="set_delay")],
        [InlineKeyboardButton(f"🔄 Попытки: {settings.get('max_retries', 3)}", callback_data="set_retries")],
        [InlineKeyboardButton("🗑 Очистить аккаунты", callback_data="clear_accounts")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⚙️ *Настройки*\nВыберите параметр для изменения:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

# Команда /proxies
async def proxies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    proxies = load_proxies()
    
    if proxies:
        text = f"🌐 Прокси ({len(proxies)} шт):\n" + "\n".join(proxies[:10])
        if len(proxies) > 10:
            text += f"\n... и еще {len(proxies) - 10}"
    else:
        text = "❌ Прокси не загружены. Добавьте их в файл proxies.txt"
    
    await update.message.reply_text(text)

# Команда /stats
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats_file = "data/stats.json"
    if os.path.exists(stats_file):
        with open(stats_file, 'r', encoding='utf-8') as f:
            stats = json.load(f)
        await update.message.reply_text(
            f"📊 *Статистика*\n\n"
            f"❤️ Всего лайков: {stats.get('total_likes', 0)}\n"
            f"👤 Всего игроков: {stats.get('total_players', 0)}\n"
            f"📅 Последний: {stats.get('last_date', 'нет данных')}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("📊 Статистики пока нет")

# Обработчик callback'ов
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "set_delay":
        context.user_data['setting'] = 'delay'
        await query.edit_message_text("Введите задержку в миллисекундах (например, 500):")
    
    elif data == "set_retries":
        context.user_data['setting'] = 'retries'
        await query.edit_message_text("Введите количество попыток (например, 3):")
    
    elif data == "clear_accounts":
        save_accounts({"guest": [], "facebook": []})
        await query.edit_message_text("✅ Все аккаунты удалены")

# Обработка текстовых сообщений
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'setting' not in context.user_data:
        return
    
    setting = context.user_data['setting']
    settings = load_settings()
    
    try:
        value = int(update.message.text)
        
        if setting == 'delay':
            settings['delay'] = value
            await update.message.reply_text(f"✅ Задержка установлена: {value} мс")
        elif setting == 'retries':
            settings['max_retries'] = value
            await update.message.reply_text(f"✅ Попыток: {value}")
        
        save_settings(settings)
        del context.user_data['setting']
        
    except ValueError:
        await update.message.reply_text("❌ Введите число")

# Главная функция
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("like", like_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("add_guest", add_guest))
    app.add_handler(CommandHandler("add_fb", add_fb))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("proxies", proxies_command))
    app.add_handler(CommandHandler("stats", stats_command))
    
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("🤖 Бот запущен...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()