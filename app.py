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
import io

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================================================
# 1. КОНФИГ
# ==================================================
TOKEN = os.getenv("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("❌ TELEGRAM_TOKEN не найден!")

API_KEY = "Tv2GrTBsyJXEBRwgUHmcUY9Gd5KnOgIA9zX5Vn3f3dAkqFgwLefrMdKVATwN"
API_URL = "https://kuzya-boost.ru/api/v2"
ADMIN_ID = 593150935
BOT_USERNAME = "NekroKrutka_rabot"
CHANNEL_ID = "@repaBotaNakruta"
CRYPTOBOT_TOKEN = os.getenv("CRYPTOBOT_TOKEN")

bot = telebot.TeleBot(TOKEN)
session = requests.Session()
session.verify = False
session.headers.update({'User-Agent': 'Mozilla/5.0'})

print("✅ Бот инициализирован")

# ==================================================
# 2. FLASK (ВЕБХУКИ)
# ==================================================
flask_app = Flask(__name__)

@flask_app.route('/')
def index():
    return "🤖 Бот NekroKrutka работает!"

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    try:
        json_data = request.get_json()
        update = telebot.types.Update.de_json(json_data)
        if update:
            bot.process_new_updates([update])
        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        print(f"❌ Ошибка webhook: {e}")
        return jsonify({'status': 'error'}), 500

@flask_app.route('/crypto_webhook', methods=['POST'])
def crypto_webhook():
    try:
        data = request.get_json()
        if data.get('status') == 'paid':
            payload = json.loads(data.get('payload', '{}'))
            user_id = int(payload.get('user_id'))
            amount_rub = float(payload.get('amount_rub'))
            
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
        print(f"❌ Ошибка crypto_webhook: {e}")
        return jsonify({'status': 'error'}), 500

# ==================================================
# 3. ПОЛУЧЕНИЕ КУРСА ИЗ CRYPTOBOT
# ==================================================
def get_crypto_rates():
    """Получает актуальный курс USDT и GRAM из CryptoBot"""
    default_rates = {"USDT": 85.0, "GRAM": 140.0}

    if not CRYPTOBOT_TOKEN:
        print("⚠️ CRYPTOBOT_TOKEN не найден, используются курсы по умолчанию.")
        return default_rates

    try:
        url = "https://pay.crypt.bot/api/getExchangeRates"
        headers = {
            'Crypto-Pay-API-Token': CRYPTOBOT_TOKEN,
            'Content-Type': 'application/json'
        }
        response = requests.post(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                rates = {}
                for rate in data.get('result', []):
                    if rate.get('source') == 'USDT' and rate.get('target') == 'RUB':
                        rates['USDT'] = float(rate.get('rate', 0))
                    elif rate.get('source') == 'GRAM' and rate.get('target') == 'RUB':
                        rates['GRAM'] = float(rate.get('rate', 0))
                
                if rates.get('USDT') and rates.get('GRAM'):
                    print(f"✅ Курсы обновлены: USDT={rates['USDT']}, GRAM={rates['GRAM']}")
                    return rates
                else:
                    return default_rates
            else:
                return default_rates
        else:
            return default_rates
    except Exception as e:
        print(f"❌ Ошибка получения курсов: {e}")
        return default_rates

# ==================================================
# 4. БАЗА ДАННЫХ
# ==================================================
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
            has_passed_captcha INTEGER DEFAULT 0,
            settings TEXT DEFAULT '{"lang":"ru","notifications":1}'
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

# ==================================================
# 5. ОСНОВНЫЕ ФУНКЦИИ
# ==================================================
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
    elif total_spent >= 150:
        return "vip"
    elif total_spent >= 50:
        return "advanced"
    else:
        return "novice"

def get_user_discount(user_id):
    levels = {
        "novice": 0,
        "advanced": 3.5,
        "vip": 5,
        "reseller": 10
    }
    return levels.get(get_user_level(user_id), 0)

def is_user_blocked(user_id):
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('SELECT is_blocked FROM users WHERE user_id = ?', (user_id,))
    result = cur.fetchone()
    conn.close()
    return result[0] == 1 if result else False

def block_user(user_id):
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('UPDATE users SET is_blocked = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def unblock_user(user_id):
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('UPDATE users SET is_blocked = 0 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def set_reseller_status(user_id, value):
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('UPDATE users SET is_reseller = ? WHERE user_id = ?', (value, user_id))
    conn.commit()
    conn.close()

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
    markup = 10 if price < 5 else 20 if price < 20 else 30 if price < 50 else 50
    return price + markup

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

def generate_promo_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

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
    cur.execute('INSERT INTO promocode_uses (promo_id, user_id, used_at) VALUES (?, ?, ?)',
                (promo_id, user_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()
    
    return {'success': True, 'message': f'✅ Промокод активирован!\n\n🎁 Бонус: {bonus_text}'}

def deactivate_promo_code(promo_id):
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('UPDATE promocodes SET is_active = 0 WHERE id = ?', (promo_id,))
    conn.commit()
    conn.close()

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

def get_service_category_path(service_id):
    for platform_name, platform in SERVICES.items():
        for category_name, category in platform["categories"].items():
            for subcategory_name, services in category.items():
                for service in services:
                    if service["id"] == service_id:
                        return {
                            'platform': platform['name'],
                            'category': category_name,
                            'subcategory': subcategory_name
                        }
    return None

def check_orders_status():
    while True:
        try:
            conn = sqlite3.connect('bot.db')
            cur = conn.cursor()
            cur.execute('''
                SELECT id, user_id, order_id, service_name, quantity, price, status
                FROM orders 
                WHERE status IN ('pending', 'выполняется', 'Awaiting', 'In progress')
            ''')
            orders = cur.fetchall()
            for order in orders:
                db_id, user_id, order_id, service_name, quantity, price, status = order
                result = get_order_status_api(order_id)
                if 'error' not in result:
                    new_status = result.get('status', 'Unknown')
                    status_display = {
                        'In progress': 'выполняется',
                        'Completed': 'выполнен ✅',
                        'Awaiting': 'ожидает',
                        'Canceled': 'отменён ❌',
                        'Fail': 'ошибка ❌',
                        'Partial': 'частично выполнен ⚠️'
                    }.get(new_status, new_status)
                    if status_display != status:
                        cur.execute('UPDATE orders SET status = ?, last_check = ? WHERE id = ?',
                                   (status_display, datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), db_id))
                        conn.commit()
                        if new_status in ['Completed', 'Canceled', 'Fail']:
                            try:
                                bot.send_message(
                                    user_id,
                                    f"📢 Статус заказа обновлён!\n\n"
                                    f"📦 {service_name}\n"
                                    f"📊 {quantity} шт | 💰 {price:.2f} руб\n"
                                    f"📌 Новый статус: {status_display}"
                                )
                            except:
                                pass
            conn.close()
        except Exception as e:
            print(f"Ошибка мониторинга: {e}")
        time.sleep(60)

# ==================================================
# 6. СТРУКТУРА УСЛУГ
# ==================================================
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

# ==================================================
# 7. ГЛАВНОЕ МЕНЮ
# ==================================================
def get_main_menu_keyboard(user_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_balance = types.InlineKeyboardButton("💰 Баланс", callback_data="balance")
    btn_buy = types.InlineKeyboardButton("🛒 Купить накрутку", callback_data="buy_menu")
    btn_refill = types.InlineKeyboardButton("🔄 Рефилл", callback_data="refill")
    btn_history = types.InlineKeyboardButton("📜 История заказов", callback_data="history")
    btn_reviews = types.InlineKeyboardButton("⭐️ Отзывы", callback_data="reviews_menu")
    btn_help = types.InlineKeyboardButton("❓ Помощь", callback_data="help")
    btn_ref = types.InlineKeyboardButton("👥 Реферальная программа", callback_data="ref_program")
    btn_promo = types.InlineKeyboardButton("🎫 Промокод", callback_data="promo_menu")
    btn_settings = types.InlineKeyboardButton("⚙️ Настройки", callback_data="settings_menu")
    btn_level = types.InlineKeyboardButton("📊 Мой уровень", callback_data="my_level")
    
    if user_id == ADMIN_ID:
        btn_admin = types.InlineKeyboardButton("🛡️ Админ-панель", callback_data="admin_panel")
        markup.add(btn_balance, btn_buy, btn_refill, btn_history, btn_reviews, btn_help, btn_ref, btn_promo, btn_settings, btn_level, btn_admin)
    else:
        markup.add(btn_balance, btn_buy, btn_refill, btn_history, btn_reviews, btn_help, btn_ref, btn_promo, btn_settings, btn_level)
    
    return markup

# ==================================================
# 8. КОМАНДА /START
# ==================================================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    
    if is_user_blocked(user_id):
        bot.send_message(message.chat.id, "⛔ Ваш аккаунт заблокирован!")
        return
    
    print(f"✅ /start от {user_id}")
    username = message.from_user.username or "Неизвестно"
    
    referrer_id = None
    has_ref_param = False
    if len(message.text.split()) > 1:
        param = message.text.split()[1]
        if param.startswith("ref_"):
            has_ref_param = True
            try:
                referrer_id = int(param.split("_")[1])
            except:
                pass
    
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('SELECT user_id, has_passed_captcha FROM users WHERE user_id = ?', (user_id,))
    existing = cur.fetchone()
    
    if not existing:
        discount_expiry = (datetime.datetime.now() + datetime.timedelta(hours=48)).strftime("%Y-%m-%d %H:%M")
        cur.execute('''
            INSERT INTO users (user_id, username, reg_date, referred_by, discount_expiry)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, username, datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), referrer_id, discount_expiry))
        conn.commit()
        conn.close()
        
        if referrer_id and referrer_id != user_id:
            markup = types.InlineKeyboardMarkup()
            btn_captcha = types.InlineKeyboardButton("✅ Я человек", callback_data=f"captcha_{referrer_id}")
            markup.add(btn_captcha)
            
            bot.send_message(
                message.chat.id,
                "👋 Привет! Подтверди, что ты человек, чтобы получить бонус за рефералку:",
                reply_markup=markup
            )
            return
        
        show_channels_and_menu(message.chat.id, user_id)
        return
    
    conn.close()
    
    if has_ref_param and not existing[1]:
        markup = types.InlineKeyboardMarkup()
        btn_captcha = types.InlineKeyboardButton("✅ Я человек", callback_data=f"captcha_{referrer_id}")
        markup.add(btn_captcha)
        
        bot.send_message(
            message.chat.id,
            "👋 Привет! Подтверди, что ты человек, чтобы получить бонус за рефералку:",
            reply_markup=markup
        )
        return
    
    show_channels_and_menu(message.chat.id, user_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith("captcha_"))
def captcha_handler(call):
    user_id = call.from_user.id
    referrer_id = int(call.data.split("_")[1])
    
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('UPDATE users SET has_passed_captcha = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('SELECT user_id FROM users WHERE user_id = ?', (referrer_id,))
    if cur.fetchone():
        cur.execute('UPDATE users SET coins = coins + 100 WHERE user_id = ?', (referrer_id,))
        conn.commit()
        
        try:
            bot.send_message(
                referrer_id,
                f"🎉 Новый реферал!\n\n"
                f"👤 Пользователь подтвердил, что он человек!\n"
                f"💰 Вы получили 100 монет!"
            )
        except:
            pass
    conn.close()
    
    bot.answer_callback_query(call.id, "✅ Подтверждено!")
    bot.delete_message(call.message.chat.id, call.message.message_id)
    show_channels_and_menu(call.message.chat.id, user_id)

def show_channels_and_menu(chat_id, user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("📢 Канал с новостями", url="https://t.me/NekroChanell")
    btn2 = types.InlineKeyboardButton("📢 Канал с отзывами", url="https://t.me/repaBotaNakruta")
    btn_menu = types.InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_start")
    markup.add(btn1, btn2, btn_menu)
    
    bot.send_message(
        chat_id,
        "📢 **Подпишись на каналы, чтобы быть в курсе!**\n\n"
        "• Канал с новостями о боте\n"
        "• Канал с отзывами пользователей\n\n"
        "После подписки нажми 'Главное меню' 👇",
        parse_mode="Markdown",
        reply_markup=markup
    )

# ==================================================
# 9. ОБРАБОТЧИКИ КНОПОК
# ==================================================
@bot.callback_query_handler(func=lambda call: True)
def main_callback_handler(call):
    user_id = call.from_user.id
    
    if is_user_blocked(user_id) and call.data != "back_to_start":
        bot.answer_callback_query(call.id, "⛔ Ваш аккаунт заблокирован!")
        return
    
    print(f"📩 Нажата кнопка: {call.data} от {user_id}")
    
    # ----- МОЙ УРОВЕНЬ -----
    if call.data == "my_level":
        level = get_user_level(user_id)
        levels_ru = {
            "novice": "🟢 Новичок",
            "advanced": "🟡 Продвинутый",
            "vip": "🔴 VIP",
            "reseller": "⚫ Реселлер"
        }
        discount = get_user_discount(user_id)
        total_spent = 0
        conn = sqlite3.connect('bot.db')
        cur = conn.cursor()
        cur.execute('SELECT total_spent FROM users WHERE user_id = ?', (user_id,))
        result = cur.fetchone()
        if result:
            total_spent = result[0]
        conn.close()
        
        text = f"📊 **Твой уровень:** {levels_ru.get(level, 'Новичок')}\n"
        text += f"📉 **Скидка:** {discount}%\n"
        text += f"💰 **Потрачено:** {total_spent:.2f} руб.\n\n"
        
        # ОПИСАНИЕ ВСЕХ УРОВНЕЙ
        text += "━" * 25 + "\n\n"
        text += "📊 **ВСЕ УРОВНИ:**\n\n"
        text += "🟢 **Новичок** — 0% скидка\n"
        text += "   ➜ Доступен сразу после регистрации\n\n"
        text += "🟡 **Продвинутый** — 3.5% скидка\n"
        text += "   ➜ Потрать **50 руб** в боте\n\n"
        text += "🔴 **VIP** — 5% скидка\n"
        text += "   ➜ Потрать **150 руб** в боте\n\n"
        text += "⚫ **Реселлер** — 10% скидка\n"
        text += "   ➜ Выдаётся администратором\n\n"
        
        if level == "novice":
            text += "⬆️ Потрать **50 руб**, чтобы получить уровень **Продвинутый** (3.5% скидка)"
        elif level == "advanced":
            text += "⬆️ Потрать **150 руб**, чтобы получить уровень **VIP** (5% скидка)"
        elif level == "vip":
            text += "⬆️ Попроси админа выдать уровень **Реселлер** (10% скидка)"
        else:
            text += "🏆 Ты на максимальном уровне!"
        
        markup = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")
        markup.add(btn_back)
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    # ----- БАЛАНС -----
    elif call.data == "balance":
        balance = get_user_balance(user_id)
        coins = get_user_coins(user_id)
        level = get_user_level(user_id)
        levels_ru = {
            "novice": "🟢 Новичок",
            "advanced": "🟡 Продвинутый",
            "vip": "🔴 VIP",
            "reseller": "⚫ Реселлер"
        }
        level_name = levels_ru.get(level, "Новичок")
        discount = get_user_discount(user_id)
        
        markup = types.InlineKeyboardMarkup()
        btn_deposit = types.InlineKeyboardButton("💳 Пополнить", callback_data="deposit")
        markup.add(btn_deposit)
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            f"💰 **Твой баланс:** {balance:.2f} руб.\n"
            f"🪙 **Монеты:** {coins}\n"
            f"📊 **Уровень:** {level_name}\n"
            f"📉 **Скидка:** {discount}%\n\n"
            f"💳 Для пополнения нажми кнопку ниже.",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    # ----- ПОПОЛНЕНИЕ -----
    elif call.data == "deposit":
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_crypto = types.InlineKeyboardButton("💳 CryptoBot", callback_data="deposit_crypto")
        btn_stars = types.InlineKeyboardButton("⭐️ Звёзды", callback_data="deposit_stars")
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="balance")
        markup.add(btn_crypto, btn_stars, btn_back)
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "💳 **Выбери способ пополнения:**",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    # ----- CRYPTOBOT -----
    elif call.data == "deposit_crypto":
        rates = get_crypto_rates()
        
        markup = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="deposit")
        markup.add(btn_back)
        
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            f"💳 **Пополнение через CryptoBot**\n\n"
            f"💰 Актуальные курсы (CryptoBot):\n"
            f"• USDT — 1 USDT = {rates['USDT']} руб\n"
            f"• Gram (GRAM) — 1 GRAM = {rates['GRAM']} руб\n\n"
            f"💳 **Твой доход:**\n"
            f"• С USDT: +10 руб с каждой единицы\n"
            f"• С GRAM: +15 руб с каждой единицы\n\n"
            f"📌 Минимальная сумма: 10 руб\n"
            f"📌 Максимальная сумма: 10000 руб\n\n"
            f"💳 Введите сумму в рублях:",
            parse_mode="Markdown",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_crypto_deposit)
    
    # ----- ЗВЁЗДЫ -----
    elif call.data == "deposit_stars":
        markup = types.InlineKeyboardMarkup(row_width=3)
        btns = [15, 25, 50, 75, 100, 150, 200, 350, 500]
        for val in btns:
            markup.add(types.InlineKeyboardButton(f"{val} ⭐️", callback_data=f"stars_{val}"))
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="deposit"))
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "⭐️ **Пополнение звёздами**\n\n"
            "💰 1 звезда = 0.80 руб\n"
            "📌 Выбери сумму:",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    elif call.data.startswith("stars_"):
        stars = call.data.split("_")[1]
        markup = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="deposit_stars")
        markup.add(btn_back)
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            f"⭐️ **Скиньте {stars} звёзд админу @nekrophoros**\n\n"
            f"✅ После получения звёзд баланс будет пополнен!",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    # ----- КУПИТЬ НАКРУТКУ -----
    elif call.data == "buy_menu":
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_tg = types.InlineKeyboardButton("✈️ Telegram", callback_data="platform_telegram")
        btn_tt = types.InlineKeyboardButton("📱 TikTok", callback_data="platform_tiktok")
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")
        markup.add(btn_tg, btn_tt, btn_back)
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "🛒 **Выбери платформу:**",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    elif call.data.startswith("platform_"):
        platform = call.data.split("_")[1]
        platform_data = SERVICES.get(platform)
        if not platform_data:
            bot.answer_callback_query(call.id, "❌ Ошибка")
            return
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        for category_name in platform_data["categories"].keys():
            btn = types.InlineKeyboardButton(
                f"📌 {category_name}",
                callback_data=f"category_{platform}_{category_name}"
            )
            markup.add(btn)
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="buy_menu")
        markup.add(btn_back)
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            f"📂 **{platform_data['name']} — выбери категорию:**",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    elif call.data.startswith("category_"):
        _, platform, category = call.data.split("_", 2)
        platform_data = SERVICES.get(platform)
        if not platform_data or category not in platform_data["categories"]:
            bot.answer_callback_query(call.id, "❌ Ошибка")
            return
        
        subcategories = platform_data["categories"][category]
        markup = types.InlineKeyboardMarkup(row_width=1)
        for sub_name in subcategories.keys():
            btn = types.InlineKeyboardButton(
                f"🔹 {sub_name}",
                callback_data=f"sub_{platform}_{category}_{sub_name}"
            )
            markup.add(btn)
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data=f"platform_{platform}")
        markup.add(btn_back)
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            f"📂 **{category} — выбери тип:**",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    elif call.data.startswith("sub_"):
        _, platform, category, subcategory = call.data.split("_", 3)
        services_list = SERVICES[platform]["categories"][category][subcategory]
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        for service in services_list:
            btn = types.InlineKeyboardButton(
                f"🛒 {service['name']}",
                callback_data=f"service_{service['id']}"
            )
            markup.add(btn)
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data=f"category_{platform}_{category}")
        markup.add(btn_back)
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "📦 **Выбери услугу:**",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    elif call.data.startswith("service_"):
        service_id = int(call.data.split("_")[1])
        service_name = get_service_name_by_id(service_id)
        price_with_markup = get_service_price_with_markup(service_id)
        category_path = get_service_category_path(service_id)
        guarantee_info = parse_guarantee(service_name)
        
        if price_with_markup is None:
            bot.answer_callback_query(call.id, "❌ Ошибка получения цены!")
            return
        
        text = f"📦 **{service_name}**\n\n"
        text += f"📊 1000 единиц — {price_with_markup:.2f} руб.\n"
        
        if guarantee_info['has_guarantee']:
            text += f"⏳ Гарантия: {guarantee_info['guarantee_text']} (Рефилл доступен)\n"
        else:
            if guarantee_info['guarantee_text'] == 'Не указана':
                text += f"⏳ Гарантия: Не указана\n"
            else:
                text += f"⏳ Гарантия: Нет (Рефилл недоступен)\n"
        
        if category_path:
            text += f"📌 Категория: {category_path['platform']} → {category_path['category']} → {category_path['subcategory']}\n"
        
        # ДОБАВЛЯЕМ ТЕКСТ ПРО ПУБЛИЧНЫЙ КАНАЛ И ПОМОЩЬ
        text += "\n" + "━" * 25 + "\n\n"
        text += "📢 **Важно!**\n"
        text += "🔗 Ссылка должна вести на **публичный канал**.\n"
        text += "❓ В случае проблем с накруткой нажмите кнопку ❓ Помощь\n"
        text += "в главном меню и вызовите администратора.\n"
        text += "📞 Либо просто напишите администратору @nekrophoros\n"
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_buy = types.InlineKeyboardButton("🛒 Купить", callback_data=f"buy_service_{service_id}")
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_services")
        markup.add(btn_buy, btn_back)
        
        if not hasattr(bot, 'temp_data'):
            bot.temp_data = {}
        bot.temp_data[user_id] = {"service_id": service_id}
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    elif call.data.startswith("buy_service_"):
        service_id = int(call.data.split("_")[2])
        if not hasattr(bot, 'temp_data') or user_id not in bot.temp_data:
            bot.temp_data[user_id] = {"service_id": service_id}
        
        markup = types.InlineKeyboardMarkup()
        btn_cancel = types.InlineKeyboardButton("❌ Отмена", callback_data="back_to_services")
        markup.add(btn_cancel)
        
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "📝 **Введите количество (от 1 до 100000):**",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_quantity)
    
    elif call.data == "back_to_services":
        if hasattr(bot, 'temp_data') and user_id in bot.temp_data:
            del bot.temp_data[user_id]
        bot.answer_callback_query(call.id)
        buy_menu(call)
    
    # ----- ИСТОРИЯ -----
    elif call.data == "history":
        conn = sqlite3.connect('bot.db')
        cur = conn.cursor()
        cur.execute('''
            SELECT service_name, quantity, price, status, date, order_id
            FROM orders 
            WHERE user_id = ? 
            ORDER BY id DESC 
            LIMIT 20
        ''', (user_id,))
        orders = cur.fetchall()
        conn.close()
        
        if not orders:
            text = "📜 У тебя пока нет заказов."
        else:
            text = "📜 **Твои заказы:**\n\n"
            for order in orders:
                status_emoji = {
                    'pending': '⏳',
                    'выполняется': '🔄',
                    'выполнен ✅': '✅',
                    'отменён ❌': '❌',
                    'ошибка ❌': '❌'
                }.get(order[3], '❓')
                text += f"{status_emoji} **{order[0]}**\n"
                text += f"📊 {order[1]} шт | 💰 {order[2]:.2f} руб.\n"
                text += f"🆔 ID: {order[5]}\n"
                text += f"📅 {order[4]}\n\n"
        
        markup = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")
        markup.add(btn_back)
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    # ----- РЕФИЛЛ -----
    elif call.data == "refill":
        refillable_orders = get_refillable_orders(user_id)
        refill_info = "ℹ️ Рефилл доступен только если с момента выполнения заказа прошло 24 часа ⏳ и услуга была с гарантией 🛡️\n\n"
        
        if not refillable_orders:
            markup = types.InlineKeyboardMarkup()
            btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")
            markup.add(btn_back)
            
            bot.answer_callback_query(call.id)
            bot.edit_message_text(
                f"🔄 **Рефилл**\n\n{refill_info}У вас нет заказов для рефилла.",
                call.message.chat.id,
                call.message.message_id,
                parse_mode="Markdown",
                reply_markup=markup
            )
            return
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        for order in refillable_orders:
            btn = types.InlineKeyboardButton(
                f"🔄 {order['service_name'][:25]}...",
                callback_data=f"refill_order_{order['id']}"
            )
            markup.add(btn)
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")
        markup.add(btn_back)
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            f"🔄 **Выбери заказ для рефилла:**\n\n{refill_info}",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    elif call.data.startswith("refill_order_"):
        order_db_id = int(call.data.split("_")[2])
        
        conn = sqlite3.connect('bot.db')
        cur = conn.cursor()
        cur.execute('SELECT service_name, order_id FROM orders WHERE id = ? AND user_id = ?', (order_db_id, user_id))
        order = cur.fetchone()
        conn.close()
        
        if not order:
            bot.answer_callback_query(call.id, "❌ Заказ не найден!")
            return
        
        service_name, api_order_id = order
        result = refill_order_api(api_order_id)
        
        if 'error' in result:
            bot.answer_callback_query(call.id, f"❌ Ошибка: {result['error']}")
            return
        
        bot.answer_callback_query(call.id, "✅ Рефилл отправлен!")
        bot.edit_message_text(
            f"🔄 **Рефилл отправлен!**\n📦 {service_name}",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown"
        )
    
    # ----- ОТЗЫВЫ -----
    elif call.data == "reviews_menu":
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_add = types.InlineKeyboardButton("✏️ Оставить отзыв", callback_data="review_add")
        btn_show = types.InlineKeyboardButton("📝 Посмотреть отзывы", callback_data="review_show")
        btn_channel = types.InlineKeyboardButton("📢 Отзывы в канале", url="https://t.me/repaBotaNakruta")
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")
        markup.add(btn_add, btn_show, btn_channel, btn_back)
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "⭐️ **Отзывы**",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    elif call.data == "review_add":
        conn = sqlite3.connect('bot.db')
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM reviews WHERE user_id = ? AND is_approved = 1', (user_id,))
        count = cur.fetchone()[0]
        conn.close()
        
        if count > 0:
            bot.answer_callback_query(call.id, "❌ Ты уже оставлял отзыв!")
            return
        
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "✏️ **Напиши отзыв в формате:** `5 Текст отзыва`",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_review)
    
    elif call.data == "review_show":
        conn = sqlite3.connect('bot.db')
        cur = conn.cursor()
        cur.execute('SELECT username, rating, review_text, date FROM reviews WHERE is_approved = 1 ORDER BY id DESC LIMIT 10')
        reviews = cur.fetchall()
        conn.close()
        
        if not reviews:
            text = "📝 Отзывов пока нет."
        else:
            text = "⭐️ **Отзывы:**\n\n"
            for username, rating, review_text, date in reviews:
                text += f"{'⭐' * rating} **{username}**\n"
                text += f"📝 {review_text}\n"
                text += f"📅 {date}\n\n"
        
        markup = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="reviews_menu")
        markup.add(btn_back)
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    # ----- ПОМОЩЬ -----
    elif call.data == "help":
        markup = types.InlineKeyboardMarkup()
        btn_admin = types.InlineKeyboardButton("📞 Вызвать админа", callback_data="call_admin")
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")
        markup.add(btn_admin, btn_back)
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "❓ **Помощь**\n\n"
            "Если есть проблема — вызови админа.\n"
            "📞 Либо просто напишите администратору @nekrophoros",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    elif call.data == "call_admin":
        conn = sqlite3.connect('bot.db')
        cur = conn.cursor()
        cur.execute('INSERT OR REPLACE INTO admin_chats (user_id, active, start_time) VALUES (?, ?, ?)',
                    (user_id, 1, datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        conn.close()
        
        bot.send_message(ADMIN_ID, f"📞 Вызов админа!\n👤 {call.from_user.first_name}\n🆔 ID: {user_id}")
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "✅ Администратор вызван!",
            call.message.chat.id,
            call.message.message_id
        )
    
    # ----- РЕФЕРАЛКА -----
    elif call.data == "ref_program":
        coins = get_user_coins(user_id)
        count, referrals = get_referral_stats(user_id)
        ref_link = get_ref_link(user_id)
        
        text = f"👥 **Реферальная программа**\n\n"
        text += f"💰 **Ваши монеты:** {coins}\n"
        text += f"👤 **Приглашено:** {count} человек\n\n"
        
        if referrals:
            text += "📋 **Ваши рефералы:**\n"
            for referee_id, date in referrals[:10]:
                conn = sqlite3.connect('bot.db')
                cur = conn.cursor()
                cur.execute('SELECT username FROM users WHERE user_id = ?', (referee_id,))
                result = cur.fetchone()
                conn.close()
                username = result[0] if result else "Неизвестно"
                text += f"• {username} — {date}\n"
        else:
            text += "📋 У вас пока нет рефералов.\n"
        
        text += f"\n🔗 **Ваша ссылка:**\n`{ref_link}`\n\n"
        text += "📌 **Как это работает:**\n"
        text += "• Пригласите друга по ссылке\n"
        text += "• Он получит **10% скидку** на первую покупку (48 часов)\n"
        text += "• Вы получите **100 монет** за каждого друга!\n\n"
        text += "🪙 **Обмен монет:**\n"
        text += "Монеты можно обменять на бесплатные услуги!"
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_share = types.InlineKeyboardButton("📤 Поделиться ссылкой", callback_data="share_ref_link")
        btn_shop = types.InlineKeyboardButton("🪙 Обмен монет", callback_data="coins_shop")
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")
        markup.add(btn_share, btn_shop, btn_back)
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    elif call.data == "share_ref_link":
        ref_link = get_ref_link(user_id)
        
        markup = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="ref_program")
        markup.add(btn_back)
        
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            f"📤 **Поделитесь ссылкой с друзьями!**\n\n"
            f"Отправьте эту ссылку друзьям:\n"
            f"`{ref_link}`\n\n"
            f"Они получат **10% скидку** на первую покупку!\n"
            f"А вы получите **100 монет** за каждого друга!",
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    # ----- ОБМЕН МОНЕТ -----
    elif call.data == "coins_shop":
        coins = get_user_coins(user_id)
        
        COINS_SHOP = {
            "telegram_subscribers": {
                "name": "🎁 Telegram Подписчики",
                "id": 1537,
                "quantity": 100,
                "coins": 200,
                "description": "100 подписчиков"
            },
            "telegram_positive": {
                "name": "🎁 Telegram Позитивные Реакции",
                "id": 1558,
                "quantity": 50,
                "coins": 200,
                "description": "50 позитивных реакций"
            },
            "telegram_negative": {
                "name": "🎁 Telegram Негативные Реакции",
                "id": 1559,
                "quantity": 50,
                "coins": 200,
                "description": "50 негативных реакций"
            },
            "tiktok_views": {
                "name": "🎁 TikTok Просмотры",
                "id": 119,
                "quantity": 500,
                "coins": 200,
                "description": "500 просмотров"
            },
            "tiktok_likes": {
                "name": "🎁 TikTok Лайки",
                "id": 120,
                "quantity": 100,
                "coins": 100,
                "description": "100 лайков"
            }
        }
        
        text = f"🪙 **Обмен монет**\n\n"
        text += f"💰 У вас: **{coins} монет**\n\n"
        text += "📦 **Доступные товары (ГАРАНТИИ НЕТ):**\n"
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        for key, item in COINS_SHOP.items():
            text += f"\n• **{item['name']}**\n"
            text += f"  📊 {item['description']}\n"
            text += f"  🪙 {item['coins']} монет\n"
            text += f"  ⚠️ Гарантии НЕТ\n"
            btn = types.InlineKeyboardButton(
                f"🛒 {item['name']} - {item['coins']} монет",
                callback_data=f"coin_buy_{key}"
            )
            markup.add(btn)
        
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="ref_program"))
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    elif call.data.startswith("coin_buy_"):
        key = call.data.replace("coin_buy_", "")
        
        COINS_SHOP = {
            "telegram_subscribers": {
                "name": "🎁 Telegram Подписчики",
                "id": 1537,
                "quantity": 100,
                "coins": 200,
                "description": "100 подписчиков"
            },
            "telegram_positive": {
                "name": "🎁 Telegram Позитивные Реакции",
                "id": 1558,
                "quantity": 50,
                "coins": 200,
                "description": "50 позитивных реакций"
            },
            "telegram_negative": {
                "name": "🎁 Telegram Негативные Реакции",
                "id": 1559,
                "quantity": 50,
                "coins": 200,
                "description": "50 негативных реакций"
            },
            "tiktok_views": {
                "name": "🎁 TikTok Просмотры",
                "id": 119,
                "quantity": 500,
                "coins": 200,
                "description": "500 просмотров"
            },
            "tiktok_likes": {
                "name": "🎁 TikTok Лайки",
                "id": 120,
                "quantity": 100,
                "coins": 100,
                "description": "100 лайков"
            }
        }
        
        if key not in COINS_SHOP:
            bot.answer_callback_query(call.id, "❌ Товар не найден!")
            return
        
        item = COINS_SHOP[key]
        coins = get_user_coins(user_id)
        
        if coins < item['coins']:
            bot.answer_callback_query(call.id, f"❌ Недостаточно монет! Нужно {item['coins']}")
            return
        
        markup = types.InlineKeyboardMarkup()
        btn_cancel = types.InlineKeyboardButton("❌ Отмена", callback_data="coins_shop")
        markup.add(btn_cancel)
        
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            f"📝 **Обмен монет**\n\n"
            f"📦 {item['name']}\n"
            f"📊 {item['description']}\n"
            f"🪙 {item['coins']} монет\n"
            f"⚠️ **Гарантии НЕТ!**\n\n"
            f"🔗 Введи ссылку для накрутки:",
            parse_mode="Markdown",
            reply_markup=markup
        )
        
        if not hasattr(bot, 'temp_data'):
            bot.temp_data = {}
        bot.temp_data[user_id] = {
            'coin_order': True,
            'service_id': item['id'],
            'service_name': item['name'],
            'quantity': item['quantity'],
            'coins_price': item['coins']
        }
        
        bot.register_next_step_handler(msg, process_coin_link)
    
    # ----- ПРОМОКОДЫ -----
    elif call.data == "promo_menu":
        markup = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")
        markup.add(btn_back)
        
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "🎫 **Введите промокод:**\n\n"
            "Промокод должен состоять из латинских букв и цифр.\n"
            "Пример: `SUMMER2026`",
            parse_mode="Markdown",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_promo_code)
    
    # ----- НАСТРОЙКИ -----
    elif call.data == "settings_menu":
        conn = sqlite3.connect('bot.db')
        cur = conn.cursor()
        cur.execute('SELECT settings FROM users WHERE user_id = ?', (user_id,))
        result = cur.fetchone()
        conn.close()
        
        if result:
            try:
                settings = json.loads(result[0])
            except:
                settings = {"lang": "ru", "notifications": 1}
        else:
            settings = {"lang": "ru", "notifications": 1}
        
        lang = "🇷🇺 Русский" if settings.get("lang") == "ru" else "🇺🇸 English"
        notif = "🔔 Включены" if settings.get("notifications") == 1 else "🔕 Отключены"
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_lang = types.InlineKeyboardButton(f"🌐 Язык: {lang}", callback_data="settings_lang")
        btn_notif = types.InlineKeyboardButton(f"🔔 Уведомления: {notif}", callback_data="settings_notif")
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")
        markup.add(btn_lang, btn_notif, btn_back)
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "⚙️ **Настройки**\n\nВыбери параметр для изменения:",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    elif call.data == "settings_lang":
        conn = sqlite3.connect('bot.db')
        cur = conn.cursor()
        cur.execute('SELECT settings FROM users WHERE user_id = ?', (user_id,))
        result = cur.fetchone()
        conn.close()
        
        try:
            settings = json.loads(result[0]) if result else {}
        except:
            settings = {}
        
        current_lang = settings.get("lang", "ru")
        new_lang = "en" if current_lang == "ru" else "ru"
        settings["lang"] = new_lang
        
        conn = sqlite3.connect('bot.db')
        cur = conn.cursor()
        cur.execute('UPDATE users SET settings = ? WHERE user_id = ?', (json.dumps(settings), user_id))
        conn.commit()
        conn.close()
        
        bot.answer_callback_query(call.id, f"✅ Язык изменён на {'Английский' if new_lang == 'en' else 'Русский'}")
        settings_menu = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="settings_menu")
        settings_menu.add(btn_back)
        bot.edit_message_text(
            "⚙️ **Настройки**\n\nЯзык изменён!",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=settings_menu
        )
    
    elif call.data == "settings_notif":
        conn = sqlite3.connect('bot.db')
        cur = conn.cursor()
        cur.execute('SELECT settings FROM users WHERE user_id = ?', (user_id,))
        result = cur.fetchone()
        conn.close()
        
        try:
            settings = json.loads(result[0]) if result else {}
        except:
            settings = {}
        
        current_notif = settings.get("notifications", 1)
        new_notif = 0 if current_notif == 1 else 1
        settings["notifications"] = new_notif
        
        conn = sqlite3.connect('bot.db')
        cur = conn.cursor()
        cur.execute('UPDATE users SET settings = ? WHERE user_id = ?', (json.dumps(settings), user_id))
        conn.commit()
        conn.close()
        
        bot.answer_callback_query(call.id, f"✅ Уведомления {'включены' if new_notif == 1 else 'отключены'}")
        settings_menu = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="settings_menu")
        settings_menu.add(btn_back)
        bot.edit_message_text(
            "⚙️ **Настройки**\n\nУведомления изменены!",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=settings_menu
        )
    
    # ----- АДМИНКА -----
    elif call.data == "admin_panel":
        if user_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Нет доступа!")
            return
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton("💰 Пополнить баланс", callback_data="admin_add_balance")
        btn2 = types.InlineKeyboardButton("🪙 Начислить монеты", callback_data="admin_add_coins")
        btn3 = types.InlineKeyboardButton("💸 Списать деньги", callback_data="admin_spend")
        btn4 = types.InlineKeyboardButton("💸 Списать монеты", callback_data="admin_spend_coins")
        btn5 = types.InlineKeyboardButton("📝 Отзывы", callback_data="admin_reviews")
        btn6 = types.InlineKeyboardButton("👥 База данных", callback_data="admin_users")
        btn7 = types.InlineKeyboardButton("📦 Заказы", callback_data="admin_orders")
        btn8 = types.InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")
        btn9 = types.InlineKeyboardButton("🎫 Промокоды", callback_data="admin_promocodes")
        btn10 = types.InlineKeyboardButton("⚫ Чёрный список", callback_data="admin_blacklist")
        btn11 = types.InlineKeyboardButton("📥 Экспорт данных", callback_data="admin_export")
        btn12 = types.InlineKeyboardButton("➕ Добавить услугу", callback_data="admin_add_service")
        btn13 = types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")
        markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8, btn9, btn10, btn11, btn12, btn13)
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "🛡️ **Админ-панель**",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    elif call.data == "admin_add_balance":
        if user_id != ADMIN_ID:
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "💰 Введи сумму и ID пользователя: `100 123456789`", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_admin_add_balance)
    
    elif call.data == "admin_add_coins":
        if user_id != ADMIN_ID:
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "🪙 **Начислить монеты**\n\nВведи количество монет и ID пользователя:\nФормат: `100 123456789`",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_admin_add_coins)
    
    elif call.data == "admin_spend":
        if user_id != ADMIN_ID:
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "💸 Введи сумму и ID пользователя для списания:\nФормат: `100 123456789`",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_admin_spend)
    
    elif call.data == "admin_spend_coins":
        if user_id != ADMIN_ID:
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "💸 Введи количество монет и ID пользователя для списания:\nФормат: `100 123456789`",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_admin_spend_coins)
    
    elif call.data == "admin_blacklist":
        if user_id != ADMIN_ID:
            return
        
        conn = sqlite3.connect('bot.db')
        cur = conn.cursor()
        cur.execute('SELECT user_id, username, is_blocked FROM users WHERE is_blocked = 1')
        blocked = cur.fetchall()
        cur.execute('SELECT user_id, username, is_blocked FROM users WHERE is_blocked = 0')
        active = cur.fetchall()
        conn.close()
        
        text = "⚫ **Чёрный список**\n\n"
        text += "🔴 **Заблокированные:**\n"
        if blocked:
            for user_id, username, _ in blocked:
                text += f"• {user_id} (@{username or 'нет'})\n"
        else:
            text += "• Нет заблокированных\n"
        
        text += "\n🟢 **Активные:**\n"
        if active:
            for user_id, username, _ in active[:10]:
                text += f"• {user_id} (@{username or 'нет'})\n"
        else:
            text += "• Нет активных\n"
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_block = types.InlineKeyboardButton("🔴 Заблокировать", callback_data="admin_block")
        btn_unblock = types.InlineKeyboardButton("🟢 Разблокировать", callback_data="admin_unblock")
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")
        markup.add(btn_block, btn_unblock, btn_back)
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    elif call.data == "admin_block":
        if user_id != ADMIN_ID:
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "🔴 Введи ID пользователя для блокировки:\nФормат: `123456789`"
        )
        bot.register_next_step_handler(msg, process_admin_block)
    
    elif call.data == "admin_unblock":
        if user_id != ADMIN_ID:
            return
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "🟢 Введи ID пользователя для разблокировки:\nФормат: `123456789`"
        )
        bot.register_next_step_handler(msg, process_admin_unblock)
    
    elif call.data == "admin_reviews":
        if user_id != ADMIN_ID:
            return
        reviews = get_pending_reviews()
        if not reviews:
            bot.answer_callback_query(call.id, "Нет новых отзывов")
            return
        
        for rev_id, user_id, username, rating, text, date in reviews:
            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.add(
                types.InlineKeyboardButton("✅ Одобрить", callback_data=f"admin_approve_{rev_id}"),
                types.InlineKeyboardButton("❌ Отклонить", callback_data=f"admin_decline_{rev_id}")
            )
            bot.send_message(call.message.chat.id, f"📝 {username} (ID: {user_id})\n⭐️ {rating}\n📝 {text}", reply_markup=markup)
        bot.answer_callback_query(call.id)
    
    elif call.data.startswith("admin_approve_"):
        if user_id != ADMIN_ID:
            return
        review_id = int(call.data.split("_")[2])
        approve_review(review_id)
        bot.answer_callback_query(call.id, "✅ Одобрено!")
    
    elif call.data.startswith("admin_decline_"):
        if user_id != ADMIN_ID:
            return
        review_id = int(call.data.split("_")[2])
        decline_review(review_id)
        bot.answer_callback_query(call.id, "❌ Отклонено!")
    
    elif call.data.startswith("admin_users"):
        if user_id != ADMIN_ID:
            return
        
        page = 0
        if call.data == "admin_users_next":
            page = bot.admin_users_page + 1
        elif call.data == "admin_users_prev":
            page = bot.admin_users_page - 1
        if page < 0:
            page = 0
        
        users, total = get_all_users(page)
        bot.admin_users_page = page
        
        if not users:
            bot.answer_callback_query(call.id, "Нет пользователей")
            return
        
        total_pages = (total + 9) // 10
        text = f"👥 **Пользователи** (стр. {page+1}/{total_pages})\n\n"
        for user in users:
            user_id, username, balance, coins, total_spent, reg_date, is_blocked = user
            status = "🔴 Заблокирован" if is_blocked else "🟢 Активен"
            text += f"🆔 {user_id}\n"
            text += f"👤 {username or 'Нет'}\n"
            text += f"🪙 {coins} монет | 💰 {balance:.2f} руб.\n"
            text += f"📊 Потрачено: {total_spent:.2f} руб.\n"
            text += f"📅 {reg_date}\n"
            text += f"📌 {status}\n\n"
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        if page > 0:
            markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_users_prev"))
        if page < total_pages - 1:
            markup.add(types.InlineKeyboardButton("Вперёд ➡️", callback_data="admin_users_next"))
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="admin_panel"))
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    elif call.data.startswith("admin_orders"):
        if user_id != ADMIN_ID:
            return
        
        page = 0
        if call.data == "admin_orders_next":
            page = bot.admin_orders_page + 1
        elif call.data == "admin_orders_prev":
            page = bot.admin_orders_page - 1
        if page < 0:
            page = 0
        
        orders, total = get_all_orders(page)
        bot.admin_orders_page = page
        
        if not orders:
            bot.answer_callback_query(call.id, "Нет заказов")
            return
        
        total_pages = (total + 9) // 10
        text = f"📦 **Заказы** (стр. {page+1}/{total_pages})\n\n"
        for order in orders:
            order_id, user_id, service_name, quantity, price, status, date, api_order_id = order
            status_emoji = {
                'pending': '⏳',
                'выполняется': '🔄',
                'выполнен ✅': '✅',
                'отменён ❌': '❌',
                'ошибка ❌': '❌'
            }.get(status, '❓')
            text += f"{status_emoji} #{api_order_id} | {user_id}\n"
            text += f"📦 {service_name[:30]}\n"
            text += f"📊 {quantity} шт | 💰 {price:.2f} руб.\n"
            text += f"📅 {date}\n\n"
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        if page > 0:
            markup.add(types.InlineKeyboardButton("⬅️ Назад", callback_data="admin_orders_prev"))
        if page < total_pages - 1:
            markup.add(types.InlineKeyboardButton("Вперёд ➡️", callback_data="admin_orders_next"))
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="admin_panel"))
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=markup)
    
    elif call.data == "admin_stats":
        if user_id != ADMIN_ID:
            return
        
        conn = sqlite3.connect('bot.db')
        cur = conn.cursor()
        
        cur.execute('SELECT COUNT(*) FROM users')
        users_count = cur.fetchone()[0]
        cur.execute('SELECT COUNT(*) FROM orders')
        orders_count = cur.fetchone()[0]
        cur.execute('SELECT SUM(price) FROM orders WHERE status = "выполнен ✅"')
        total_revenue = cur.fetchone()[0] or 0
        cur.execute('SELECT COUNT(*) FROM reviews WHERE is_approved = 0')
        pending_reviews = cur.fetchone()[0]
        cur.execute('SELECT SUM(coins) FROM users')
        total_coins = cur.fetchone()[0] or 0
        
        cur.execute('''
            SELECT user_id, username, total_spent 
            FROM users 
            ORDER BY total_spent DESC 
            LIMIT 5
        ''')
        top_users = cur.fetchall()
        
        cur.execute('''
            SELECT service_name, COUNT(*) as count, SUM(price) as total
            FROM orders 
            WHERE status = "выполнен ✅"
            GROUP BY service_name
            ORDER BY count DESC
            LIMIT 5
        ''')
        top_services = cur.fetchall()
        
        cur.execute('''
            SELECT strftime('%H', date) as hour, COUNT(*) as count
            FROM orders 
            GROUP BY hour
            ORDER BY count DESC
            LIMIT 5
        ''')
        peak_hours = cur.fetchall()
        
        conn.close()
        
        text = f"📊 **СТАТИСТИКА**\n\n"
        text += f"👤 Пользователей: {users_count}\n"
        text += f"📦 Заказов: {orders_count}\n"
        text += f"💰 Выручка: {total_revenue:.2f} руб.\n"
        text += f"🪙 Всего монет: {total_coins}\n"
        text += f"📝 Отзывов на модерации: {pending_reviews}\n\n"
        
        text += "🏆 **ТОП ПОЛЬЗОВАТЕЛЕЙ:**\n"
        for i, (user_id, username, spent) in enumerate(top_users, 1):
            text += f"{i}. {username or user_id} — {spent:.2f} руб.\n"
        
        text += "\n📌 **ТОП УСЛУГ:**\n"
        for i, (name, count, total) in enumerate(top_services, 1):
            text += f"{i}. {name[:30]} — {count} заказов ({total:.2f} руб.)\n"
        
        text += "\n⏰ **ЧАСЫ ПИК:**\n"
        for hour, count in peak_hours:
            text += f"• {hour}:00 — {count} заказов\n"
        
        markup = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")
        markup.add(btn_back)
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    elif call.data == "admin_promocodes":
        if user_id != ADMIN_ID:
            return
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton("📝 Создать промокод", callback_data="admin_promo_create")
        btn2 = types.InlineKeyboardButton("📋 Список промокодов", callback_data="admin_promo_list")
        btn3 = types.InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")
        markup.add(btn1, btn2, btn3)
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "🎫 **Управление промокодами**",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    elif call.data == "admin_promo_create":
        if user_id != ADMIN_ID:
            return
        
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            call.message.chat.id,
            "📝 **Создание промокода**\n\nВведите название промокода:\n(только латиница и цифры)\n\nИли введите `auto` для генерации случайного кода."
        )
        bot.register_next_step_handler(msg, process_admin_promo_create)
    
    elif call.data == "admin_promo_list":
        if user_id != ADMIN_ID:
            return
        
        promos = get_all_promocodes()
        if not promos:
            markup = types.InlineKeyboardMarkup()
            btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="admin_promocodes")
            markup.add(btn_back)
            
            bot.answer_callback_query(call.id)
            bot.edit_message_text(
                "📋 **Список промокодов**\n\nНет созданных промокодов.",
                call.message.chat.id,
                call.message.message_id,
                parse_mode="Markdown",
                reply_markup=markup
            )
            return
        
        text = "📋 **Список промокодов:**\n\n"
        for promo in promos:
            promo_id, code, bonus_type, bonus_amount, max_uses, used_count, expires_at, is_active = promo
            status = "🟢 Активен" if is_active else "🔴 Неактивен"
            type_names = {'rubles': '💰 руб.', 'coins': '🪙 монет', 'discount': '📉 % скидки'}
            expiry_text = "бессрочно" if not expires_at else expires_at
            
            text += f"📝 `{code}`\n"
            text += f"   {type_names.get(bonus_type, '')} {bonus_amount}\n"
            text += f"   Использован: {used_count}/{max_uses if max_uses > 0 else '∞'}\n"
            text += f"   ⏳ {expiry_text}\n"
            text += f"   {status}\n\n"
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("🔙 Назад", callback_data="admin_promocodes"))
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    elif call.data == "admin_add_service":
        if user_id != ADMIN_ID:
            return
        
        markup = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="admin_panel")
        markup.add(btn_back)
        
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "➕ **Добавление услуги**\n\n"
            "ℹ️ Добавление услуги будет доступно в следующем обновлении.\n\n"
            "Сейчас можно только редактировать файл `SERVICES` в коде.",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
    
    elif call.data == "admin_export":
        if user_id != ADMIN_ID:
            return
        
        bot.answer_callback_query(call.id, "🔄 Собираю данные...")
        
        conn = sqlite3.connect('bot.db')
        cur = conn.cursor()
        
        # Собираем все данные
        users = cur.execute('SELECT * FROM users').fetchall()
        orders = cur.execute('SELECT * FROM orders').fetchall()
        reviews = cur.execute('SELECT * FROM reviews').fetchall()
        referrals = cur.execute('SELECT * FROM referrals').fetchall()
        promocodes = cur.execute('SELECT * FROM promocodes').fetchall()
        
        conn.close()
        
        # Создаём TXT файл
        date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        
        txt_content = "=" * 50 + "\n"
        txt_content += "📊 ЭКСПОРТ ДАННЫХ NEKROKRUTKA\n"
        txt_content += f"📅 Дата: {date}\n"
        txt_content += "=" * 50 + "\n\n"
        
        txt_content += "👥 ПОЛЬЗОВАТЕЛИ:\n"
        txt_content += "-" * 30 + "\n"
        for user in users:
            txt_content += f"ID: {user[0]} | Username: {user[1]} | Баланс: {user[2]} | Монеты: {user[3]} | Потрачено: {user[9]} | Дата: {user[6]}\n"
        
        txt_content += "\n📦 ЗАКАЗЫ:\n"
        txt_content += "-" * 30 + "\n"
        for order in orders:
            txt_content += f"ID: {order[0]} | Пользователь: {order[1]} | Услуга: {order[3]} | Кол-во: {order[5]} | Цена: {order[6]} | Статус: {order[7]} | Дата: {order[9]}\n"
        
        txt_content += "\n⭐️ ОТЗЫВЫ:\n"
        txt_content += "-" * 30 + "\n"
        for review in reviews:
            txt_content += f"ID: {review[0]} | Пользователь: {review[1]} | Оценка: {review[3]} | Текст: {review[4]} | Дата: {review[5]}\n"
        
        txt_content += "\n👥 РЕФЕРАЛЫ:\n"
        txt_content += "-" * 30 + "\n"
        for referral in referrals:
            txt_content += f"Пригласитель: {referral[1]} | Приглашённый: {referral[2]} | Дата: {referral[3]}\n"
        
        txt_content += "\n🎫 ПРОМОКОДЫ:\n"
        txt_content += "-" * 30 + "\n"
        for promo in promocodes:
            txt_content += f"Код: {promo[1]} | Тип: {promo[2]} | Сумма: {promo[3]} | Лимит: {promo[4]} | Использовано: {promo[5]}\n"
        
        txt_content += "\n" + "=" * 50 + "\n"
        txt_content += "📥 КОНЕЦ ЭКСПОРТА\n"
        
        file = io.BytesIO(txt_content.encode('utf-8'))
        file.name = "backup_data.txt"
        
        bot.send_document(
            call.message.chat.id,
            file,
            caption=f"📥 **Экспорт данных**\n\n📅 Дата: {date}\n📊 Формат: TXT"
        )
    
    # ----- НАЗАД -----
    elif call.data == "back_to_start":
        back_to_start(call)
    
    else:
        bot.answer_callback_query(call.id, "⚠️ Функция временно недоступна")

# ==================================================
# 10. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==================================================
def process_quantity(message):
    user_id = message.from_user.id
    try:
        quantity = int(message.text.strip())
        if quantity < 1 or quantity > 100000:
            bot.send_message(message.chat.id, "❌ От 1 до 100000!")
            return
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введи число!")
        return
    
    if not hasattr(bot, 'temp_data') or user_id not in bot.temp_data:
        bot.send_message(message.chat.id, "❌ Ошибка! Начни заново.")
        return
    
    service_id = bot.temp_data[user_id]["service_id"]
    
    discount = 1.0
    discount_msg = ""
    
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('SELECT discount_used, discount_expiry, pending_discount FROM users WHERE user_id = ?', (user_id,))
    result = cur.fetchone()
    conn.close()
    
    if result:
        discount_used, discount_expiry, pending_discount = result
        
        if discount_used == 0 and discount_expiry:
            try:
                expiry_date = datetime.datetime.strptime(discount_expiry, "%Y-%m-%d %H:%M")
                if expiry_date > datetime.datetime.now():
                    discount = 0.9
                    discount_msg = "🎁 Скидка 10% (первая покупка) применена!"
                    conn = sqlite3.connect('bot.db')
                    cur = conn.cursor()
                    cur.execute('UPDATE users SET discount_used = 1 WHERE user_id = ?', (user_id,))
                    conn.commit()
                    conn.close()
                else:
                    conn = sqlite3.connect('bot.db')
                    cur = conn.cursor()
                    cur.execute('UPDATE users SET discount_expiry = NULL WHERE user_id = ?', (user_id,))
                    conn.commit()
                    conn.close()
            except:
                pass
        
        if pending_discount > 0:
            discount = min(discount, (100 - pending_discount) / 100)
            discount_msg += f"\n🎫 Скидка {pending_discount}% (промокод) применена!"
            conn = sqlite3.connect('bot.db')
            cur = conn.cursor()
            cur.execute('UPDATE users SET pending_discount = 0 WHERE user_id = ?', (user_id,))
            conn.commit()
            conn.close()
    
    price_with_markup = get_service_price_with_markup(service_id)
    if price_with_markup is None:
        bot.send_message(message.chat.id, "❌ Ошибка получения цены!")
        return
    
    total_price = (quantity / 1000) * price_with_markup * discount
    balance = get_user_balance(user_id)
    if balance < total_price:
        bot.send_message(
            message.chat.id,
            f"❌ **Недостаточно средств!**\n\n"
            f"💰 Баланс: {balance:.2f} руб.\n"
            f"💳 Нужно: {total_price:.2f} руб."
        )
        return
    
    if discount_msg:
        bot.send_message(message.chat.id, discount_msg)
    
    bot.temp_data[user_id]["quantity"] = quantity
    bot.temp_data[user_id]["total_price"] = total_price
    
    msg = bot.send_message(
        message.chat.id,
        "📝 **Введи ссылку:**"
    )
    bot.register_next_step_handler(msg, process_link)

def process_link(message):
    user_id = message.from_user.id
    link = message.text.strip()
    if not link.startswith(('http://', 'https://')):
        bot.send_message(message.chat.id, "❌ Ссылка должна начинаться с http:// или https://")
        return
    
    if not hasattr(bot, 'temp_data') or user_id not in bot.temp_data:
        bot.send_message(message.chat.id, "❌ Ошибка! Начни заново.")
        return
    
    data = bot.temp_data[user_id]
    service_id = data["service_id"]
    quantity = data["quantity"]
    total_price = data["total_price"]
    
    result = create_order_api(service_id, link, quantity)
    if 'error' in result or 'order' not in result:
        bot.send_message(
            message.chat.id,
            f"❌ Ошибка: {result.get('error', 'Неизвестно')}"
        )
        return
    
    order_id = result['order']
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (total_price, user_id))
    cur.execute('UPDATE users SET total_spent = total_spent + ? WHERE user_id = ?', (total_price, user_id))
    service_name = get_service_name_by_id(service_id)
    cur.execute('''
        INSERT INTO orders (user_id, service_id, service_name, link, quantity, price, status, order_id, date, last_check)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, service_id, service_name, link, quantity, total_price, 'выполняется', str(order_id),
          datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
          datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()
    
    del bot.temp_data[user_id]
    bot.send_message(
        message.chat.id,
        f"✅ **Заказ создан!**\n\n"
        f"📦 {service_name}\n"
        f"📊 {quantity} шт\n"
        f"💰 {total_price:.2f} руб.\n"
        f"🆔 ID заказа: {order_id}\n"
        f"⏳ Статус: выполняется"
    )

def process_crypto_deposit(message):
    user_id = message.from_user.id
    
    try:
        amount_rub = float(message.text.strip())
        if amount_rub < 10:
            bot.send_message(message.chat.id, "❌ Минимальная сумма: 10 руб!")
            return
        if amount_rub > 10000:
            bot.send_message(message.chat.id, "❌ Максимальная сумма: 10000 руб!")
            return
    except ValueError:
        bot.send_message(message.chat.id, "❌ Введите число!")
        return
    
    rates = get_crypto_rates()
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_usdt = types.InlineKeyboardButton(
        f"💵 USDT (1 USDT = {rates['USDT'] - 10} руб)",
        callback_data=f"crypto_usdt_{amount_rub}"
    )
    btn_gram = types.InlineKeyboardButton(
        f"🟣 Gram (1 GRAM = {rates['GRAM'] - 15} руб)",
        callback_data=f"crypto_gram_{amount_rub}"
    )
    btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="deposit")
    markup.add(btn_usdt, btn_gram, btn_back)
    
    bot.send_message(
        message.chat.id,
        f"💰 Сумма: {amount_rub:.2f} руб\n\n"
        f"💰 Актуальные курсы (CryptoBot):\n"
        f"• USDT — 1 USDT = {rates['USDT']} руб\n"
        f"• Gram (GRAM) — 1 GRAM = {rates['GRAM']} руб\n\n"
        f"💳 **Твой доход:**\n"
        f"• С USDT: +10 руб с каждой единицы\n"
        f"• С GRAM: +15 руб с каждой единицы\n\n"
        f"📌 Выбери валюту для оплаты:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("crypto_"))
def crypto_currency_selected(call):
    user_id = call.from_user.id
    data = call.data.split("_")
    currency = data[1]
    amount_rub = float(data[2])
    
    if not CRYPTOBOT_TOKEN:
        bot.answer_callback_query(call.id, "❌ CryptoBot не настроен!")
        return
    
    rates = get_crypto_rates()
    
    if currency == "USDT":
        real_rate = rates["USDT"] - 10
        amount_crypto = amount_rub / real_rate
        currency_name = "USDT"
    elif currency == "GRAM":
        real_rate = rates["GRAM"] - 15
        amount_crypto = amount_rub / real_rate
        currency_name = "GRAM"
    else:
        bot.answer_callback_query(call.id, "❌ Неизвестная валюта!")
        return
    
    amount_crypto = round(amount_crypto, 4)
    
    try:
        url = "https://api.cryptobot.app/createInvoice"
        headers = {
            'Crypto-Pay-API-Token': CRYPTOBOT_TOKEN,
            'Content-Type': 'application/json'
        }
        payload = {
            "asset": currency,
            "amount": amount_crypto,
            "description": f"Пополнение баланса NekroKrutka на {amount_rub} руб.",
            "payload": json.dumps({
                "user_id": user_id,
                "amount_rub": amount_rub,
                "real_rate": real_rate
            })
        }
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('ok'):
                invoice_id = data['result']['invoice_id']
                pay_url = data['result']['pay_url']
                
                markup = types.InlineKeyboardMarkup()
                btn_pay = types.InlineKeyboardButton("💳 Оплатить", url=pay_url)
                btn_check = types.InlineKeyboardButton("🔄 Проверить оплату", callback_data=f"check_payment_{invoice_id}")
                btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="deposit")
                markup.add(btn_pay, btn_check, btn_back)
                
                bot.answer_callback_query(call.id)
                bot.edit_message_text(
                    f"💳 **Счёт создан!**\n\n"
                    f"💰 Сумма: {amount_rub:.2f} руб\n"
                    f"💵 Валюта: {currency_name}\n"
                    f"📊 К оплате: {amount_crypto} {currency_name}\n"
                    f"📈 Курс: 1 {currency_name} = {real_rate:.2f} руб (с учётом дохода)\n\n"
                    f"1️⃣ Нажми 'Оплатить'\n"
                    f"2️⃣ Оплати через CryptoBot\n"
                    f"3️⃣ Нажми 'Проверить оплату' после оплаты\n\n"
                    f"⚠️ Если оплата не проходит, попробуй через пару минут.",
                    call.message.chat.id,
                    call.message.message_id,
                    parse_mode="Markdown",
                    reply_markup=markup
                )
                return
        print(f"❌ Ошибка CryptoBot: {response.text if response else 'Нет ответа'}")
        bot.answer_callback_query(call.id, "❌ Ошибка создания счёта! Попробуй позже.")
    except Exception as e:
        print(f"❌ Ошибка создания счёта: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка создания счёта!")

@bot.callback_query_handler(func=lambda call: call.data.startswith("check_payment_"))
def check_payment(call):
    bot.answer_callback_query(call.id, "🔄 Проверяем...")
    bot.send_message(
        call.message.chat.id,
        "🔄 Проверка оплаты...\n\n"
        "Если вы оплатили, баланс пополнится автоматически в течение минуты.\n"
        "Если оплата не пришла — попробуйте ещё раз."
    )

def process_coin_link(message):
    user_id = message.from_user.id
    link = message.text.strip()
    
    if not link.startswith(('http://', 'https://')):
        bot.send_message(message.chat.id, "❌ Ссылка должна начинаться с http:// или https://")
        return
    
    if not hasattr(bot, 'temp_data') or user_id not in bot.temp_data:
        bot.send_message(message.chat.id, "❌ Ошибка! Начните заново.")
        return
    
    data = bot.temp_data[user_id]
    if not data.get('coin_order'):
        return
    
    service_id = data['service_id']
    service_name = data['service_name']
    quantity = data['quantity']
    coins_price = data['coins_price']
    
    result = create_order_api(service_id, link, quantity)
    
    if 'error' in result or 'order' not in result:
        bot.send_message(
            message.chat.id,
            f"❌ Ошибка: {result.get('error', 'Неизвестно')}"
        )
        return
    
    order_id = result['order']
    
    conn = sqlite3.connect('bot.db')
    cur = conn.cursor()
    cur.execute('UPDATE users SET coins = coins - ? WHERE user_id = ?', (coins_price, user_id))
    cur.execute('''
        INSERT INTO orders (user_id, service_id, service_name, link, quantity, price, status, order_id, date, last_check)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, service_id, service_name, link, quantity, 0, 'выполняется', str(order_id),
          datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
          datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()
    
    del bot.temp_data[user_id]
    bot.send_message(
        message.chat.id,
        f"✅ **Заказ по монетам создан!**\n\n"
        f"📦 {service_name}\n"
        f"📊 {quantity} шт\n"
        f"🪙 Списано: {coins_price} монет\n"
        f"🆔 ID заказа: {order_id}\n"
        f"⏳ Статус: выполняется\n\n"
        f"⚠️ Напоминаем: гарантии НЕТ!"
    )

def process_promo_code(message):
    user_id = message.from_user.id
    code = message.text.strip().upper()
    
    if not re.match(r'^[A-Z0-9]+$', code):
        bot.send_message(message.chat.id, "❌ Промокод должен содержать только латинские буквы и цифры!")
        return
    
    result = use_promo_code(code, user_id)
    
    markup = types.InlineKeyboardMarkup()
    btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")
    markup.add(btn_back)
    
    bot.send_message(message.chat.id, result['message'], reply_markup=markup)

def process_admin_add_balance(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        parts = message.text.split()
        amount = float(parts[0])
        user_id = int(parts[1])
        conn = sqlite3.connect('bot.db')
        cur = conn.cursor()
        cur.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"✅ Пополнено {amount} руб. для {user_id}")
    except:
        bot.send_message(message.chat.id, "❌ Формат: `100 123456789`")

def process_admin_add_coins(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        parts = message.text.split()
        coins = int(parts[0])
        user_id = int(parts[1])
        conn = sqlite3.connect('bot.db')
        cur = conn.cursor()
        cur.execute('UPDATE users SET coins = coins + ? WHERE user_id = ?', (coins, user_id))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"✅ Начислено {coins} монет пользователю {user_id}")
    except:
        bot.send_message(message.chat.id, "❌ Формат: `100 123456789`")

def process_admin_spend(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        parts = message.text.split()
        amount = float(parts[0])
        user_id = int(parts[1])
        conn = sqlite3.connect('bot.db')
        cur = conn.cursor()
        cur.execute('UPDATE users SET balance = balance - ? WHERE user_id = ?', (amount, user_id))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"✅ Списано {amount} руб. с пользователя {user_id}")
    except:
        bot.send_message(message.chat.id, "❌ Формат: `100 123456789`")

def process_admin_spend_coins(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        parts = message.text.split()
        coins = int(parts[0])
        user_id = int(parts[1])
        conn = sqlite3.connect('bot.db')
        cur = conn.cursor()
        cur.execute('UPDATE users SET coins = coins - ? WHERE user_id = ?', (coins, user_id))
        conn.commit()
        conn.close()
        bot.send_message(message.chat.id, f"✅ Списано {coins} монет с пользователя {user_id}")
    except:
        bot.send_message(message.chat.id, "❌ Формат: `100 123456789`")

def process_admin_block(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        user_id = int(message.text.strip())
        block_user(user_id)
        bot.send_message(message.chat.id, f"✅ Пользователь {user_id} заблокирован!")
    except:
        bot.send_message(message.chat.id, "❌ Введи корректный ID!")

def process_admin_unblock(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        user_id = int(message.text.strip())
        unblock_user(user_id)
        bot.send_message(message.chat.id, f"✅ Пользователь {user_id} разблокирован!")
    except:
        bot.send_message(message.chat.id, "❌ Введи корректный ID!")

def process_admin_promo_create(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    code = message.text.strip().upper()
    if code == "AUTO":
        code = generate_promo_code()
        bot.send_message(message.chat.id, f"✅ Сгенерирован код: `{code}`", parse_mode="Markdown")
    
    if not re.match(r'^[A-Z0-9]+$', code):
        bot.send_message(message.chat.id, "❌ Только латиница и цифры!")
        return
    
    if not hasattr(bot, 'temp_promo'):
        bot.temp_promo = {}
    bot.temp_promo[message.from_user.id] = {'code': code}
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("💰 Рубли", callback_data="promo_type_rubles")
    btn2 = types.InlineKeyboardButton("🪙 Монеты", callback_data="promo_type_coins")
    btn3 = types.InlineKeyboardButton("📉 Скидка %", callback_data="promo_type_discount")
    markup.add(btn1, btn2, btn3)
    
    bot.send_message(
        message.chat.id,
        f"📝 Выберите тип бонуса для промокода `{code}`:",
        parse_mode="Markdown",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("promo_type_"))
def admin_promo_type(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    bonus_type = call.data.replace("promo_type_", "")
    user_id = call.from_user.id
    
    if not hasattr(bot, 'temp_promo') or user_id not in bot.temp_promo:
        bot.answer_callback_query(call.id, "❌ Ошибка! Начните заново.")
        return
    
    bot.temp_promo[user_id]['bonus_type'] = bonus_type
    
    type_names = {'rubles': 'рублей', 'coins': 'монет', 'discount': '% скидки'}
    bot.answer_callback_query(call.id)
    
    msg = bot.send_message(
        call.message.chat.id,
        f"📝 Введите количество {type_names.get(bonus_type, '')}:"
    )
    bot.register_next_step_handler(msg, admin_promo_amount)

def admin_promo_amount(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            bot.send_message(message.chat.id, "❌ Количество должно быть больше 0!")
            return
    except:
        bot.send_message(message.chat.id, "❌ Введите число!")
        return
    
    user_id = message.from_user.id
    if not hasattr(bot, 'temp_promo') or user_id not in bot.temp_promo:
        bot.send_message(message.chat.id, "❌ Ошибка! Начните заново.")
        return
    
    bot.temp_promo[user_id]['amount'] = amount
    bot.send_message(
        message.chat.id,
        "📝 Введите максимальное количество активаций:\n(0 = безлимит)"
    )
    bot.register_next_step_handler(message, admin_promo_max_uses)

def admin_promo_max_uses(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        max_uses = int(message.text.strip())
        if max_uses < 0:
            bot.send_message(message.chat.id, "❌ Не может быть отрицательным!")
            return
    except:
        bot.send_message(message.chat.id, "❌ Введите число!")
        return
    
    user_id = message.from_user.id
    if not hasattr(bot, 'temp_promo') or user_id not in bot.temp_promo:
        bot.send_message(message.chat.id, "❌ Ошибка! Начните заново.")
        return
    
    bot.temp_promo[user_id]['max_uses'] = max_uses
    bot.send_message(
        message.chat.id,
        "📝 Введите дату истечения (в формате `ДД.ММ.ГГГГ ЧЧ:ММ`)\nили введите `0` для бессрочного действия:"
    )
    bot.register_next_step_handler(message, admin_promo_expiry)

def admin_promo_expiry(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    expiry_input = message.text.strip()
    
    if expiry_input == "0":
        expires_at = None
    else:
        try:
            dt = datetime.datetime.strptime(expiry_input, "%d.%m.%Y %H:%M")
            expires_at = dt.strftime("%Y-%m-%d %H:%M")
        except:
            bot.send_message(message.chat.id, "❌ Неправильный формат! Используйте `ДД.ММ.ГГГГ ЧЧ:ММ`")
            return
    
    user_id = message.from_user.id
    if not hasattr(bot, 'temp_promo') or user_id not in bot.temp_promo:
        bot.send_message(message.chat.id, "❌ Ошибка! Начните заново.")
        return
    
    data = bot.temp_promo[user_id]
    code = data['code']
    bonus_type = data['bonus_type']
    amount = data['amount']
    max_uses = data['max_uses']
    
    if create_promo_code(code, bonus_type, amount, max_uses, expires_at):
        type_names = {'rubles': 'рублей', 'coins': 'монет', 'discount': '% скидки'}
        expiry_text = "бессрочный" if not expires_at else expires_at
        bot.send_message(
            message.chat.id,
            f"✅ **Промокод создан!**\n\n"
            f"📝 Код: `{code}`\n"
            f"🎁 Бонус: {amount} {type_names.get(bonus_type, '')}\n"
            f"📊 Макс. активаций: {max_uses if max_uses > 0 else '∞'}\n"
            f"⏳ Срок: {expiry_text}",
            parse_mode="Markdown"
        )
    else:
        bot.send_message(message.chat.id, "❌ Ошибка! Возможно, такой промокод уже существует.")
    
    del bot.temp_promo[user_id]

def buy_menu(call):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_tg = types.InlineKeyboardButton("✈️ Telegram", callback_data="platform_telegram")
    btn_tt = types.InlineKeyboardButton("📱 TikTok", callback_data="platform_tiktok")
    btn_back = types.InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")
    markup.add(btn_tg, btn_tt, btn_back)
    
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        "🛒 **Выбери платформу:**",
        call.message.chat.id,
        call.message.message_id,
        parse_mode="Markdown",
        reply_markup=markup
    )

def process_review(message):
    try:
        text = message.text.strip()
        match = re.match(r'^(\d+)\s+(.+)$', text)
        if not match:
            bot.send_message(message.chat.id, "❌ Формат: `5 Текст отзыва`")
            return
        rating = int(match.group(1))
        review_text = match.group(2)
        if rating < 1 or rating > 5:
            bot.send_message(message.chat.id, "❌ Оценка от 1 до 5!")
            return
        
        conn = sqlite3.connect('bot.db')
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO reviews (user_id, username, rating, review_text, date, is_approved)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (message.from_user.id, message.from_user.username or "Неизвестно", rating, review_text,
              datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), 0))
        conn.commit()
        conn.close()
        
        bot.send_message(message.chat.id, "✅ Отзыв отправлен на модерацию!")
        bot.send_message(ADMIN_ID, f"📢 Новый отзыв!\n👤 {message.from_user.first_name}\n⭐️ {rating}\n📝 {review_text}")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {e}")

def back_to_start(call):
    user_id = call.from_user.id
    
    markup = get_main_menu_keyboard(user_id)
    text = "🏠 **Главное меню**"
    
    try:
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
            reply_markup=markup
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

# ==================================================
# 11. ЗАПУСК
# ==================================================
if __name__ == "__main__":
    import threading

    print("🚀 Бот NekroKrutka запущен!")
    print(f"👤 Админ: {ADMIN_ID}")
    print(f"📱 Бот: @{BOT_USERNAME}")
    print(f"📢 Канал: {CHANNEL_ID}")

    try:
        bot.delete_webhook()
        print("✅ Webhook удалён!")
    except:
        pass

    webhook_url = "https://nekrokrutka-bot.onrender.com/webhook"
    bot.set_webhook(url=webhook_url)
    print(f"✅ Webhook установлен: {webhook_url}")

    monitor_thread = threading.Thread(target=check_orders_status, daemon=True)
    monitor_thread.start()
    print("🔄 Мониторинг статусов запущен!")

    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host='0.0.0.0', port=port)
