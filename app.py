import telebot
from telebot import types
import sqlite3
import datetime
import requests
import urllib3
import time
import threading
import re
import os
import json
import random
import string
from flask import Flask, request, jsonify

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ===== КОНФИГ =====
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден в переменных окружения!")

API_KEY = "Tv2GrTBsyJXEBRwgUHmcUY9Gd5KnOgIA9zX5Vn3f3dAkqFgwLefrMdKVATwN"
API_URL = "https://kuzya-boost.ru/api/v2"
ADMIN_ID = 593150935
BOT_USERNAME = "NekroKrutka_rabot"
CHANNEL_ID = "@repaBotaNakruta"
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")

if not CRYPTOBOT_TOKEN:
    print("⚠️ CRYPTOBOT_TOKEN не найден! Автопополнение через криптобот не будет работать.")

bot = telebot.TeleBot(TOKEN)
session = requests.Session()
session.verify = False
session.headers.update({'User-Agent': 'Mozilla/5.0'})

print("✅ Бот инициализирован")

# ===== Flask приложение =====
flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return "🤖 Бот NekroKrutka работает!"

@flask_app.route('/webhook', methods=['POST'])
def crypto_webhook():
    try:
        data = request.get_json()
        print(f"📩 Webhook получен: {data}")
        
        if data.get('status') == 'paid':
            invoice_id = data.get('invoice_id')
            user_id = int(data.get('user_id'))
            amount_rub = float(data.get('amount_rub'))
            
            conn = sqlite3.connect('bot.db')
            cur = conn.cursor()
            cur.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount_rub, user_id))
            conn.commit()
            conn.close()
            
            try:
                new_balance = get_user_balance(user_id)
                bot.send_message(
                    user_id,
                    f"✅ **Пополнение успешно!**\n\n"
                    f"💰 Сумма: {amount_rub:.2f} руб.\n"
                    f"📊 Новый баланс: {new_balance:.2f} руб."
                )
            except:
                pass
            
            return jsonify({'status': 'ok'}), 200
        
        return jsonify({'status': 'ignored'}), 200
    except Exception as e:
        print(f"❌ Ошибка webhook: {e}")
        return jsonify({'status': 'error'}), 500

# ===== НАЦЕНКИ =====
def get_markup(price):
    if price < 5:
        return 10
    elif price < 20:
        return 20
    elif price < 50:
        return 30
    else:
        return 50

# ===== СИСТЕМА УРОВНЕЙ =====
LEVELS = {
    "novice": {"name": "🟢 Новичок", "discount": 0, "spent_required": 0},
    "advanced": {"name": "🟡 Продвинутый", "discount": 3.5, "spent_required": 50},
    "vip": {"name": "🔴 VIP", "discount": 5, "spent_required": 150},
    "reseller": {"name": "⚫ Реселлер", "discount": 10, "spent_required": 0}
}

def get_user_level(user_id):
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('SELECT total_spent, is_reseller FROM users WHERE user_id = ?', (user_id,))
    result = cur.fetchone()
    conn.close()
    
    if not result:
        return "novice"
    
    total_spent, is_reseller = result
    
    if is_reseller == 1:
        return "reseller"
    
    if total_spent >= 150:
        return "vip"
    elif total_spent >= 50:
        return "advanced"
    else:
        return "novice"

def get_user_discount(user_id):
    level = get_user_level(user_id)
    return LEVELS[level]["discount"]

# ===== БАЗА ДАННЫХ =====
def init_db():
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance REAL DEFAULT 0,
            coins INTEGER DEFAULT 0,
            referred_by INTEGER DEFAULT NULL,
            discount_used INTEGER DEFAULT 0,
            discount_expiry TEXT DEFAULT NULL,
            reg_date TEXT,
            pending_discount REAL DEFAULT 0,
            total_spent REAL DEFAULT 0,
            is_reseller INTEGER DEFAULT 0,
            is_blocked INTEGER DEFAULT 0,
            has_passed_captcha INTEGER DEFAULT 0
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            service_id INTEGER,
            service_name TEXT,
            link TEXT,
            quantity INTEGER,
            price REAL,
            status TEXT DEFAULT 'pending',
            order_id TEXT,
            date TEXT,
            last_check TEXT,
            is_coin_order INTEGER DEFAULT 0
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            rating INTEGER,
            review_text TEXT,
            date TEXT,
            is_approved INTEGER DEFAULT 0
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER,
            referee_id INTEGER,
            date TEXT
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS admin_chats (
            user_id INTEGER PRIMARY KEY,
            active INTEGER DEFAULT 1,
            start_time TEXT
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS promocodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            bonus_type TEXT,
            bonus_amount REAL,
            max_uses INTEGER,
            used_count INTEGER DEFAULT 0,
            expires_at TEXT,
            is_active INTEGER DEFAULT 1,
            created_by INTEGER,
            created_at TEXT
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS promocode_uses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            promo_id INTEGER,
            user_id INTEGER,
            used_at TEXT
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS review_counter (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            counter INTEGER DEFAULT 0
        )
    ''')
    
    cur.execute('INSERT OR IGNORE INTO review_counter (id, counter) VALUES (1, 0)')
    
    conn.commit()
    conn.close()
    print("✅ База данных готова")

init_db()

# ===== ФУНКЦИИ =====
def get_user_balance(user_id):
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    result = cur.fetchone()
    conn.close()
    return result[0] if result else 0

def get_user_coins(user_id):
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('SELECT coins FROM users WHERE user_id = ?', (user_id,))
    result = cur.fetchone()
    conn.close()
    return result[0] if result else 0

def is_user_blocked(user_id):
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('SELECT is_blocked FROM users WHERE user_id = ?', (user_id,))
    result = cur.fetchone()
    conn.close()
    return result[0] == 1 if result else False

def get_service_price(service_id):
    try:
        url = f"{API_URL}?action=services&key={API_KEY}"
        response = session.get(url, timeout=30)
        if response.status_code == 200:
            services = response.json()
            for s in services:
                if s.get('service') == service_id:
                    return float(s.get('rate', 0))
        return None
    except:
        return None

def get_service_price_with_markup(service_id):
    price = get_service_price(service_id)
    if price is None:
        return None
    return price + get_markup(price)

def create_order_api(service_id, link, quantity):
    try:
        url = f"{API_URL}?action=add&service={service_id}&link={link}&quantity={quantity}&key={API_KEY}"
        response = session.get(url, timeout=30)
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"Ошибка {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def get_order_status_api(order_id):
    try:
        url = f"{API_URL}?action=status&order={order_id}&key={API_KEY}"
        response = session.get(url, timeout=30)
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"Ошибка {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def refill_order_api(order_id):
    try:
        url = f"{API_URL}?action=refill&order={order_id}&key={API_KEY}"
        response = session.get(url, timeout=30)
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"Ошибка {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def has_user_reviewed(user_id):
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM reviews WHERE user_id = ? AND is_approved = 1', (user_id,))
    count = cur.fetchone()[0]
    conn.close()
    return count > 0

def get_service_name_by_id(service_id):
    for platform in SERVICES.values():
        for category in platform["categories"].values():
            for subcategory in category.values():
                for service in subcategory:
                    if service["id"] == service_id:
                        return service["name"]
    return f"Услуга #{service_id}"

def parse_guarantee(service_name):
    name_lower = service_name.lower()
    
    if 'без гарантии' in name_lower or 'без гарантий' in name_lower or '⛔' in name_lower:
        return {'has_guarantee': False, 'guarantee_text': 'Нет гарантии', 'refill_available': False}
    
    patterns = [
        (r'\[(\d+)\s*\+\s*день\]', '1 день'),
        (r'\[(\d+)\s*день\]', '1 день'),
        (r'\[(\d+)\s*дня\]', '{0} дня'),
        (r'\[(\d+)\s*дней\]', '{0} дней'),
        (r'\[(\d+)\s*дн\]', '{0} дней'),
        (r'\[(\d+)\s*месяц\]', '{0} месяц'),
        (r'\[(\d+)\s*месяца\]', '{0} месяца'),
        (r'\[(\d+)\s*месяцев\]', '{0} месяцев'),
    ]
    
    for pattern, template in patterns:
        match = re.search(pattern, name_lower)
        if match:
            num = match.group(1)
            days_text = template.format(num)
            return {'has_guarantee': True, 'guarantee_text': days_text, 'refill_available': True}
    
    if 'навсегда' in name_lower:
        return {'has_guarantee': True, 'guarantee_text': 'Навсегда', 'refill_available': True}
    
    if '♻️' in service_name:
        return {'has_guarantee': True, 'guarantee_text': 'Есть гарантия (срок не указан)', 'refill_available': True}
    
    return {'has_guarantee': False, 'guarantee_text': 'Не указана', 'refill_available': False}

def is_guaranteed_service(service_name):
    guarantee_keywords = ['гарант', 'день', 'дн', 'месяц', 'мес', 'навсегда', '♻️']
    return any(keyword in service_name.lower() for keyword in guarantee_keywords)

def get_refillable_orders(user_id):
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    
    cur.execute('''
        SELECT id, service_name, service_id, quantity, price, date, order_id
        FROM orders 
        WHERE user_id = ? AND status = 'выполнен ✅'
        ORDER BY date DESC
    ''', (user_id,))
    orders = cur.fetchall()
    conn.close()
    
    refillable = []
    now = datetime.datetime.now()
    
    for order in orders:
        order_id, service_name, service_id, quantity, price, date_str, api_order_id = order
        if not is_guaranteed_service(service_name):
            continue
        try:
            order_date = datetime.datetime.strptime(date_str, "%Y-%m-%d %H:%M")
            hours_passed = (now - order_date).total_seconds() / 3600
            if hours_passed >= 24:
                refillable.append({
                    'id': order_id,
                    'service_name': service_name,
                    'service_id': service_id,
                    'quantity': quantity,
                    'price': price,
                    'date': date_str,
                    'api_order_id': api_order_id
                })
        except:
            continue
    return refillable

def get_referral_stats(user_id):
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM referrals WHERE referrer_id = ?', (user_id,))
    count = cur.fetchone()[0]
    cur.execute('''
        SELECT referee_id, date 
        FROM referrals 
        WHERE referrer_id = ? 
        ORDER BY date DESC
    ''', (user_id,))
    referrals = cur.fetchall()
    conn.close()
    return count, referrals

def get_ref_link(user_id):
    return f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

def get_next_review_number():
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('UPDATE review_counter SET counter = counter + 1 WHERE id = 1')
    cur.execute('SELECT counter FROM review_counter WHERE id = 1')
    result = cur.fetchone()
    conn.commit()
    conn.close()
    return result[0] if result else 1

def send_review_to_channel(username, user_id, rating, review_text):
    try:
        review_number = get_next_review_number()
        date = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
        
        text = (
            f"⭐️ **Отзыв #{review_number}**\n\n"
            f"👤 @{username} (ID: {user_id})\n"
            f"⭐️ Оценка: {rating}/5\n"
            f"📝 {review_text}\n\n"
            f"📅 {date}"
        )
        
        bot.send_message(CHANNEL_ID, text, parse_mode="Markdown")
        return True
    except Exception as e:
        print(f"Ошибка отправки в канал: {e}")
        return False

# ===== ПРОМОКОДЫ =====
def generate_promo_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def create_promo_code(code, bonus_type, bonus_amount, max_uses, expires_at=None):
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    try:
        cur.execute('''
            INSERT INTO promocodes (code, bonus_type, bonus_amount, max_uses, expires_at, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (code, bonus_type, bonus_amount, max_uses, expires_at, ADMIN_ID, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

def get_promo_code(code):
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('''
        SELECT id, code, bonus_type, bonus_amount, max_uses, used_count, expires_at, is_active
        FROM promocodes 
        WHERE code = ? AND is_active = 1
    ''', (code,))
    result = cur.fetchone()
    conn.close()
    return result

def use_promo_code(code, user_id):
    promo = get_promo_code(code)
    if not promo:
        return {'success': False, 'message': '❌ Промокод не найден или неактивен!'}
    
    promo_id, promo_code, bonus_type, bonus_amount, max_uses, used_count, expires_at, is_active = promo
    
    if expires_at:
        try:
            expiry = datetime.datetime.strptime(expires_at, "%Y-%m-%d %H:%M")
            if expiry < datetime.datetime.now():
                return {'success': False, 'message': '❌ Срок действия промокода истёк!'}
        except:
            pass
    
    if max_uses > 0 and used_count >= max_uses:
        return {'success': False, 'message': '❌ Промокод уже использован максимальное количество раз!'}
    
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('SELECT id FROM promocode_uses WHERE promo_id = ? AND user_id = ?', (promo_id, user_id))
    if cur.fetchone():
        conn.close()
        return {'success': False, 'message': '❌ Вы уже использовали этот промокод!'}
    
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    
    if bonus_type == 'rubles':
        cur.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (bonus_amount, user_id))
        bonus_text = f"{bonus_amount:.2f} руб."
    elif bonus_type == 'coins':
        cur.execute('UPDATE users SET coins = coins + ? WHERE user_id = ?', (bonus_amount, user_id))
        bonus_text = f"{bonus_amount} монет"
    elif bonus_type == 'discount':
        cur.execute('UPDATE users SET pending_discount = ? WHERE user_id = ?', (bonus_amount, user_id))
        bonus_text = f"{bonus_amount}% скидка на следующий заказ"
    else:
        conn.close()
        return {'success': False, 'message': '❌ Неизвестный тип бонуса!'}
    
    cur.execute('UPDATE promocodes SET used_count = used_count + 1 WHERE id = ?', (promo_id,))
    
    cur.execute('''
        INSERT INTO promocode_uses (promo_id, user_id, used_at)
        VALUES (?, ?, ?)
    ''', (promo_id, user_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    
    conn.commit()
    conn.close()
    
    return {'success': True, 'message': f'✅ Промокод активирован!\n\n🎁 Бонус: {bonus_text}', 'bonus_type': bonus_type, 'bonus_amount': bonus_amount}

def get_all_promocodes():
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('''
        SELECT id, code, bonus_type, bonus_amount, max_uses, used_count, expires_at, is_active
        FROM promocodes 
        ORDER BY id DESC
    ''')
    result = cur.fetchall()
    conn.close()
    return result

# ===== АДМИН-ФУНКЦИИ =====
def get_all_users(page=0, per_page=10):
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    offset = page * per_page
    cur.execute('''
        SELECT user_id, username, balance, coins, total_spent, reg_date, is_blocked 
        FROM users 
        ORDER BY reg_date DESC 
        LIMIT ? OFFSET ?
    ''', (per_page, offset))
    users = cur.fetchall()
    cur.execute('SELECT COUNT(*) FROM users')
    total = cur.fetchone()[0]
    conn.close()
    return users, total

def get_all_orders(page=0, per_page=10):
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    offset = page * per_page
    cur.execute('''
        SELECT id, user_id, service_name, quantity, price, status, date, order_id
        FROM orders 
        ORDER BY id DESC 
        LIMIT ? OFFSET ?
    ''', (per_page, offset))
    orders = cur.fetchall()
    cur.execute('SELECT COUNT(*) FROM orders')
    total = cur.fetchone()[0]
    conn.close()
    return orders, total

def get_pending_reviews():
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('SELECT id, user_id, username, rating, review_text, date FROM reviews WHERE is_approved = 0')
    reviews = cur.fetchall()
    conn.close()
    return reviews

def approve_review(review_id):
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('SELECT user_id, username, rating, review_text FROM reviews WHERE id = ?', (review_id,))
    review = cur.fetchone()
    if review:
        user_id, username, rating, review_text = review
        send_review_to_channel(username, user_id, rating, review_text)
        cur.execute('UPDATE reviews SET is_approved = 1 WHERE id = ?', (review_id,))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

def decline_review(review_id):
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('DELETE FROM reviews WHERE id = ?', (review_id,))
    conn.commit()
    conn.close()

# ===== ОСТАЛЬНОЙ КОД БОТА =====
# Здесь должны быть все обработчики кнопок, команды и т.д.
# Я их не копирую, чтобы не переполнять сообщение, но они должны быть

# ===== СТРУКТУРА УСЛУГ =====
SERVICES = {
    "telegram": {
        "name": "✈️ Telegram",
        "categories": {
            "Подписчики": {
                "С гарантией": [
                    {"id": 1631, "name": "⭐️ Telegram Подписчики [1+ день без списаний ♻️] [Моментальные]"},
                    {"id": 1583, "name": "⭐️ Telegram Подписчики [3 дня без списаний ♻️] [Моментальные]"},
                    {"id": 1585, "name": "⭐️ Telegram Подписчики [7 дней без списаний ♻️] [Моментальные]"},
                    {"id": 1580, "name": "⭐️ Telegram Подписчики [Навсегда без списаний ♻️] [Моментальные]"},
                ],
                "Без гарантии": [
                    {"id": 1900, "name": "Telegram Подписчики [Без гарантии] [Моментальный старт]"},
                    {"id": 1630, "name": "Telegram Подписчики [Без гарантии ⛔️] [Рефилл 30 дней ♻️]"},
                ]
            },
            "Реакции": {
                "С просмотрами": [
                    {"id": 1670, "name": "Telegram Позитивные Реакции [👍🤩🎉🔥❤️🥰👏🏻🥳😍❤️‍🔥💯] + Просмотры"},
                    {"id": 1671, "name": "Telegram Негативные Реакции [🖕💔👎😢💩🤮🤬😡🥱🍌😈] + Просмотры"},
                ],
                "Без просмотров": [
                    {"id": 1574, "name": "Telegram Позитивные Реакции [👍🎉🔥❤️🥰🤩👏🏻]"},
                    {"id": 1535, "name": "Telegram Реакция [👍❤️🔥🎉]"},
                    {"id": 1536, "name": "Telegram Реакция [👎💩😱😢]"},
                    {"id": 1499, "name": "Telegram Негативные Реакции [👎💩🤮🤔🤯😁😢🤬]"},
                ]
            },
            "Просмотры": {
                "Все": [
                    {"id": 1547, "name": "⭐ Telegram Просмотры на пост [Быстрый старт]"},
                    {"id": 1548, "name": "Telegram Просмотры на пост [Моментальные]"},
                ]
            }
        }
    },
    "tiktok": {
        "name": "📱 TikTok",
        "categories": {
            "Просмотры": {
                "С гарантией": [
                    {"id": 1609, "name": "TikTok Просмотры [Моментальный старт] [Гарантия 30 дней ♻️]"},
                ],
                "Без гарантии": [
                    {"id": 1617, "name": "TikTok Просмотры [Моментальный старт] [Без гарантии ⛔]"},
                ]
            },
            "Лайки": {
                "С гарантией": [
                    {"id": 172, "name": "⭐️ TikTok Лайки [Моментальные] [Гарантия 30 дней♻️]"},
                ],
                "Без гарантии": [
                    {"id": 110, "name": "⭐️ TikTok Лайки [Моментальные] [Без гарантии⛔️]"},
                ]
            },
            "Репосты/Сохранения": {
                "Все": [
                    {"id": 1640, "name": "TikTok Поделиться [Без списаний]"},
                    {"id": 1641, "name": "TikTok Сохранения [Без списаний ♻️]"},
                ]
            }
        }
    }
}

# ===== ЗАПУСК =====
if __name__ == "__main__":
    import threading
    
    print("🚀 Бот NekroKrutka запущен!")
    print(f"👤 Админ: {ADMIN_ID}")
    print(f"📱 Бот: @{BOT_USERNAME}")
    print(f"📢 Канал: {CHANNEL_ID}")
    
    monitor_thread = threading.Thread(target=check_orders_status, daemon=True)
    monitor_thread.start()
    print("🔄 Мониторинг статусов запущен!")
    
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host='0.0.0.0', port=port)
