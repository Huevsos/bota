import asyncio
import logging
import sqlite3
import random
import string
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import Dice

# ========== НАСТРОЙКИ ==========
TOKEN = "8126450707:AAE1grJdi8DReGgCHJdE2MzEa7ocNVClvq8"
ADMIN_ID = 7433757951
MIN_WITHDRAWAL = 5000  # Минимальная сумма для вывода
CHANNEL_USERNAME = "@cosinxx_prime"  # Обязательный канал для подписки
CHANNEL_LINK = "https://t.me/cosinxx_prime"  # Ссылка на канал
CONTESTS_CHANNEL_ID = -1003175116993  # ID канала для конкурсов (замените на свой)

# ========== ФОТОГРАФИИ ДЛЯ РАЗДЕЛОВ ==========
BALANCE_IMAGE_URL = "https://disk.yandex.ru/i/JT8xfr8dWFmVmw"  # Фото для баланса
WITHDRAWAL_IMAGE_URL = "https://disk.yandex.ru/i/slPRl9JvJZ9kbA"  # Фото для вывода
GAMES_IMAGE_URL = "https://disk.yandex.ru/i/H01GkyACwrhJ0w"  # Фото для игр
REFERRALS_IMAGE_URL = "https://disk.yandex.ru/i/ygVsk4S_AytCHg"  # Фото для рефералов

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ========== БАЗА ДАННЫХ ==========
class Database:
    def __init__(self, db_file="project_evolution_complete.db"):
        self.db_file = db_file
        self.create_tables()
        self.init_settings()
        self.fix_broken_channel_links()
    
    def get_connection(self):
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        return conn
    
    def create_tables(self):
        with self.get_connection() as conn:
            # Настройки
            conn.execute('''CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )''')
            
            # Пользователи
            conn.execute('''CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                balance INTEGER DEFAULT 0,
                referrals INTEGER DEFAULT 0,
                total_wagered INTEGER DEFAULT 0,
                total_won INTEGER DEFAULT 0,
                referral_id INTEGER,
                subscribed INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            
            # Транзакции
            conn.execute('''CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                type TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            
            # Выводы в Project Evolution
            conn.execute('''CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                skin_name TEXT,
                skin_pattern TEXT,
                screenshot_url TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            
            # Промокоды
            conn.execute('''CREATE TABLE IF NOT EXISTS promo_codes (
                code TEXT PRIMARY KEY,
                amount INTEGER,
                uses_left INTEGER,
                max_uses INTEGER,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            
            # Использованные промокоды
            conn.execute('''CREATE TABLE IF NOT EXISTS used_promo_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                code TEXT,
                amount INTEGER,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            
            # История ставок
            conn.execute('''CREATE TABLE IF NOT EXISTS bets_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                game_type TEXT,
                result TEXT,
                win_amount INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            
            # Каналы для обязательной подписки
            conn.execute('''CREATE TABLE IF NOT EXISTS subscription_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_username TEXT,
                channel_link TEXT,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )''')
            
            # Конкурсы
            conn.execute('''CREATE TABLE IF NOT EXISTS contests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                description TEXT,
                prize_amount INTEGER,
                winner_id INTEGER,
                status TEXT DEFAULT 'active',
                message_id INTEGER,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ends_at TIMESTAMP
            )''')
            
            # Участники конкурсов
            conn.execute('''CREATE TABLE IF NOT EXISTS contest_participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contest_id INTEGER,
                user_id INTEGER,
                username TEXT,
                first_name TEXT,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (contest_id) REFERENCES contests (id)
            )''')
            
            conn.commit()
            logger.info("✅ Таблицы базы данных созданы")
    
    def fix_broken_channel_links(self):
        """Исправляет неправильные ссылки в базе данных"""
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT id, channel_link FROM subscription_channels")
            channels = cursor.fetchall()
            
            fixed_count = 0
            for channel in channels:
                channel_id = channel['id']
                old_link = channel['channel_link']
                
                if old_link and (old_link.startswith('@') or ')' in old_link or old_link.startswith('http://@')):
                    # Исправляем ссылку
                    clean_link = old_link.replace('@', '').strip(')').strip()
                    if clean_link.startswith('http://'):
                        clean_link = clean_link.replace('http://', '').strip()
                    
                    # Проверяем, является ли это username
                    if '/' not in clean_link and '.' not in clean_link:
                        new_link = f"https://t.me/{clean_link}"
                    else:
                        # Если это уже ссылка, исправляем ее
                        if not clean_link.startswith('https://'):
                            new_link = f"https://{clean_link}"
                        else:
                            new_link = clean_link
                    
                    conn.execute("UPDATE subscription_channels SET channel_link = ? WHERE id = ?", 
                               (new_link, channel_id))
                    fixed_count += 1
                    logger.info(f"Исправлена ссылка для канала {channel_id}: {old_link} -> {new_link}")
            
            if fixed_count > 0:
                conn.commit()
                logger.info(f"✅ Исправлено {fixed_count} неправильных ссылок на каналы")
    
    def init_settings(self):
        with self.get_connection() as conn:
            # Устанавливаем значения по умолчанию
            default_settings = [
                ('referral_bonus', '350'),
                ('channel_username', CHANNEL_USERNAME),
                ('channel_link', CHANNEL_LINK),
                ('subscription_required', '1'),  # 1 = обязательно, 0 = не обязательно
                ('balance_image_url', BALANCE_IMAGE_URL),
                ('withdrawal_image_url', WITHDRAWAL_IMAGE_URL),
                ('games_image_url', GAMES_IMAGE_URL),
                ('referrals_image_url', REFERRALS_IMAGE_URL)
            ]
            
            for key, value in default_settings:
                cursor = conn.execute("SELECT 1 FROM settings WHERE key = ?", (key,))
                if not cursor.fetchone():
                    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))
            
            # Добавляем тестовый канал если нет каналов
            cursor = conn.execute("SELECT COUNT(*) as count FROM subscription_channels")
            if cursor.fetchone()['count'] == 0:
                # Исправляем ссылку для тестового канала
                clean_username = CHANNEL_USERNAME.replace('@', '').strip()
                clean_link = CHANNEL_LINK
                if clean_link.startswith('@'):
                    clean_link = f"https://t.me/{clean_link.replace('@', '')}"
                
                conn.execute("INSERT INTO subscription_channels (channel_username, channel_link) VALUES (?, ?)",
                           (CHANNEL_USERNAME, clean_link))
            
            conn.commit()
    
    def get_setting(self, key, default=None):
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            if row:
                return row['value']
            return default
    
    def update_setting(self, key, value):
        with self.get_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
            conn.commit()
            return True
    
    # ========== МЕТОДЫ ДЛЯ КАНАЛОВ ПОДПИСКИ ==========
    
    def add_subscription_channel(self, channel_username, channel_link):
        with self.get_connection() as conn:
            try:
                # Очищаем ссылку
                clean_link = self.clean_channel_link(channel_link)
                
                conn.execute('''INSERT INTO subscription_channels (channel_username, channel_link, is_active) 
                              VALUES (?, ?, 1)''',
                           (channel_username, clean_link))
                conn.commit()
                return True
            except sqlite3.Error as e:
                logger.error(f"Ошибка при добавлении канала: {e}")
                return False
    
    def clean_channel_link(self, link):
        """Очищает и форматирует ссылку на канал"""
        if not link:
            return ""
        
        # Убираем лишние символы
        clean_link = link.strip().strip(')').strip()
        
        # Если это username (начинается с @ или просто текст)
        if clean_link.startswith('@'):
            username = clean_link.replace('@', '').strip()
            return f"https://t.me/{username}"
        elif clean_link.startswith('http://@'):
            username = clean_link.replace('http://@', '').strip()
            return f"https://t.me/{username}"
        elif clean_link.startswith('https://@'):
            username = clean_link.replace('https://@', '').strip()
            return f"https://t.me/{username}"
        elif not clean_link.startswith('http'):
            # Предполагаем что это username без @
            return f"https://t.me/{clean_link}"
        
        return clean_link
    
    def get_subscription_channels(self, active_only=True):
        with self.get_connection() as conn:
            query = "SELECT * FROM subscription_channels"
            if active_only:
                query += " WHERE is_active = 1"
            query += " ORDER BY created_at"
            cursor = conn.execute(query)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def update_subscription_channel(self, channel_id, channel_username=None, channel_link=None, is_active=None):
        with self.get_connection() as conn:
            try:
                updates = []
                params = []
                
                if channel_username is not None:
                    updates.append("channel_username = ?")
                    params.append(channel_username)
                
                if channel_link is not None:
                    updates.append("channel_link = ?")
                    params.append(self.clean_channel_link(channel_link))
                
                if is_active is not None:
                    updates.append("is_active = ?")
                    params.append(is_active)
                
                if updates:
                    params.append(channel_id)
                    query = f"UPDATE subscription_channels SET {', '.join(updates)} WHERE id = ?"
                    conn.execute(query, params)
                    conn.commit()
                    return True
            except sqlite3.Error as e:
                logger.error(f"Ошибка при обновлении канала: {e}")
                return False
    
    def delete_subscription_channel(self, channel_id):
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM subscription_channels WHERE id = ?", (channel_id,))
            conn.commit()
            return cursor.rowcount > 0
    
    def toggle_subscription_channel(self, channel_id):
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT is_active FROM subscription_channels WHERE id = ?", (channel_id,))
            row = cursor.fetchone()
            if row:
                new_status = 0 if row['is_active'] == 1 else 1
                conn.execute("UPDATE subscription_channels SET is_active = ? WHERE id = ?", (new_status, channel_id))
                conn.commit()
                return new_status
            return None
    
    async def check_all_subscriptions(self, user_id):
        """Проверяет подписку на все обязательные каналы"""
        channels = self.get_subscription_channels(active_only=True)
        if not channels:
            return True, []  # Нет каналов - пропускаем проверку
        
        not_subscribed = []
        
        for channel in channels:
            channel_username = channel['channel_username']
            if not channel_username or channel_username == "@ваш_канал" or channel_username == "@my_channel":
                continue  # Пропускаем не настроенные каналы
            
            try:
                # Убираем @ если есть и лишние символы
                clean_username = channel_username.replace('@', '').strip()
                
                # Проверяем что username не пустой
                if not clean_username:
                    continue
                
                chat_member = await bot.get_chat_member(f"@{clean_username}", user_id)
                is_subscribed = chat_member.status in ['member', 'administrator', 'creator']
                
                if not is_subscribed:
                    not_subscribed.append(channel)
            except Exception as e:
                logger.error(f"Ошибка при проверке подписки на канал {channel_username}: {e}")
                # В случае ошибки проверяем ссылку
                if 'not found' in str(e) or 'chat not found' in str(e):
                    logger.warning(f"Канал {channel_username} не найден. Проверьте правильность username.")
                not_subscribed.append(channel)  # В случае ошибки считаем что не подписан
        
        if not_subscribed:
            return False, not_subscribed
        return True, []
    
    # ========== МЕТОДЫ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ ==========
    
    def add_user(self, user_id, username, first_name, last_name, referral_id=None):
        with self.get_connection() as conn:
            # Проверяем, существует ли пользователь
            cursor = conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
            if cursor.fetchone():
                return False
            
            # Добавляем пользователя
            conn.execute('''INSERT INTO users (user_id, username, first_name, last_name, referral_id) 
                          VALUES (?, ?, ?, ?, ?)''',
                       (user_id, username, first_name, last_name, referral_id))
            
            # Если есть реферер, начисляем бонус
            if referral_id and referral_id != user_id:
                referral_bonus = int(self.get_setting('referral_bonus', 350))
                # Начисляем бонус рефереру
                conn.execute("UPDATE users SET balance = balance + ?, referrals = referrals + 1 WHERE user_id = ?",
                           (referral_bonus, referral_id))
                
                # Добавляем запись о транзакции
                conn.execute('''INSERT INTO transactions (user_id, amount, type, description)
                              VALUES (?, ?, ?, ?)''',
                           (referral_id, referral_bonus, 'referral', f'Бонус за приглашение {user_id}'))
                
                # Уведомляем реферера о новом реферале
                asyncio.create_task(self.notify_referrer(referral_id, user_id, username, first_name))
            
            conn.commit()
            return True
    
    async def notify_referrer(self, referrer_id, new_user_id, username, first_name):
        """Уведомляет реферера о новом реферале"""
        try:
            referral_bonus = int(self.get_setting('referral_bonus', 350))
            user_info = f"@{username}" if username else f"{first_name} (ID: {new_user_id})"
            message = (
                f"🎉 <b>У вас новый реферал!</b>\n\n"
                f"👤 Пользователь: {user_info}\n"
                f"💰 Начислено: <b>{referral_bonus} голды</b>\n"
                f"💎 Ваш баланс пополнен автоматически!"
            )
            await bot.send_message(referrer_id, message, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление рефереру {referrer_id}: {e}")
    
    def update_subscription_status(self, user_id, subscribed=True):
        with self.get_connection() as conn:
            status = 1 if subscribed else 0
            conn.execute("UPDATE users SET subscribed = ? WHERE user_id = ?", (status, user_id))
            conn.commit()
            return True
    
    def check_subscription(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT subscribed FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                return bool(row['subscribed'])
            return False
    
    def get_user(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    def get_balance(self, user_id):
        user = self.get_user(user_id)
        return user['balance'] if user else 0
    
    def update_balance(self, user_id, amount, description=""):
        with self.get_connection() as conn:
            try:
                # Обновляем баланс
                conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
                
                # Добавляем транзакцию
                if description:
                    conn.execute('''INSERT INTO transactions (user_id, amount, type, description)
                                  VALUES (?, ?, ?, ?)''',
                               (user_id, amount, 'admin_add' if amount > 0 else 'admin_remove', description))
                
                conn.commit()
                return True
            except Exception as e:
                logger.error(f"Ошибка при обновлении баланса: {e}")
                return False
    
    # ========== МЕТОДЫ ДЛЯ ИГР ==========
    
    def process_bet(self, user_id, amount, game_type, result, win_amount):
        with self.get_connection() as conn:
            try:
                # Получаем текущий баланс
                cursor = conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
                current_balance = cursor.fetchone()
                
                if not current_balance:
                    logger.error(f"Пользователь {user_id} не найден")
                    return False
                
                current_balance = current_balance['balance']
                
                # Проверяем, достаточно ли средств для ставки
                if amount > current_balance:
                    logger.error(f"Недостаточно средств: {amount} > {current_balance}")
                    return False
                
                # Рассчитываем изменение баланса
                balance_change = win_amount - amount
                
                # Обновляем баланс
                conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", 
                            (balance_change, user_id))
                
                # Обновляем статистику
                conn.execute("UPDATE users SET total_wagered = total_wagered + ? WHERE user_id = ?", 
                            (amount, user_id))
                
                if win_amount > 0:
                    conn.execute("UPDATE users SET total_won = total_won + ? WHERE user_id = ?", 
                                (win_amount, user_id))
                
                # Добавляем в историю ставок
                conn.execute('''INSERT INTO bets_history (user_id, amount, game_type, result, win_amount)
                              VALUES (?, ?, ?, ?, ?)''',
                           (user_id, amount, game_type, result, win_amount))
                
                # Добавляем транзакцию
                transaction_type = 'bet_win' if win_amount > 0 else 'bet_loss'
                conn.execute('''INSERT INTO transactions (user_id, amount, type, description)
                              VALUES (?, ?, ?, ?)''',
                           (user_id, balance_change, transaction_type, f'Ставка в {game_type}: {result}'))
                
                conn.commit()
                logger.info(f"✅ Ставка обработана: user_id={user_id}, amount={amount}, win_amount={win_amount}")
                return True
                
            except Exception as e:
                logger.error(f"Ошибка в process_bet: {e}")
                conn.rollback()
                return False
    
    def get_bets_history(self, user_id, limit=10):
        with self.get_connection() as conn:
            cursor = conn.execute('''SELECT * FROM bets_history 
                                   WHERE user_id = ? 
                                   ORDER BY created_at DESC 
                                   LIMIT ?''',
                                (user_id, limit))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    # ========== МЕТОДЫ ДЛЯ РЕФЕРАЛОВ ==========
    
    def get_referrals(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.execute('''SELECT user_id, username, first_name, created_at 
                                   FROM users WHERE referral_id = ? ORDER BY created_at DESC''',
                                (user_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    # ========== МЕТОДЫ ДЛЯ ВЫВОДА ==========
    
    def create_withdrawal(self, user_id, amount, skin_name, skin_pattern, screenshot_url=None):
        with self.get_connection() as conn:
            try:
                # Проверяем баланс
                cursor = conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
                user = cursor.fetchone()
                
                if not user:
                    logger.error(f"Пользователь {user_id} не найден")
                    return None
                
                balance = user['balance']
                
                if amount > balance:
                    logger.error(f"Недостаточно средств: {amount} > {balance}")
                    return None
                
                # Списываем средства
                conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
                
                # Создаем заявку на вывод
                cursor = conn.execute('''INSERT INTO withdrawals (user_id, amount, skin_name, skin_pattern, screenshot_url)
                                       VALUES (?, ?, ?, ?, ?)''',
                                    (user_id, amount, skin_name, skin_pattern, screenshot_url))
                withdrawal_id = cursor.lastrowid
                
                # Добавляем транзакцию
                conn.execute('''INSERT INTO transactions (user_id, amount, type, description)
                              VALUES (?, ?, ?, ?)''',
                           (user_id, -amount, 'withdrawal', f'Запрос на скин #{withdrawal_id} в Project Evolution'))
                
                conn.commit()
                logger.info(f"✅ Заявка на вывод #{withdrawal_id} создана: user_id={user_id}, amount={amount}")
                return withdrawal_id
                
            except Exception as e:
                logger.error(f"Ошибка в create_withdrawal: {e}")
                conn.rollback()
                return None
    
    def get_withdrawals(self, user_id=None, status=None):
        with self.get_connection() as conn:
            query = "SELECT * FROM withdrawals"
            params = []
            
            if user_id:
                query += " WHERE user_id = ?"
                params.append(user_id)
                if status:
                    query += " AND status = ?"
                    params.append(status)
            elif status:
                query += " WHERE status = ?"
                params.append(status)
            
            query += " ORDER BY created_at DESC"
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def update_withdrawal_status(self, withdrawal_id, status):
        with self.get_connection() as conn:
            # Получаем информацию о выплате
            cursor = conn.execute("SELECT user_id, amount FROM withdrawals WHERE id = ?", (withdrawal_id,))
            withdrawal = cursor.fetchone()
            
            if not withdrawal:
                return False
            
            user_id, amount = withdrawal['user_id'], withdrawal['amount']
            
            # Обновляем статус
            conn.execute("UPDATE withdrawals SET status = ? WHERE id = ?", (status, withdrawal_id))
            
            # Если отклоняем, возвращаем средства
            if status == 'rejected':
                conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
                conn.execute('''INSERT INTO transactions (user_id, amount, type, description)
                              VALUES (?, ?, ?, ?)''',
                           (user_id, amount, 'refund', f'Возврат по заявке #{withdrawal_id}'))
            
            conn.commit()
            return True
    
    # ========== МЕТОДЫ ДЛЯ СТАТИСТИКИ ==========
    
    def get_all_users(self):
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT user_id, username, first_name, balance, total_wagered, total_won, created_at FROM users ORDER BY created_at DESC")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_stats(self):
        with self.get_connection() as conn:
            cursor = conn.execute('''SELECT 
                COUNT(*) as total_users,
                SUM(balance) as total_balance,
                SUM(referrals) as total_referrals,
                SUM(total_wagered) as total_wagered,
                SUM(total_won) as total_won,
                (SELECT COUNT(*) FROM withdrawals WHERE status = 'pending') as pending_withdrawals,
                (SELECT SUM(amount) FROM withdrawals WHERE status = 'paid') as total_paid
            FROM users''')
            row = cursor.fetchone()
            if row:
                result = dict(row)
                for key in result:
                    if result[key] is None:
                        result[key] = 0
                return result
            return {'total_users': 0, 'total_balance': 0, 'total_referrals': 0, 'total_wagered': 0, 'total_won': 0, 'pending_withdrawals': 0, 'total_paid': 0}
    
    # ========== МЕТОДЫ ДЛЯ ПРОМОКОДОВ ==========
    
    def create_promo_code(self, code, amount, max_uses, created_by):
        with self.get_connection() as conn:
            try:
                conn.execute('''INSERT INTO promo_codes (code, amount, uses_left, max_uses, created_by)
                              VALUES (?, ?, ?, ?, ?)''',
                           (code, amount, max_uses, max_uses, created_by))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False  # Промокод уже существует
    
    def use_promo_code(self, user_id, code):
        with self.get_connection() as conn:
            # Проверяем, использовал ли уже пользователь этот промокод
            cursor = conn.execute("SELECT 1 FROM used_promo_codes WHERE user_id = ? AND code = ?", (user_id, code))
            if cursor.fetchone():
                return False, "Вы уже использовали этот промокод"
            
            # Получаем информацию о промокоде
            cursor = conn.execute("SELECT amount, uses_left FROM promo_codes WHERE code = ?", (code,))
            promo = cursor.fetchone()
            
            if not promo:
                return False, "Промокод не найден"
            
            amount, uses_left = promo['amount'], promo['uses_left']
            
            if uses_left <= 0:
                return False, "Промокод больше не действителен"
            
            # Используем промокод
            conn.execute("UPDATE promo_codes SET uses_left = uses_left - 1 WHERE code = ?", (code,))
            
            # Начисляем голду
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
            
            # Записываем использование
            conn.execute('''INSERT INTO used_promo_codes (user_id, code, amount)
                          VALUES (?, ?, ?)''',
                       (user_id, code, amount))
            
            # Записываем транзакцию
            conn.execute('''INSERT INTO transactions (user_id, amount, type, description)
                          VALUES (?, ?, ?, ?)''',
                       (user_id, amount, 'promo', f'Активация промокода {code}'))
            
            conn.commit()
            return True, f"Промокод активирован! Получено {amount} голды"
    
    def get_promo_codes(self):
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM promo_codes ORDER BY created_at DESC")
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def delete_promo_code(self, code):
        with self.get_connection() as conn:
            cursor = conn.execute("DELETE FROM promo_codes WHERE code = ?", (code,))
            conn.commit()
            return cursor.rowcount > 0
    
    # ========== МЕТОДЫ ДЛЯ КОНКУРСОВ ==========
    
    def create_contest(self, name, description, prize_amount, created_by, duration_hours=24):
        with self.get_connection() as conn:
            try:
                # Рассчитываем время окончания
                ends_at = datetime.now() + timedelta(hours=duration_hours)
                
                conn.execute('''INSERT INTO contests (name, description, prize_amount, created_by, ends_at, status)
                              VALUES (?, ?, ?, ?, ?, 'active')''',
                           (name, description, prize_amount, created_by, ends_at))
                contest_id = conn.lastrowid
                conn.commit()
                return contest_id
            except Exception as e:
                logger.error(f"Ошибка при создании конкурса: {e}")
                return None
    
    def get_contests(self, status=None):
        with self.get_connection() as conn:
            query = "SELECT * FROM contests"
            params = []
            
            if status:
                query += " WHERE status = ?"
                params.append(status)
            
            query += " ORDER BY created_at DESC"
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_contest(self, contest_id):
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT * FROM contests WHERE id = ?", (contest_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    def update_contest_message_id(self, contest_id, message_id, chat_id=None):
        with self.get_connection() as conn:
            conn.execute("UPDATE contests SET message_id = ? WHERE id = ?", (message_id, contest_id))
            conn.commit()
            return True
    
    def join_contest(self, contest_id, user_id, username, first_name):
        with self.get_connection() as conn:
            try:
                # Проверяем, не участвует ли уже пользователь
                cursor = conn.execute('''SELECT 1 FROM contest_participants 
                                       WHERE contest_id = ? AND user_id = ?''',
                                    (contest_id, user_id))
                if cursor.fetchone():
                    return False, "Вы уже участвуете в этом конкурсе"
                
                # Добавляем участника
                conn.execute('''INSERT INTO contest_participants (contest_id, user_id, username, first_name)
                              VALUES (?, ?, ?, ?)''',
                           (contest_id, user_id, username, first_name))
                conn.commit()
                return True, "✅ Вы успешно присоединились к конкурсу!"
            except Exception as e:
                logger.error(f"Ошибка при присоединении к конкурсу: {e}")
                return False, "Ошибка при присоединении к конкурсу"
    
    def get_contest_participants(self, contest_id):
        with self.get_connection() as conn:
            cursor = conn.execute('''SELECT * FROM contest_participants 
                                   WHERE contest_id = ? ORDER BY joined_at''',
                                (contest_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    
    def get_contest_participant_count(self, contest_id):
        with self.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) as count FROM contest_participants WHERE contest_id = ?", (contest_id,))
            row = cursor.fetchone()
            return row['count'] if row else 0
    
    def select_contest_winner(self, contest_id):
        with self.get_connection() as conn:
            try:
                # Получаем всех участников
                participants = self.get_contest_participants(contest_id)
                if not participants:
                    return None, "Нет участников для выбора победителя"
                
                # Выбираем случайного победителя
                winner = random.choice(participants)
                winner_id = winner['user_id']
                
                # Получаем информацию о конкурсе
                contest = self.get_contest(contest_id)
                if not contest:
                    return None, "Конкурс не найден"
                
                # Обновляем конкурс
                conn.execute("UPDATE contests SET winner_id = ?, status = 'completed' WHERE id = ?", 
                           (winner_id, contest_id))
                
                # Начисляем приз победителю
                prize_amount = contest['prize_amount']
                conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", 
                           (prize_amount, winner_id))
                
                # Добавляем транзакцию
                conn.execute('''INSERT INTO transactions (user_id, amount, type, description)
                              VALUES (?, ?, ?, ?)''',
                           (winner_id, prize_amount, 'contest_win', f'Победа в конкурсе "{contest["name"]}"'))
                
                conn.commit()
                return winner, "✅ Победитель выбран и приз начислен"
            except Exception as e:
                logger.error(f"Ошибка при выборе победителя: {e}")
                return None, f"Ошибка при выборе победителя: {e}"
    
    def end_contest(self, contest_id):
        with self.get_connection() as conn:
            conn.execute("UPDATE contests SET status = 'completed', ends_at = datetime('now') WHERE id = ?", (contest_id,))
            conn.commit()
            return True
    
    def delete_contest(self, contest_id):
        with self.get_connection() as conn:
            # Удаляем участников
            conn.execute("DELETE FROM contest_participants WHERE contest_id = ?", (contest_id,))
            # Удаляем конкурс
            cursor = conn.execute("DELETE FROM contests WHERE id = ?", (contest_id,))
            conn.commit()
            return cursor.rowcount > 0

# Инициализируем базу данных
db = Database()

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
async def check_subscription_required(user_id):
    """Проверяет обязательную подписку на все каналы"""
    subscription_required = db.get_setting('subscription_required', '1') == '1'
    if not subscription_required:
        return True, None
    
    channels = db.get_subscription_channels(active_only=True)
    if not channels:
        return True, None  # Нет обязательных каналов
    
    is_subscribed, not_subscribed_channels = await db.check_all_subscriptions(user_id)
    
    if is_subscribed:
        # Обновляем статус в базе
        db.update_subscription_status(user_id, True)
        return True, None
    else:
        # Обновляем статус в базе
        db.update_subscription_status(user_id, False)
        
        # Создаем клавиатуру со всеми каналами
        buttons = []
        
        for channel in not_subscribed_channels:
            channel_username = channel['channel_username']
            channel_link = channel['channel_link']
            
            # Проверяем ссылку
            if not channel_link or not channel_link.startswith('http'):
                channel_link = f"https://t.me/{channel_username.replace('@', '')}"
            
            if channel_link:
                buttons.append([InlineKeyboardButton(
                    text=f"📢 Подписаться на {channel_username}", 
                    url=channel_link
                )])
        
        buttons.append([InlineKeyboardButton(
            text="✅ Я подписался на все каналы", 
            callback_data="check_subscription_all"
        )])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        # Создаем текст со списком каналов
        channels_text = "\n".join([f"• {ch['channel_username']}" for ch in not_subscribed_channels])
        
        return False, {
            'keyboard': keyboard,
            'channels_text': channels_text,
            'channels_count': len(not_subscribed_channels)
        }

async def check_and_end_contests():
    """Проверяет и завершает просроченные конкурсы"""
    try:
        contests = db.get_contests(status='active')
        now = datetime.now()
        
        for contest in contests:
            ends_at = datetime.strptime(contest['ends_at'], '%Y-%m-%d %H:%M:%S') if isinstance(contest['ends_at'], str) else contest['ends_at']
            
            if now > ends_at:
                # Время конкурса истекло
                participants_count = db.get_contest_participant_count(contest['id'])
                
                if participants_count > 0:
                    # Выбираем победителя
                    winner, message = db.select_contest_winner(contest['id'])
                    
                    if winner:
                        # Уведомляем победителя
                        try:
                            winner_user = db.get_user(winner['user_id'])
                            winner_name = f"@{winner_user['username']}" if winner_user and winner_user['username'] else winner_user['first_name'] if winner_user else f"ID: {winner['user_id']}"
                            
                            await bot.send_message(
                                winner['user_id'],
                                f"🎉 <b>ПОЗДРАВЛЯЕМ!</b>\n\n"
                                f"🏆 <b>Вы победили в конкурсе:</b> {contest['name']}\n"
                                f"💰 <b>Приз:</b> {contest['prize_amount']} голды\n"
                                f"💎 <b>Приз начислен на ваш баланс!</b>\n\n"
                                f"🎮 Проверьте баланс в боте.",
                                parse_mode='HTML'
                            )
                            
                            # Обновляем сообщение конкурса
                            try:
                                if contest.get('message_id'):
                                    # Пытаемся обновить в канале конкурсов
                                    try:
                                        await bot.edit_message_text(
                                            chat_id=CONTESTS_CHANNEL_ID,
                                            message_id=contest['message_id'],
                                            text=format_contest_message(contest, winner_name, participants_count),
                                            parse_mode='HTML',
                                            reply_markup=None
                                        )
                                    except:
                                        # Если не в канале, обновляем у админа
                                        await bot.edit_message_text(
                                            chat_id=ADMIN_ID,
                                            message_id=contest['message_id'],
                                            text=format_contest_message(contest, winner_name, participants_count),
                                            parse_mode='HTML',
                                            reply_markup=None
                                        )
                            except Exception as e:
                                logger.error(f"Не удалось обновить сообщение конкурса: {e}")
                                
                        except Exception as e:
                            logger.error(f"Не удалось уведомить победителя: {e}")
                else:
                    # Нет участников, просто завершаем конкурс
                    db.end_contest(contest['id'])
    except Exception as e:
        logger.error(f"Ошибка при проверке конкурсов: {e}")

def format_contest_message(contest, winner_name=None, participants_count=None):
    """Форматирует сообщение о конкурсе"""
    if participants_count is None:
        participants_count = db.get_contest_participant_count(contest['id'])
    
    status_emoji = "🟢" if contest['status'] == 'active' else "🔴" if contest['status'] == 'completed' else "⚫"
    status_text = "Активен" if contest['status'] == 'active' else "Завершен" if contest['status'] == 'completed' else "Отменен"
    
    message = f"{status_emoji} <b>КОНКУРС #{contest['id']}</b>\n\n"
    message += f"🏆 <b>Название:</b> {contest['name']}\n"
    message += f"📝 <b>Описание:</b> {contest['description']}\n"
    message += f"💰 <b>Приз:</b> {contest['prize_amount']} голды\n"
    message += f"👥 <b>Участников:</b> {participants_count}\n"
    message += f"📊 <b>Статус:</b> {status_text}\n"
    
    if contest['status'] == 'active':
        ends_at = contest['ends_at']
        if isinstance(ends_at, str):
            ends_at = ends_at[:19]
        message += f"⏰ <b>Заканчивается:</b> {ends_at}\n\n"
        message += "🎯 <b>Нажмите кнопку ниже, чтобы присоединиться!</b>"
    elif contest['status'] == 'completed' and winner_name:
        message += f"🏅 <b>Победитель:</b> {winner_name}\n\n"
        message += "✅ <b>Конкурс завершен!</b>"
    else:
        message += "\n❌ <b>Конкурс завершен без победителя</b>"
    
    return message

# ========== КЛАВИАТУРЫ ==========
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💰 Баланс"), KeyboardButton(text="🎮 Игры")],
            [KeyboardButton(text="👥 Мои рефералы"), KeyboardButton(text="🎁 Промокод")],
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="ℹ️ Помощь")]
        ],
        resize_keyboard=True
    )

def games_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎮 Вывод в Project Evolution")],
            [KeyboardButton(text="🎲 Сделать ставку")],
            [KeyboardButton(text="📊 История ставок")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )

def dice_bet_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎲 Чет", callback_data="dice_even"),
                InlineKeyboardButton(text="🎲 Нечет", callback_data="dice_odd")
            ],
            [
                InlineKeyboardButton(text="🎯 От 1-3", callback_data="dice_1_3"),
                InlineKeyboardButton(text="🎯 От 4-6", callback_data="dice_4_6")
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_bet")]
        ]
    )

def amount_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="100", callback_data="amount_100"),
                InlineKeyboardButton(text="500", callback_data="amount_500"),
                InlineKeyboardButton(text="1000", callback_data="amount_1000")
            ],
            [
                InlineKeyboardButton(text="2000", callback_data="amount_2000"),
                InlineKeyboardButton(text="5000", callback_data="amount_5000"),
                InlineKeyboardButton(text="10000", callback_data="amount_10000")
            ],
            [InlineKeyboardButton(text="🎮 Другая сумма", callback_data="amount_custom")]
        ]
    )

def withdrawal_amount_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="5000", callback_data="withdraw_5000"),
                InlineKeyboardButton(text="10000", callback_data="withdraw_10000"),
                InlineKeyboardButton(text="20000", callback_data="withdraw_20000")
            ],
            [
                InlineKeyboardButton(text="50000", callback_data="withdraw_50000"),
                InlineKeyboardButton(text="100000", callback_data="withdraw_100000"),
                InlineKeyboardButton(text="🎮 Другая сумма", callback_data="withdraw_custom")
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_withdrawal")]
        ]
    )

def admin_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Общая статистика"), KeyboardButton(text="👥 Все пользователи")],
            [KeyboardButton(text="🎮 Заявки на вывод"), KeyboardButton(text="🎁 Промокоды")],
            [KeyboardButton(text="🎯 Конкурсы"), KeyboardButton(text="💰 Выдать голду")],
            [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="📢 Рассылка")],
            [KeyboardButton(text="⬅️ В меню")]
        ],
        resize_keyboard=True
    )

def admin_contests_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Активные конкурсы")],
            [KeyboardButton(text="➕ Создать конкурс")],
            [KeyboardButton(text="🏆 Завершить конкурс")],
            [KeyboardButton(text="🗑️ Удалить конкурс")],
            [KeyboardButton(text="⬅️ Назад в админку")]
        ],
        resize_keyboard=True
    )

def admin_settings_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💰 Изменить реф. бонус")],
            [KeyboardButton(text="📢 Управление каналами")],
            [KeyboardButton(text="🔧 Вкл/Выкл подписку")],
            [KeyboardButton(text="⬅️ Назад в админку")]
        ],
        resize_keyboard=True
    )

def admin_channels_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Список каналов")],
            [KeyboardButton(text="➕ Добавить канал")],
            [KeyboardButton(text="⚙️ Управление каналами")],
            [KeyboardButton(text="⬅️ Назад в настройки")]
        ],
        resize_keyboard=True
    )

# ========== СОСТОЯНИЯ ==========
class WithdrawalStates(StatesGroup):
    choosing_amount = State()
    entering_skin_name = State()
    entering_skin_pattern = State()
    waiting_for_screenshot = State()

class DiceBetStates(StatesGroup):
    choosing_amount = State()
    choosing_bet_type = State()

class PromoCodeState(StatesGroup):
    entering_code = State()

class AdminAddGoldState(StatesGroup):
    entering_user_id = State()
    entering_amount = State()
    entering_description = State()

class AdminCreatePromoState(StatesGroup):
    entering_amount = State()
    entering_uses = State()

class AdminCreateContestState(StatesGroup):
    entering_name = State()
    entering_description = State()
    entering_prize_amount = State()
    entering_duration = State()

class AdminEndContestState(StatesGroup):
    choosing_contest = State()

class AdminDeleteContestState(StatesGroup):
    choosing_contest = State()

class AdminSettingsState(StatesGroup):
    changing_referral_bonus = State()
    changing_subscription_required = State()

class AdminChannelState(StatesGroup):
    adding_channel_username = State()
    adding_channel_link = State()

class BroadcastState(StatesGroup):
    waiting_for_message = State()

# ========== ОБРАБОТЧИКИ КОМАНД ==========
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = message.from_user
    args = message.text.split()
    
    # Проверяем подписку
    is_allowed, subscription_info = await check_subscription_required(user.id)
    if not is_allowed:
        channels_text = subscription_info['channels_text']
        keyboard = subscription_info['keyboard']
        channels_count = subscription_info['channels_count']
        
        await message.answer(
            f"📢 <b>Для использования бота необходимо подписаться на каналы!</b>\n\n"
            f"Подпишитесь на наши каналы ({channels_count}):\n"
            f"{channels_text}\n\n"
            f"После подписки нажмите кнопку ниже:",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        return
    
    referral_id = None
    if len(args) > 1:
        try:
            referral_id = int(args[1])
            if referral_id == user.id:
                referral_id = None
            elif not db.get_user(referral_id):
                referral_id = None
        except:
            referral_id = None
    
    is_new = db.add_user(user.id, user.username, user.first_name, user.last_name, referral_id)
    
    # Получаем username бота
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user.id}"
    
    # Получаем текущий реферальный бонус
    referral_bonus = int(db.get_setting('referral_bonus', 350))
    
    text = "🎮 <b>Добро пожаловать в бот с Project Evolution!</b>\n\n" if is_new else "👋 <b>С возвращением!</b>\n\n"
    
    if referral_id:
        text += f"✅ Вы были приглашены пользователем!\n\n"
    
    text += f"🔗 <b>Ваша реферальная ссылка:</b>\n<code>{ref_link}</code>\n\n"
    text += f"💰 <b>За каждого друга:</b> {referral_bonus} голды\n"
    text += f"🎮 <b>Мин. вывод в Project Evolution:</b> {MIN_WITHDRAWAL} голды\n\n"
    text += f"💎 <b>Доступные функции:</b>\n"
    text += f"• 🎮 Вывод скинов в Project Evolution\n"
    text += f"• 🎲 Азартные игры с кубиками\n"
    text += f"• 🎁 Промокоды и бонусы\n"
    text += f"• 👥 Реферальная система\n"
    text += f"• 🎯 Участвуйте в конкурсах с призами!"
    
    await message.answer(text, reply_markup=main_menu(), parse_mode='HTML')

@dp.callback_query(F.data.in_(["check_subscription", "check_subscription_all"]))
async def check_subscription_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    # Проверяем подписку
    is_allowed, subscription_info = await check_subscription_required(user_id)
    
    if is_allowed:
        await callback.message.edit_text(
            "✅ <b>Отлично! Вы подписаны на все каналы.</b>\n\n"
            "Теперь вы можете пользоваться всеми функциями бота!",
            parse_mode='HTML'
        )
        
        # Отправляем приветственное сообщение
        bot_info = await bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
        referral_bonus = int(db.get_setting('referral_bonus', 350))
        
        text = f"🎮 <b>Добро пожаловать!</b>\n\n"
        text += f"🔗 <b>Ваша реферальная ссылка:</b>\n<code>{ref_link}</code>\n\n"
        text += f"💰 <b>За каждого друга:</b> {referral_bonus} голды\n"
        text += f"🎮 <b>Мин. вывод в Project Evolution:</b> {MIN_WITHDRAWAL} голды"
        
        await callback.message.answer(text, reply_markup=main_menu(), parse_mode='HTML')
    else:
        channels_text = subscription_info['channels_text']
        keyboard = subscription_info['keyboard']
        channels_count = subscription_info['channels_count']
        
        await callback.message.edit_text(
            f"❌ <b>Вы еще не подписаны на все каналы!</b>\n\n"
            f"Необходимо подписаться на каналы ({channels_count}):\n"
            f"{channels_text}\n\n"
            f"После подписки нажмите кнопку еще раз.",
            reply_markup=keyboard,
            parse_mode='HTML'
        )

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Нет доступа к админ-панели")
        return
    
    # Проверяем и завершаем просроченные конкурсы
    await check_and_end_contests()
    
    await message.answer("👑 <b>Панель администратора Project Evolution</b>", reply_markup=admin_main_menu(), parse_mode='HTML')

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    # Проверяем подписку
    is_allowed, subscription_info = await check_subscription_required(message.from_user.id)
    if not is_allowed:
        channels_text = subscription_info['channels_text']
        keyboard = subscription_info['keyboard']
        channels_count = subscription_info['channels_count']
        
        await message.answer(
            f"📢 <b>Для использования бота необходимо подписаться на каналы!</b>\n\n"
            f"Подпишитесь на наши каналы ({channels_count}):\n"
            f"{channels_text}",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        return
    
    referral_bonus = int(db.get_setting('referral_bonus', 350))
    
    help_text = f"""
🎮 <b>Помощь по Project Evolution боту</b>

💰 <b>Как заработать голду:</b>
1. Приглашайте друзей по своей ссылке
2. За каждого приглашенного: <b>{referral_bonus} голды</b>
3. Играйте в азартные игры
4. Используйте промокоды для бонусов
5. Участвуйте в конкурсах с призами!

🎮 <b>Как вывести скин в Project Evolution:</b>
1. Накопите от <b>{MIN_WITHDRAWAL} голды</b>
2. Нажмите "🎮 Игры" → "🎮 Вывод в Project Evolution"
3. Выберите сумму вывода
4. Введите название скина
5. Укажите паттерн скина
6. <b>Прикрепите скриншот</b> с вашим профилем в Project Evolution
7. Получите скин в игре!

🎲 <b>Игра в кубики:</b>
1. Нажмите "🎮 Игры" → "🎲 Сделать ставку"
2. Выберите сумму ставки
3. Выберите тип ставки (Чет/Нечет или диапазон)
4. Кидается кубик
5. Если выиграли - получаете х2 от ставки!

🎯 <b>Конкурсы:</b>
• Администраторы запускают конкурсы с призами
• Участвуйте и выигрывайте голду
• Призы начисляются автоматически

🎁 <b>Промокоды:</b>
• Нажмите "🎁 Промокод"
• Введите промокод
• Получите бонусную голду

📊 <b>Основные команды:</b>
/start - Начать работу
/help - Эта справка
/admin - Админ-панель (только для админа)
/promo - Активировать промокод
    """
    
    await message.answer(help_text, parse_mode='HTML')

@dp.message(Command("promo"))
async def cmd_promo(message: types.Message, state: FSMContext):
    # Проверяем подписку
    is_allowed, subscription_info = await check_subscription_required(message.from_user.id)
    if not is_allowed:
        channels_text = subscription_info['channels_text']
        keyboard = subscription_info['keyboard']
        channels_count = subscription_info['channels_count']
        
        await message.answer(
            f"📢 <b>Для использования бота необходимо подписаться на каналы!</b>\n\n"
            f"Подпишитесь на наши каналы ({channels_count}):\n"
            f"{channels_text}",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        return
    
    await message.answer("🎁 <b>Введите промокод:</b>", parse_mode='HTML')
    await state.set_state(PromoCodeState.entering_code)

# ========== ОБРАБОТЧИКИ КНОПОК ==========
@dp.message(F.text == "⬅️ Назад")
async def back_to_main(message: types.Message):
    await message.answer("Главное меню:", reply_markup=main_menu())

@dp.message(F.text == "💰 Баланс")
async def show_balance(message: types.Message):
    # Проверяем подписку
    is_allowed, subscription_info = await check_subscription_required(message.from_user.id)
    if not is_allowed:
        channels_text = subscription_info['channels_text']
        keyboard = subscription_info['keyboard']
        channels_count = subscription_info['channels_count']
        
        await message.answer(
            f"📢 <b>Для использования бота необходимо подписаться на каналы!</b>\n\n"
            f"Подпишитесь на наши каналы ({channels_count}):\n"
            f"{channels_text}",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        return
    
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Нажмите /start чтобы начать")
        return
    
    referrals = db.get_referrals(message.from_user.id)
    referral_bonus = int(db.get_setting('referral_bonus', 350))
    
    text = f"""
💰 <b>Ваш баланс:</b> {user['balance']} голды
👥 <b>Приглашено друзей:</b> {user['referrals']}
🎁 <b>Заработано на рефералах:</b> {user['referrals'] * referral_bonus} голды

🎲 <b>Статистика игр:</b>
├ Поставлено: {user['total_wagered']} голды
└ Выиграно: {user['total_won']} голды

🎮 <b>Мин. вывод в Project Evolution:</b> {MIN_WITHDRAWAL} голды
✅ <b>Доступно для вывода:</b> {'Да' if user['balance'] >= MIN_WITHDRAWAL else 'Нет'}

📈 <b>Активных рефералов:</b> {len(referrals)}
    """
    
    # Отправляем фото с балансом если есть ссылка
    balance_image = db.get_setting('balance_image_url', BALANCE_IMAGE_URL)
    if balance_image and balance_image.startswith('http'):
        try:
            await message.answer_photo(
                photo=balance_image,
                caption=text,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Не удалось отправить фото баланса: {e}")
            await message.answer(text, parse_mode='HTML')
    else:
        await message.answer(text, parse_mode='HTML')

@dp.message(F.text == "🎮 Игры")
async def games_menu_handler(message: types.Message):
    # Проверяем подписку
    is_allowed, subscription_info = await check_subscription_required(message.from_user.id)
    if not is_allowed:
        channels_text = subscription_info['channels_text']
        keyboard = subscription_info['keyboard']
        channels_count = subscription_info['channels_count']
        
        await message.answer(
            f"📢 <b>Для использования бота необходимо подписаться на каналы!</b>\n\n"
            f"Подпишитесь на наши каналы ({channels_count}):\n"
            f"{channels_text}",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        return
    
    # Отправляем фото для раздела игр
    games_image = db.get_setting('games_image_url', GAMES_IMAGE_URL)
    if games_image and games_image.startswith('http'):
        try:
            await message.answer_photo(
                photo=games_image,
                caption="🎮 <b>Игровое меню</b>\n\nВыберите интересующий вас раздел:",
                reply_markup=games_menu(),
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Не удалось отправить фото игр: {e}")
            await message.answer("🎮 <b>Игровое меню</b>", reply_markup=games_menu(), parse_mode='HTML')
    else:
        await message.answer("🎮 <b>Игровое меню</b>", reply_markup=games_menu(), parse_mode='HTML')

@dp.message(F.text == "🎮 Вывод в Project Evolution")
async def start_withdrawal(message: types.Message):
    # Проверяем подписку
    is_allowed, subscription_info = await check_subscription_required(message.from_user.id)
    if not is_allowed:
        channels_text = subscription_info['channels_text']
        keyboard = subscription_info['keyboard']
        channels_count = subscription_info['channels_count']
        
        await message.answer(
            f"📢 <b>Для использования бота необходимо подписаться на каналы!</b>\n\n"
            f"Подпишитесь на наши каналы ({channels_count}):\n"
            f"{channels_text}",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        return
    
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Нажмите /start чтобы начать")
        return
    
    balance = user['balance']
    
    if balance < MIN_WITHDRAWAL:
        await message.answer(
            f"❌ <b>Недостаточно голды!</b>\n\n"
            f"💰 Ваш баланс: {balance} голды\n"
            f"🎮 Нужно для вывода в Project Evolution: {MIN_WITHDRAWAL} голды\n\n"
            f"💎 Пригласите друзей или сыграйте в игры!",
            parse_mode='HTML'
        )
        return
    
    # Отправляем фото для раздела вывода
    withdrawal_image = db.get_setting('withdrawal_image_url', WITHDRAWAL_IMAGE_URL)
    
    caption = (
        f"🎮 <b>Вывод скина в Project Evolution</b>\n\n"
        f"💰 <b>Доступно:</b> {balance} голды\n"
        f"💎 <b>Мин. сумма:</b> {MIN_WITHDRAWAL} голды\n"
        f"📸 <b>Важно:</b> При выводе <b>обязательно прикрепите скриншот</b> с вашим профилем в Project Evolution\n\n"
        f"<b>Выберите сумму для вывода:</b>"
    )
    
    if withdrawal_image and withdrawal_image.startswith('http'):
        try:
            await message.answer_photo(
                photo=withdrawal_image,
                caption=caption,
                reply_markup=withdrawal_amount_keyboard(),
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Не удалось отправить фото вывода: {e}")
            await message.answer(caption, reply_markup=withdrawal_amount_keyboard(), parse_mode='HTML')
    else:
        await message.answer(caption, reply_markup=withdrawal_amount_keyboard(), parse_mode='HTML')

# ========== ИСПРАВЛЕННЫЕ ОБРАБОТЧИКИ ВЫВОДА ==========
@dp.callback_query(F.data.startswith("withdraw_"))
async def process_withdrawal_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обработчик инлайн-кнопок вывода"""
    user_id = callback.from_user.id
    data = callback.data
    
    if data == "cancel_withdrawal":
        await state.clear()
        await callback.message.edit_text("❌ Вывод отменен.")
        await callback.message.answer("Главное меню:", reply_markup=main_menu())
        return
    
    if data == "withdraw_custom":
        await callback.message.edit_text(
            "🎮 <b>Введите сумму для вывода:</b>\n"
            f"(Минимум: {MIN_WITHDRAWAL} голды)",
            parse_mode='HTML'
        )
        await state.set_state(WithdrawalStates.choosing_amount)
        return
    
    # Обработка фиксированных сумм
    try:
        amount_str = data.replace("withdraw_", "")
        amount = int(amount_str)
        
        user_balance = db.get_balance(user_id)
        
        if amount < MIN_WITHDRAWAL:
            await callback.answer(
                f"❌ Минимальная сумма вывода: {MIN_WITHDRAWAL} голды",
                show_alert=True
            )
            return
        
        if amount > user_balance:
            await callback.answer(
                f"❌ Недостаточно средств.\nВаш баланс: {user_balance} голды",
                show_alert=True
            )
            return
        
        await state.update_data(amount=amount)
        
        await callback.message.edit_text(
            f"🎮 <b>Сумма вывода:</b> {amount} голды\n\n"
            f"<b>Введите название скина:</b>\n"
            f"(Например: AK-47 | Красная линия, AWP | Дракон Лор, и т.д.)",
            parse_mode='HTML'
        )
        await state.set_state(WithdrawalStates.entering_skin_name)
        
    except ValueError:
        await callback.answer("❌ Ошибка. Попробуйте еще раз", show_alert=True)

@dp.message(WithdrawalStates.choosing_amount)
async def enter_custom_withdrawal_amount(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        user_balance = db.get_balance(message.from_user.id)
        
        if amount < MIN_WITHDRAWAL:
            await message.answer(
                f"❌ Минимальная сумма вывода: {MIN_WITHDRAWAL} голды\n"
                f"Введите сумму еще раз:"
            )
            return
        
        if amount > user_balance:
            await message.answer(
                f"❌ Недостаточно средств.\n"
                f"Ваш баланс: {user_balance} голды\n"
                f"Введите сумму еще раз:"
            )
            return
        
        await state.update_data(amount=amount)
        
        await message.answer(
            f"🎮 <b>Сумма вывода:</b> {amount} голды\n\n"
            f"<b>Введите название скина:</b>\n"
            f"(Например: AK-47 | Красная линия, AWP | Дракон Лор, и т.д.)",
            parse_mode='HTML'
        )
        await state.set_state(WithdrawalStates.entering_skin_name)
        
    except ValueError:
        await message.answer("❌ Введите целое число (например: 5000):")

@dp.message(WithdrawalStates.entering_skin_name)
async def enter_skin_name(message: types.Message, state: FSMContext):
    skin_name = message.text.strip()
    
    if len(skin_name) < 3:
        await message.answer("❌ Название скина слишком короткое. Введите снова:")
        return
    
    await state.update_data(skin_name=skin_name)
    
    await message.answer(
        f"🎮 <b>Скин:</b> {skin_name}\n\n"
        f"<b>Введите паттерн скина:</b>\n"
        f"(Например: 0.15, 0.07, или 'любой паттерн')",
        parse_mode='HTML'
    )
    await state.set_state(WithdrawalStates.entering_skin_pattern)

@dp.message(WithdrawalStates.entering_skin_pattern)
async def enter_skin_pattern(message: types.Message, state: FSMContext):
    skin_pattern = message.text.strip()
    data = await state.get_data()
    
    await state.update_data(skin_pattern=skin_pattern)
    
    await message.answer(
        f"🎮 <b>Скин:</b> {data['skin_name']}\n"
        f"🎨 <b>Паттерн:</b> {skin_pattern}\n\n"
        f"📸 <b>Теперь прикрепите скриншот</b> с вашим профилем в Project Evolution:\n"
        f"• Скриншот должен показывать ваш никнейм в игре\n"
        f"• Можно сделать скриншот профиля или инвентаря\n"
        f"• Это необходимо для подтверждения владения аккаунтом\n\n"
        f"<i>Отправьте фото прямо в чат...</i>",
        parse_mode='HTML'
    )
    await state.set_state(WithdrawalStates.waiting_for_screenshot)

@dp.message(WithdrawalStates.waiting_for_screenshot, F.photo)
async def receive_screenshot(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    
    # Проверяем, есть ли все необходимые данные
    if 'amount' not in data or 'skin_name' not in data or 'skin_pattern' not in data:
        await message.answer("❌ Ошибка: данные заявки неполные. Начните заново.")
        await state.clear()
        return
    
    # Получаем фото с наилучшим качеством
    photo = message.photo[-1]
    file_id = photo.file_id
    
    # Проверяем баланс еще раз
    user_balance = db.get_balance(user_id)
    if data['amount'] > user_balance:
        await message.answer(
            f"❌ Недостаточно средств.\n"
            f"Требуется: {data['amount']} голды\n"
            f"Ваш баланс: {user_balance} голды",
            parse_mode='HTML'
        )
        await state.clear()
        return
    
    # Создаем заявку на вывод
    try:
        withdrawal_id = db.create_withdrawal(
            user_id, 
            data['amount'],
            data['skin_name'],
            data['skin_pattern'],
            file_id  # Сохраняем file_id скриншота
        )
        
        if not withdrawal_id:
            await message.answer("❌ Ошибка при создании заявки. Попробуйте позже.")
            await state.clear()
            return
        
        # Получаем обновленные данные пользователя
        user = db.get_user(user_id)
        
        # Уведомляем пользователя
        await message.answer(
            f"✅ <b>Заявка на вывод #{withdrawal_id} создана!</b>\n\n"
            f"🎮 <b>Скин:</b> {data['skin_name']}\n"
            f"🎨 <b>Паттерн:</b> {data['skin_pattern']}\n"
            f"💰 <b>Стоимость:</b> {data['amount']} голды\n"
            f"📸 <b>Скриншот:</b> Прикреплен ✅\n"
            f"🎯 <b>Платформа:</b> Project Evolution\n\n"
            f"⏳ Заявка будет обработана в течение 24 часов.\n"
            f"📊 Статус можно отслеживать в разделе 'Статистика'.\n\n"
            f"🎮 <b>После одобрения скин будет доступен в вашем инвентаре Project Evolution!</b>",
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
        
        # Уведомляем администратора
        username = f"@{user['username']}" if user['username'] else user['first_name']
        
        admin_text = (
            f"🎮 <b>НОВАЯ ЗАЯВКА НА ВЫВОД В PROJECT EVOLUTION #{withdrawal_id}</b>\n\n"
            f"👤 <b>Игрок:</b> {username}\n"
            f"🆔 <b>ID:</b> {user_id}\n"
            f"💰 <b>Стоимость:</b> {data['amount']} голды\n"
            f"🎮 <b>Скин:</b> {data['skin_name']}\n"
            f"🎨 <b>Паттерн:</b> {data['skin_pattern']}\n"
            f"📸 <b>Скриншот:</b> Прикреплен ✅\n\n"
            f"✅ Одобрить: /approve_{withdrawal_id}\n"
            f"❌ Отклонить: /reject_{withdrawal_id}\n"
            f"👁️ Просмотр скриншота: /view_screenshot_{withdrawal_id}"
        )
        
        try:
            await bot.send_message(ADMIN_ID, admin_text, parse_mode='HTML')
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление админу: {e}")
            
    except Exception as e:
        logger.error(f"Ошибка при создании заявки: {e}")
        await message.answer("❌ Ошибка при создании заявки. Попробуйте позже.")
    
    await state.clear()

@dp.message(WithdrawalStates.waiting_for_screenshot)
async def wrong_screenshot_format(message: types.Message):
    await message.answer(
        "❌ <b>Пожалуйста, прикрепите скриншот как фото!</b>\n\n"
        "Нажмите на значок 📎 и выберите 'Фото' или 'Галерея'\n"
        "Скриншот должен показывать ваш профиль в Project Evolution.",
        parse_mode='HTML'
    )

# ========== ИГРА В КУБИКИ ==========
@dp.message(F.text == "🎲 Сделать ставку")
async def start_dice_game(message: types.Message):
    # Проверяем подписку
    is_allowed, subscription_info = await check_subscription_required(message.from_user.id)
    if not is_allowed:
        channels_text = subscription_info['channels_text']
        keyboard = subscription_info['keyboard']
        channels_count = subscription_info['channels_count']
        
        await message.answer(
            f"📢 <b>Для использования бота необходимо подписаться на каналы!</b>\n\n"
            f"Подпишитесь на наши каналы ({channels_count}):\n"
            f"{channels_text}",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        return
    
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Нажмите /start чтобы начать")
        return
    
    balance = user['balance']
    
    if balance < 100:
        await message.answer(
            f"❌ <b>Недостаточно голды для игры!</b>\n\n"
            f"💰 Ваш баланс: {balance} голды\n"
            f"🎮 Минимальная ставка: 100 голды\n\n"
            f"💎 Пригласите друзей или используйте промокод!",
            parse_mode='HTML'
        )
        return
    
    await message.answer(
        f"🎲 <b>Игра в кубики</b>\n\n"
        f"💰 <b>Доступно:</b> {balance} голды\n"
        f"🎮 <b>Правила:</b>\n"
        f"• Кидается кубик (от 1 до 6)\n"
        f"• Ставка на Чет/Нечет: x2 выигрыш\n"
        f"• Ставка на 1-3 или 4-6: x2 выигрыш\n\n"
        f"<b>Выберите сумму ставки:</b>",
        reply_markup=amount_keyboard(),
        parse_mode='HTML'
    )

@dp.callback_query(F.data.startswith("amount_"))
async def choose_bet_amount(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "amount_custom":
        await callback.message.edit_text(
            "🎲 <b>Введите сумму ставки:</b>\n"
            "(Минимум: 100 голды)",
            parse_mode='HTML'
        )
        await state.set_state(DiceBetStates.choosing_amount)
        return
    
    if callback.data == "cancel_bet":
        await state.clear()
        await callback.message.edit_text("❌ Ставка отменена.")
        await callback.message.answer("Главное меню:", reply_markup=main_menu())
        return
    
    amount_str = callback.data.replace("amount_", "")
    try:
        amount = int(amount_str)
        user_balance = db.get_balance(callback.from_user.id)
        
        if amount < 100:
            await callback.answer("❌ Минимальная ставка: 100 голды", show_alert=True)
            return
        
        if amount > user_balance:
            await callback.answer(f"❌ Недостаточно средств. Ваш баланс: {user_balance} голды", show_alert=True)
            return
        
        await state.update_data(amount=amount)
        
        await callback.message.edit_text(
            f"🎲 <b>Сумма ставки:</b> {amount} голды\n\n"
            f"<b>Выберите тип ставки:</b>\n"
            f"• Чет (2, 4, 6) - x2\n"
            f"• Нечет (1, 3, 5) - x2\n"
            f"• От 1-3 (1, 2, 3) - x2\n"
            f"• От 4-6 (4, 5, 6) - x2",
            reply_markup=dice_bet_keyboard(),
            parse_mode='HTML'
        )
        await state.set_state(DiceBetStates.choosing_bet_type)
        
    except ValueError:
        await callback.answer("❌ Ошибка. Попробуйте еще раз", show_alert=True)

@dp.message(DiceBetStates.choosing_amount)
async def enter_custom_bet_amount(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        user_balance = db.get_balance(message.from_user.id)
        
        if amount < 100:
            await message.answer(
                f"❌ Минимальная ставка: 100 голды\n"
                f"Введите сумму еще раз:"
            )
            return
        
        if amount > user_balance:
            await message.answer(
                f"❌ Недостаточно средств.\n"
                f"Ваш баланс: {user_balance} голды\n"
                f"Введите сумму еще раз:"
            )
            return
        
        await state.update_data(amount=amount)
        
        await message.answer(
            f"🎲 <b>Сумма ставки:</b> {amount} голды\n\n"
            f"<b>Выберите тип ставки:</b>\n"
            f"• Чет (2, 4, 6) - x2\n"
            f"• Нечет (1, 3, 5) - x2\n"
            f"• От 1-3 (1, 2, 3) - x2\n"
            f"• От 4-6 (4, 5, 6) - x2",
            reply_markup=dice_bet_keyboard(),
            parse_mode='HTML'
        )
        await state.set_state(DiceBetStates.choosing_bet_type)
        
    except ValueError:
        await message.answer("❌ Введите целое число (например: 1000):")

@dp.callback_query(DiceBetStates.choosing_bet_type, F.data.startswith("dice_"))
async def process_dice_bet(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "cancel_bet":
        await state.clear()
        await callback.message.edit_text("❌ Ставка отменена.")
        await callback.message.answer("Главное меню:", reply_markup=main_menu())
        return
    
    data = await state.get_data()
    if 'amount' not in data:
        await callback.answer("❌ Ошибка: сумма ставки не найдена", show_alert=True)
        await state.clear()
        return
    
    amount = data['amount']
    bet_type = callback.data.replace("dice_", "")
    
    # Проверяем баланс еще раз
    user_balance = db.get_balance(callback.from_user.id)
    if amount > user_balance:
        await callback.answer(f"❌ Недостаточно средств. Ваш баланс: {user_balance} голды", show_alert=True)
        await state.clear()
        return
    
    # Отправляем анимацию кубика
    dice_message = await callback.message.answer_dice(emoji="🎲")
    dice_value = dice_message.dice.value  # Получаем значение кубика (1-6)
    
    await asyncio.sleep(2)  # Ждем пока анимация завершится
    
    # Определяем результат
    win = False
    result_text = ""
    
    if bet_type == "even":
        win = dice_value % 2 == 0  # Четное
        result_text = "Чет" if win else "Нечет"
    elif bet_type == "odd":
        win = dice_value % 2 == 1  # Нечетное
        result_text = "Нечет" if win else "Чет"
    elif bet_type == "1_3":
        win = dice_value in [1, 2, 3]  # 1-3
        result_text = "1-3" if win else "4-6"
    elif bet_type == "4_6":
        win = dice_value in [4, 5, 6]  # 4-6
        result_text = "4-6" if win else "1-3"
    
    win_amount = amount * 2 if win else 0
    
    # Обрабатываем ставку в базе
    try:
        success = db.process_bet(
            callback.from_user.id,
            amount,
            'dice',
            f"Кубик: {dice_value} ({result_text})",
            win_amount
        )
        
        if not success:
            await callback.answer("❌ Ошибка при обработке ставки", show_alert=True)
            await state.clear()
            return
            
    except Exception as e:
        logger.error(f"Ошибка при обработке ставки: {e}")
        await callback.answer("❌ Ошибка при обработке ставки", show_alert=True)
        await state.clear()
        return
    
    # Получаем обновленный баланс
    user = db.get_user(callback.from_user.id)
    
    if win:
        await callback.message.answer(
            f"🎉 <b>ПОБЕДА!</b>\n\n"
            f"🎲 <b>Выпало:</b> {dice_value}\n"
            f"💰 <b>Ставка:</b> {amount} голды\n"
            f"💎 <b>Выигрыш:</b> {win_amount} голды\n"
            f"🏦 <b>Новый баланс:</b> {user['balance']} голды\n\n"
            f"🎮 <b>Вы удвоили свою ставку!</b>",
            parse_mode='HTML'
        )
    else:
        await callback.message.answer(
            f"❌ <b>ПРОИГРЫШ</b>\n\n"
            f"🎲 <b>Выпало:</b> {dice_value}\n"
            f"💰 <b>Ставка:</b> {amount} голды\n"
            f"🏦 <b>Новый баланс:</b> {user['balance']} голды\n\n"
            f"💪 <b>Попробуйте еще раз!</b>",
            parse_mode='HTML'
        )
    
    await state.clear()

@dp.message(F.text == "📊 История ставок")
async def show_bets_history(message: types.Message):
    # Проверяем подписку
    is_allowed, subscription_info = await check_subscription_required(message.from_user.id)
    if not is_allowed:
        channels_text = subscription_info['channels_text']
        keyboard = subscription_info['keyboard']
        channels_count = subscription_info['channels_count']
        
        await message.answer(
            f"📢 <b>Для использования бота необходимо подписаться на каналы!</b>\n\n"
            f"Подпишитесь на наши каналы ({channels_count}):\n"
            f"{channels_text}",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        return
    
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Нажмите /start чтобы начать")
        return
    
    bets = db.get_bets_history(message.from_user.id, limit=10)
    
    if not bets:
        await message.answer(
            "📊 <b>История ставок пуста</b>\n\n"
            "Сделайте свою первую ставку в разделе 🎮 Игры!",
            parse_mode='HTML'
        )
        return
    
    text = "📊 <b>Последние 10 ставок:</b>\n\n"
    
    for bet in bets:
        date = bet['created_at'][:16] if bet['created_at'] else "N/A"
        result = "✅ +" if bet['win_amount'] > 0 else "❌ -"
        amount = bet['win_amount'] if bet['win_amount'] > 0 else bet['amount']
        
        text += f"{result} <b>{amount}G</b> - {bet['result']}\n"
        text += f"   <i>{date}</i>\n\n"
    
    text += f"🎲 <b>Всего поставлено:</b> {user['total_wagered']} голды\n"
    text += f"💰 <b>Всего выиграно:</b> {user['total_won']} голды"
    
    await message.answer(text, parse_mode='HTML')

@dp.message(F.text == "👥 Мои рефералы")
async def show_referrals(message: types.Message):
    # Проверяем подписку
    is_allowed, subscription_info = await check_subscription_required(message.from_user.id)
    if not is_allowed:
        channels_text = subscription_info['channels_text']
        keyboard = subscription_info['keyboard']
        channels_count = subscription_info['channels_count']
        
        await message.answer(
            f"📢 <b>Для использования бота необходимо подписаться на каналы!</b>\n\n"
            f"Подпишитесь на наши каналы ({channels_count}):\n"
            f"{channels_text}",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        return
    
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Нажмите /start чтобы начать")
        return
    
    referrals = db.get_referrals(message.from_user.id)
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={message.from_user.id}"
    
    referral_bonus = int(db.get_setting('referral_bonus', 350))
    
    text = f"👥 <b>Ваши рефералы ({len(referrals)}):</b>\n\n"
    
    if referrals:
        for i, ref in enumerate(referrals[:15], 1):
            name = f"@{ref['username']}" if ref['username'] else ref['first_name']
            date = ref['created_at'][:10] if ref['created_at'] else "N/A"
            text += f"{i}. {name} - {date}\n"
        
        if len(referrals) > 15:
            text += f"\n... и еще {len(referrals) - 15} пользователей"
    else:
        text += "😔 Пока никого не пригласили...\n"
    
    text += f"\n🔗 <b>Ваша реферальная ссылка:</b>\n<code>{ref_link}</code>"
    text += f"\n\n💰 <b>За каждого друга:</b> {referral_bonus} голды"
    
    # Отправляем фото для раздела рефералов
    referrals_image = db.get_setting('referrals_image_url', REFERRALS_IMAGE_URL)
    if referrals_image and referrals_image.startswith('http'):
        try:
            await message.answer_photo(
                photo=referrals_image,
                caption=text,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Не удалось отправить фото рефералов: {e}")
            await message.answer(text, parse_mode='HTML')
    else:
        await message.answer(text, parse_mode='HTML')

@dp.message(PromoCodeState.entering_code)
async def enter_promo_code(message: types.Message, state: FSMContext):
    promo_code = message.text.strip().upper()
    success, result = db.use_promo_code(message.from_user.id, promo_code)
    
    if success:
        await message.answer(f"✅ {result}", parse_mode='HTML')
    else:
        await message.answer(f"❌ {result}", parse_mode='HTML')
    
    await state.clear()

@dp.message(F.text == "🎁 Промокод")
async def enter_promo_from_button(message: types.Message, state: FSMContext):
    # Проверяем подписку
    is_allowed, subscription_info = await check_subscription_required(message.from_user.id)
    if not is_allowed:
        channels_text = subscription_info['channels_text']
        keyboard = subscription_info['keyboard']
        channels_count = subscription_info['channels_count']
        
        await message.answer(
            f"📢 <b>Для использования бота необходимо подписаться на каналы!</b>\n\n"
            f"Подпишитесь на наши каналы ({channels_count}):\n"
            f"{channels_text}",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        return
    
    await message.answer("🎁 <b>Введите промокод:</b>", parse_mode='HTML')
    await state.set_state(PromoCodeState.entering_code)

@dp.message(F.text == "📊 Статистика")
async def show_statistics(message: types.Message):
    # Проверяем подписку
    is_allowed, subscription_info = await check_subscription_required(message.from_user.id)
    if not is_allowed:
        channels_text = subscription_info['channels_text']
        keyboard = subscription_info['keyboard']
        channels_count = subscription_info['channels_count']
        
        await message.answer(
            f"📢 <b>Для использования бота необходимо подписаться на каналы!</b>\n\n"
            f"Подпишитесь на наши каналы ({channels_count}):\n"
            f"{channels_text}",
            reply_markup=keyboard,
            parse_mode='HTML'
        )
        return
    
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("Нажмите /start чтобы начать")
        return
    
    referrals = db.get_referrals(message.from_user.id)
    withdrawals = db.get_withdrawals(user_id=message.from_user.id)
    referral_bonus = int(db.get_setting('referral_bonus', 350))
    
    if message.from_user.id == ADMIN_ID:
        # Админская статистика
        stats = db.get_stats()
        channels = db.get_subscription_channels()
        active_channels = len([c for c in channels if c['is_active'] == 1])
        contests = db.get_contests()
        active_contests = len([c for c in contests if c['status'] == 'active'])
        
        text = f"""
👑 <b>АДМИН СТАТИСТИКА</b>

👥 <b>Игроков всего:</b> {stats['total_users']}
💰 <b>Общая голда в системе:</b> {stats['total_balance']}
🎮 <b>Всего рефералов:</b> {stats['total_referrals']}

🎲 <b>Игровая статистика:</b>
├ Поставлено всего: {stats['total_wagered']} голды
└ Выиграно всего: {stats['total_won']} голды

⏳ <b>Ожидает скинов:</b> {stats['pending_withdrawals']} заявок
💸 <b>Выдано скинов на:</b> {stats['total_paid']} голды

📢 <b>Каналы подписки:</b>
├ Всего каналов: {len(channels)}
└ Активных: {active_channels}

🎯 <b>Конкурсы:</b>
├ Всего конкурсов: {len(contests)}
└ Активных: {active_contests}

⚙️ <b>Настройки:</b>
├ Бонус за друга: {referral_bonus} голды
└ Мин. вывод: {MIN_WITHDRAWAL} голды
        """
    else:
        # Обычная статистика игрока
        text = f"""
📊 <b>ВАША СТАТИСТИКА</b>

👤 <b>Профиль:</b>
├ ID: {user['user_id']}
├ Ник: {user['first_name']}
├ Баланс: {user['balance']} голды
└ Рефералов: {user['referrals']}

💰 <b>Заработок:</b>
├ На рефералах: {user['referrals'] * referral_bonus} голды
└ Доступно для вывода: {'✅ Да' if user['balance'] >= MIN_WITHDRAWAL else '❌ Нет'}

🎲 <b>Статистика игр:</b>
├ Поставлено: {user['total_wagered']} голды
├ Выиграно: {user['total_won']} голды
└ Профит: {user['total_won'] - user['total_wagered']} голды

🎮 <b>Заявки на скины:</b>
"""
        
        if withdrawals:
            for w in withdrawals[:3]:
                status_icons = {'pending': '⏳', 'paid': '✅', 'rejected': '❌'}
                text += f"{status_icons.get(w['status'], '❓')} #{w['id']}: {w['skin_name'][:30]}... - {w['status']}\n"
            
            if len(withdrawals) > 3:
                text += f"... и еще {len(withdrawals) - 3} заявок\n"
        else:
            text += "Нет активных заявок\n"
    
    await message.answer(text, parse_mode='HTML')

@dp.message(F.text == "ℹ️ Помощь")
async def show_help(message: types.Message):
    await cmd_help(message)

# ========== АДМИН ФУНКЦИИ ==========
@dp.message(F.text == "⬅️ В меню")
async def admin_to_main_menu(message: types.Message):
    await message.answer("Главное меню:", reply_markup=main_menu())

@dp.message(F.text == "📊 Общая статистика")
async def admin_overall_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    stats = db.get_stats()
    referral_bonus = int(db.get_setting('referral_bonus', 350))
    channels = db.get_subscription_channels()
    active_channels = len([c for c in channels if c['is_active'] == 1])
    contests = db.get_contests()
    active_contests = len([c for c in contests if c['status'] == 'active'])
    
    text = f"""
👑 <b>СТАТИСТИКА PROJECT EVOLUTION БОТА</b>

📈 <b>Общая:</b>
├ Игроков: {stats['total_users']}
├ Голда в системе: {stats['total_balance']}
├ Всего рефералов: {stats['total_referrals']}
└ Выдано скинов на: {stats['total_paid']} голды

🎲 <b>Игровая статистика:</b>
├ Поставлено всего: {stats['total_wagered']} голды
└ Выиграно всего: {stats['total_won']} голды

⏳ <b>На модерации:</b> {stats['pending_withdrawals']} заявок

📢 <b>Каналы подписки:</b>
├ Всего каналов: {len(channels)}
├ Активных: {active_channels}
└ Неактивных: {len(channels) - active_channels}

🎯 <b>Конкурсы:</b>
├ Всего конкурсов: {len(contests)}
├ Активных: {active_contests}
└ Завершенных: {len(contests) - active_contests}

💰 <b>Настройки:</b>
├ Реферальный бонус: {referral_bonus} голды
└ Мин. вывод скина: {MIN_WITHDRAWAL} голды
    """
    await message.answer(text, parse_mode='HTML')

@dp.message(F.text == "👥 Все пользователи")
async def admin_all_users(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    users = db.get_all_users()
    
    if not users:
        await message.answer("📭 Нет игроков в базе")
        return
    
    text = f"👥 <b>Все игроки ({len(users)}):</b>\n\n"
    
    for i, user in enumerate(users[:20], 1):
        username = f"@{user['username']}" if user['username'] else user['first_name']
        date = user['created_at'][:10] if user['created_at'] else "N/A"
        profit = user['total_won'] - user['total_wagered']
        profit_sign = "+" if profit > 0 else ""
        
        text += f"{i}. {username} - {user['balance']}G (Игры: {profit_sign}{profit}G) - {date}\n"
    
    if len(users) > 20:
        text += f"\n... и еще {len(users) - 20} игроков"
    
    await message.answer(text, parse_mode='HTML')

@dp.message(F.text == "🎮 Заявки на вывод")
async def admin_pending_withdrawals(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    withdrawals = db.get_withdrawals(status='pending')
    
    if not withdrawals:
        await message.answer("✅ Нет заявок на вывод в Project Evolution.")
        return
    
    text = "⏳ <b>Заявки на скины (ожидают):</b>\n\n"
    
    for w in withdrawals:
        user = db.get_user(w['user_id'])
        username = f"@{user['username']}" if user and user['username'] else user['first_name'] if user else f"ID: {w['user_id']}"
        
        screenshot_status = "✅" if w['screenshot_url'] else "❌"
        
        text += (
            f"🆔 <b>#{w['id']}</b>\n"
            f"👤 {username}\n"
            f"🎮 <b>Скин:</b> {w['skin_name']}\n"
            f"🎨 <b>Паттерн:</b> {w['skin_pattern']}\n"
            f"📸 <b>Скриншот:</b> {screenshot_status}\n"
            f"💰 {w['amount']} голды\n"
            f"✅ /approve_{w['id']}  ❌ /reject_{w['id']}  👁️ /view_screenshot_{w['id']}\n\n"
        )
    
    await message.answer(text, parse_mode='HTML')

@dp.message(F.text.startswith("/approve_"))
async def admin_approve_withdrawal(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        withdrawal_id = int(message.text.replace("/approve_", ""))
        
        if db.update_withdrawal_status(withdrawal_id, 'paid'):
            # Получаем информацию о выплате
            withdrawals = db.get_withdrawals()
            withdrawal = next((w for w in withdrawals if w['id'] == withdrawal_id), None)
            
            if withdrawal:
                # Уведомляем пользователя
                try:
                    await bot.send_message(
                        withdrawal['user_id'],
                        f"✅ <b>Ваша заявка на вывод #{withdrawal_id} одобрена!</b>\n\n"
                        f"🎮 <b>Скин:</b> {withdrawal['skin_name']}\n"
                        f"🎨 <b>Паттерн:</b> {withdrawal['skin_pattern']}\n"
                        f"💰 <b>Стоимость:</b> {withdrawal['amount']} голды\n\n"
                        f"🎯 <b>Скин добавлен в ваш инвентарь Project Evolution!</b>\n"
                        f"Проверьте игру для получения.",
                        parse_mode='HTML'
                    )
                except:
                    pass
            
            await message.answer(f"✅ Заявка #{withdrawal_id} одобрена.")
        else:
            await message.answer(f"❌ Заявка #{withdrawal_id} не найдена.")
            
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте: /approve_123")

@dp.message(F.text.startswith("/reject_"))
async def admin_reject_withdrawal(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        withdrawal_id = int(message.text.replace("/reject_", ""))
        
        if db.update_withdrawal_status(withdrawal_id, 'rejected'):
            # Получаем информацию о выплате
            withdrawals = db.get_withdrawals()
            withdrawal = next((w for w in withdrawals if w['id'] == withdrawal_id), None)
            
            if withdrawal:
                # Уведомляем пользователя
                try:
                    await bot.send_message(
                        withdrawal['user_id'],
                        f"❌ <b>Ваша заявка на вывод #{withdrawal_id} отклонена.</b>\n\n"
                        f"🎮 <b>Скин:</b> {withdrawal['skin_name']}\n"
                        f"💰 <b>Стоимость:</b> {withdrawal['amount']} голды\n\n"
                        f"💎 Голда возвращена на баланс.",
                        parse_mode='HTML'
                    )
                except:
                    pass
            
            await message.answer(f"❌ Заявка #{withdrawal_id} отклонена.")
        else:
            await message.answer(f"❌ Заявка #{withdrawal_id} не найдена.")
            
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте: /reject_123")

@dp.message(Command("view_screenshot_"))
async def view_withdrawal_screenshot(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        withdrawal_id = int(message.text.replace("/view_screenshot_", ""))
        withdrawals = db.get_withdrawals()
        withdrawal = next((w for w in withdrawals if w['id'] == withdrawal_id), None)
        
        if not withdrawal:
            await message.answer(f"❌ Заявка #{withdrawal_id} не найдена.")
            return
        
        if not withdrawal['screenshot_url']:
            await message.answer(f"❌ Для заявки #{withdrawal_id} скриншот не прикреплен.")
            return
        
        # Получаем информацию о пользователе
        user = db.get_user(withdrawal['user_id'])
        username = f"@{user['username']}" if user and user['username'] else user['first_name'] if user else f"ID: {withdrawal['user_id']}"
        
        caption = (
            f"📸 <b>Скриншот для заявки #{withdrawal_id}</b>\n\n"
            f"👤 <b>Игрок:</b> {username}\n"
            f"🎮 <b>Скин:</b> {withdrawal['skin_name']}\n"
            f"🎨 <b>Паттерн:</b> {withdrawal['skin_pattern']}\n"
            f"💰 <b>Сумма:</b> {withdrawal['amount']} голды\n"
            f"📅 <b>Дата:</b> {withdrawal['created_at'][:16] if withdrawal['created_at'] else 'N/A'}"
        )
        
        try:
            await bot.send_photo(
                chat_id=message.chat.id,
                photo=withdrawal['screenshot_url'],
                caption=caption,
                parse_mode='HTML'
            )
        except:
            await message.answer(f"❌ Не удалось загрузить скриншот для заявки #{withdrawal_id}")
            
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте: /view_screenshot_123")

@dp.message(F.text == "💰 Выдать голду")
async def admin_add_gold_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "💰 <b>Выдача голды пользователю</b>\n\n"
        "Введите ID пользователя или @username:",
        parse_mode='HTML'
    )
    await state.set_state(AdminAddGoldState.entering_user_id)

@dp.message(AdminAddGoldState.entering_user_id)
async def admin_add_gold_user_id(message: types.Message, state: FSMContext):
    user_input = message.text.strip()
    user = None
    
    # Пробуем найти пользователя
    if user_input.startswith('@'):
        # По username
        username = user_input[1:]
        all_users = db.get_all_users()
        for u in all_users:
            if u['username'] == username:
                user = u
                break
    else:
        # По ID
        try:
            user_id = int(user_input)
            user = db.get_user(user_id)
        except ValueError:
            pass
    
    if not user:
        await message.answer("❌ Пользователь не найден. Введите снова:")
        return
    
    await state.update_data(user_id=user['user_id'], username=user['first_name'])
    await message.answer(
        f"👤 <b>Найден пользователь:</b> {user['first_name']} (ID: {user['user_id']})\n\n"
        f"Введите количество голды (можно отрицательное для списания):",
        parse_mode='HTML'
    )
    await state.set_state(AdminAddGoldState.entering_amount)

@dp.message(AdminAddGoldState.entering_amount)
async def admin_add_gold_amount(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        await state.update_data(amount=amount)
        
        await message.answer(
            "Введите описание операции (например: 'Бонус за активность'):"
        )
        await state.set_state(AdminAddGoldState.entering_description)
    except ValueError:
        await message.answer("❌ Введите целое число:")

@dp.message(AdminAddGoldState.entering_description)
async def admin_add_gold_description(message: types.Message, state: FSMContext):
    description = message.text.strip()
    data = await state.get_data()
    
    success = db.update_balance(data['user_id'], data['amount'], description)
    
    if success:
        # Получаем обновленные данные пользователя
        user = db.get_user(data['user_id'])
        
        # Уведомляем пользователя
        try:
            operation = "начислена" if data['amount'] > 0 else "списана"
            await bot.send_message(
                data['user_id'],
                f"💰 <b>Изменение баланса!</b>\n\n"
                f"{operation.capitalize()} <b>{abs(data['amount'])} голды</b>\n"
                f"💎 <b>Причина:</b> {description}\n"
                f"🏦 <b>Текущий баланс:</b> {user['balance']} голды",
                parse_mode='HTML'
            )
        except:
            pass
        
        await message.answer(
            f"✅ <b>Баланс обновлен!</b>\n\n"
            f"👤 Пользователь: {data['username']}\n"
            f"💰 Изменение: {data['amount']} голды\n"
            f"📝 Описание: {description}\n"
            f"💎 Новый баланс: {user['balance']} голды",
            parse_mode='HTML',
            reply_markup=admin_main_menu()
        )
    else:
        await message.answer("❌ Ошибка при обновлении баланса")
    
    await state.clear()

# ========== ИСПРАВЛЕННЫЕ КОНКУРСЫ ==========
@dp.message(F.text == "🎯 Конкурсы")
async def admin_contests_menu_handler(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    # Проверяем и завершаем просроченные конкурсы
    await check_and_end_contests()
    
    await message.answer(
        "🎯 <b>Управление конкурсами</b>\n\n"
        "Здесь вы можете создавать и управлять конкурсами с призами в голде.\n"
        "Конкурсы автоматически завершаются по истечении времени и выбирают победителя.",
        reply_markup=admin_contests_menu(),
        parse_mode='HTML'
    )

@dp.message(F.text == "📋 Активные конкурсы")
async def admin_list_contests(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    contests = db.get_contests()
    
    if not contests:
        await message.answer("📭 Нет активных конкурсов")
        return
    
    text = "🎯 <b>Список конкурсов:</b>\n\n"
    
    for contest in contests:
        status_emoji = "🟢" if contest['status'] == 'active' else "🔴" if contest['status'] == 'completed' else "⚫"
        participants_count = db.get_contest_participant_count(contest['id'])
        winner_text = ""
        
        if contest['winner_id']:
            winner_user = db.get_user(contest['winner_id'])
            winner_name = f"@{winner_user['username']}" if winner_user and winner_user['username'] else winner_user['first_name'] if winner_user else f"ID: {contest['winner_id']}"
            winner_text = f"\n🏅 <b>Победитель:</b> {winner_name}"
        
        text += (
            f"{status_emoji} <b>Конкурс #{contest['id']}</b>\n"
            f"🏆 <b>Название:</b> {contest['name']}\n"
            f"💰 <b>Приз:</b> {contest['prize_amount']} голды\n"
            f"👥 <b>Участников:</b> {participants_count}\n"
            f"📅 <b>Создан:</b> {contest['created_at'][:16] if contest['created_at'] else 'N/A'}\n"
            f"{winner_text}\n\n"
        )
    
    await message.answer(text, parse_mode='HTML')

@dp.message(F.text == "➕ Создать конкурс")
async def admin_create_contest_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "➕ <b>Создание нового конкурса</b>\n\n"
        "Введите название конкурса:",
        parse_mode='HTML'
    )
    await state.set_state(AdminCreateContestState.entering_name)

@dp.message(AdminCreateContestState.entering_name)
async def admin_create_contest_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    
    if len(name) < 3:
        await message.answer("❌ Название слишком короткое. Введите снова:")
        return
    
    await state.update_data(name=name)
    await message.answer(
        f"🏆 <b>Название конкурса:</b> {name}\n\n"
        f"Введите описание конкурса:",
        parse_mode='HTML'
    )
    await state.set_state(AdminCreateContestState.entering_description)

@dp.message(AdminCreateContestState.entering_description)
async def admin_create_contest_description(message: types.Message, state: FSMContext):
    description = message.text.strip()
    
    if len(description) < 5:
        await message.answer("❌ Описание слишком короткое. Введите снова:")
        return
    
    await state.update_data(description=description)
    await message.answer(
        f"📝 <b>Описание:</b> {description}\n\n"
        f"Введите сумму приза в голде:",
        parse_mode='HTML'
    )
    await state.set_state(AdminCreateContestState.entering_prize_amount)

@dp.message(AdminCreateContestState.entering_prize_amount)
async def admin_create_contest_prize_amount(message: types.Message, state: FSMContext):
    try:
        prize_amount = int(message.text.strip())
        
        if prize_amount < 100:
            await message.answer("❌ Минимальная сумма приза: 100 голды. Введите снова:")
            return
        
        await state.update_data(prize_amount=prize_amount)
        await message.answer(
            f"💰 <b>Приз:</b> {prize_amount} голды\n\n"
            f"Введите продолжительность конкурса в часах (1-720):",
            parse_mode='HTML'
        )
        await state.set_state(AdminCreateContestState.entering_duration)
    except ValueError:
        await message.answer("❌ Введите целое число:")

@dp.message(AdminCreateContestState.entering_duration)
async def admin_create_contest_duration(message: types.Message, state: FSMContext):
    try:
        duration = int(message.text.strip())
        
        if duration < 1 or duration > 720:
            await message.answer("❌ Продолжительность должна быть от 1 до 720 часов. Введите снова:")
            return
        
        data = await state.get_data()
        
        # Создаем конкурс в базе
        contest_id = db.create_contest(
            data['name'],
            data['description'],
            data['prize_amount'],
            ADMIN_ID,
            duration
        )
        
        if contest_id:
            # Получаем созданный конкурс
            contest = db.get_contest(contest_id)
            
            # Создаем сообщение с кнопкой участия
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(
                        text="🎯 Участвовать в конкурсе",
                        callback_data=f"join_contest_{contest_id}"
                    )]
                ]
            )
            
            contest_message = format_contest_message(contest)
            
            try:
                # Пытаемся отправить в канал конкурсов
                if CONTESTS_CHANNEL_ID:
                    sent_message = await bot.send_message(
                        CONTESTS_CHANNEL_ID,
                        contest_message,
                        reply_markup=keyboard,
                        parse_mode='HTML'
                    )
                    db.update_contest_message_id(contest_id, sent_message.message_id)
                    
                    await message.answer(
                        f"✅ <b>Конкурс создан и опубликован в канале!</b>\n\n"
                        f"🏆 <b>Название:</b> {data['name']}\n"
                        f"📝 <b>Описание:</b> {data['description']}\n"
                        f"💰 <b>Приз:</b> {data['prize_amount']} голды\n"
                        f"⏰ <b>Продолжительность:</b> {duration} часов\n\n"
                        f"🎯 Конкурс опубликован в канале конкурсов.",
                        parse_mode='HTML',
                        reply_markup=admin_contests_menu()
                    )
                else:
                    # Если нет канала, отправляем админу
                    sent_message = await message.answer(
                        contest_message,
                        reply_markup=keyboard,
                        parse_mode='HTML'
                    )
                    db.update_contest_message_id(contest_id, sent_message.message_id)
                    
                    await message.answer(
                        f"✅ <b>Конкурс создан!</b>\n\n"
                        f"🏆 <b>Название:</b> {data['name']}\n"
                        f"📝 <b>Описание:</b> {data['description']}\n"
                        f"💰 <b>Приз:</b> {data['prize_amount']} голды\n"
                        f"⏰ <b>Продолжительность:</b> {duration} часов\n\n"
                        f"🎯 Конкурс опубликован выше. Вы можете отправить его в канал или группу.",
                        parse_mode='HTML',
                        reply_markup=admin_contests_menu()
                    )
            except Exception as e:
                logger.error(f"Ошибка при публикации конкурса: {e}")
                await message.answer(
                    f"✅ Конкурс создан, но не удалось опубликовать: {e}\n"
                    f"ID конкурса: {contest_id}",
                    reply_markup=admin_contests_menu()
                )
        else:
            await message.answer(
                "❌ Не удалось создать конкурс. Попробуйте позже.",
                reply_markup=admin_contests_menu()
            )
        
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите целое число:")

# Обработчик для участия в конкурсе
@dp.callback_query(F.data.startswith("join_contest_"))
async def join_contest_callback(callback: types.CallbackQuery):
    try:
        contest_id = int(callback.data.replace("join_contest_", ""))
    except ValueError:
        await callback.answer("❌ Ошибка: неверный ID конкурса", show_alert=True)
        return
    
    contest = db.get_contest(contest_id)
    
    if not contest:
        await callback.answer("❌ Конкурс не найден", show_alert=True)
        return
    
    if contest['status'] != 'active':
        await callback.answer("❌ Конкурс уже завершен", show_alert=True)
        return
    
    # Проверяем подписку
    is_allowed, subscription_info = await check_subscription_required(callback.from_user.id)
    if not is_allowed:
        await callback.answer("❌ Для участия необходимо подписаться на каналы", show_alert=True)
        return
    
    # Проверяем, не участвует ли уже пользователь
    success, message = db.join_contest(
        contest_id,
        callback.from_user.id,
        callback.from_user.username,
        callback.from_user.first_name
    )
    
    if success:
        # Обновляем сообщение конкурса
        participants_count = db.get_contest_participant_count(contest_id)
        updated_message = format_contest_message(contest, participants_count=participants_count)
        
        try:
            if contest.get('message_id'):
                # Пытаемся обновить в канале
                try:
                    await bot.edit_message_text(
                        chat_id=CONTESTS_CHANNEL_ID,
                        message_id=contest['message_id'],
                        text=updated_message,
                        parse_mode='HTML',
                        reply_markup=callback.message.reply_markup
                    )
                except:
                    # Если не в канале, обновляем у админа
                    await bot.edit_message_text(
                        chat_id=ADMIN_ID,
                        message_id=contest['message_id'],
                        text=updated_message,
                        parse_mode='HTML',
                        reply_markup=callback.message.reply_markup
                    )
        except:
            pass
        
        await callback.answer(message, show_alert=True)
    else:
        await callback.answer(message, show_alert=True)

@dp.message(F.text == "🏆 Завершить конкурс")
async def admin_end_contest_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    contests = db.get_contests(status='active')
    
    if not contests:
        await message.answer("📭 Нет активных конкурсов для завершения")
        return
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    for contest in contests:
        keyboard.row(
            InlineKeyboardButton(
                text=f"#{contest['id']} - {contest['name']} ({contest['prize_amount']}G)",
                callback_data=f"end_contest_{contest['id']}"
            )
        )
    
    await message.answer(
        "🏆 <b>Выберите конкурс для завершения:</b>\n\n"
        "При завершении конкурса будет автоматически выбран победитель "
        "и приз будет начислен на его баланс.",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    await state.set_state(AdminEndContestState.choosing_contest)

@dp.callback_query(F.data.startswith("end_contest_"))
async def admin_end_contest_execute(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    
    contest_id = int(callback.data.replace("end_contest_", ""))
    contest = db.get_contest(contest_id)
    
    if not contest:
        await callback.answer("❌ Конкурс не найден", show_alert=True)
        await state.clear()
        return
    
    # Выбираем победителя
    winner, message = db.select_contest_winner(contest_id)
    
    if winner:
        # Уведомляем победителя
        try:
            winner_user = db.get_user(winner['user_id'])
            winner_name = f"@{winner_user['username']}" if winner_user and winner_user['username'] else winner_user['first_name'] if winner_user else f"ID: {winner['user_id']}"
            
            await bot.send_message(
                winner['user_id'],
                f"🎉 <b>ПОЗДРАВЛЯЕМ!</b>\n\n"
                f"🏆 <b>Вы победили в конкурсе:</b> {contest['name']}\n"
                f"💰 <b>Приз:</b> {contest['prize_amount']} голды\n"
                f"💎 <b>Приз начислен на ваш баланс!</b>\n\n"
                f"🎮 Проверьте баланс в боте.",
                parse_mode='HTML'
            )
            
            # Обновляем сообщение конкурса
            participants_count = db.get_contest_participant_count(contest_id)
            updated_message = format_contest_message(contest, winner_name, participants_count)
            
            try:
                if contest.get('message_id'):
                    # Пытаемся обновить в канале
                    try:
                        await bot.edit_message_text(
                            chat_id=CONTESTS_CHANNEL_ID,
                            message_id=contest['message_id'],
                            text=updated_message,
                            parse_mode='HTML',
                            reply_markup=None
                        )
                    except:
                        # Если не в канале, обновляем у админа
                        await bot.edit_message_text(
                            chat_id=ADMIN_ID,
                            message_id=contest['message_id'],
                            text=updated_message,
                            parse_mode='HTML',
                            reply_markup=None
                        )
            except Exception as e:
                logger.error(f"Не удалось обновить сообщение конкурса: {e}")
            
            await callback.message.edit_text(
                f"✅ <b>Конкурс завершен!</b>\n\n"
                f"🏆 <b>Конкурс:</b> {contest['name']}\n"
                f"💰 <b>Приз:</b> {contest['prize_amount']} голды\n"
                f"🏅 <b>Победитель:</b> {winner_name}\n\n"
                f"💎 Приз начислен победителю.",
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Ошибка при уведомлении победителя: {e}")
            await callback.message.edit_text(
                f"✅ Конкурс завершен, но не удалось уведомить победителя: {e}",
                parse_mode='HTML'
            )
    else:
        # Нет участников, просто завершаем
        db.end_contest(contest_id)
        await callback.message.edit_text(
            f"✅ <b>Конкурс завершен без победителя</b>\n\n"
            f"🏆 <b>Конкурс:</b> {contest['name']}\n"
            f"💰 <b>Приз:</b> {contest['prize_amount']} голды\n\n"
            f"👥 Не было участников.",
            parse_mode='HTML'
        )
    
    await state.clear()

@dp.message(F.text == "🗑️ Удалить конкурс")
async def admin_delete_contest_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    contests = db.get_contests()
    
    if not contests:
        await message.answer("📭 Нет конкурсов для удаления")
        return
    
    keyboard = InlineKeyboardMarkup(row_width=1)
    for contest in contests:
        status_emoji = "🟢" if contest['status'] == 'active' else "🔴"
        keyboard.row(
            InlineKeyboardButton(
                text=f"{status_emoji} #{contest['id']} - {contest['name']}",
                callback_data=f"delete_contest_{contest['id']}"
            )
        )
    
    await message.answer(
        "🗑️ <b>Выберите конкурс для удаления:</b>\n\n"
        "Внимание: удаление конкурса также удалит всех участников.",
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    await state.set_state(AdminDeleteContestState.choosing_contest)

@dp.callback_query(F.data.startswith("delete_contest_"))
async def admin_delete_contest_confirm(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    contest_id = int(callback.data.replace("delete_contest_", ""))
    contest = db.get_contest(contest_id)
    
    if not contest:
        await callback.answer("❌ Конкурс не найден", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.row(
        InlineKeyboardButton(
            text="✅ Да, удалить",
            callback_data=f"confirm_delete_contest_{contest_id}"
        ),
        InlineKeyboardButton(
            text="❌ Нет, отмена",
            callback_data="cancel_delete_contest"
        )
    )
    
    await callback.message.edit_text(
        f"⚠️ <b>Вы уверены, что хотите удалить конкурс?</b>\n\n"
        f"🏆 <b>Конкурс:</b> {contest['name']}\n"
        f"💰 <b>Приз:</b> {contest['prize_amount']} голды\n"
        f"📊 <b>Статус:</b> {contest['status']}\n\n"
        f"При удалении будут удалены все записи об участниках.",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

@dp.callback_query(F.data.startswith("confirm_delete_contest_"))
async def admin_delete_contest_execute(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    contest_id = int(callback.data.replace("confirm_delete_contest_", ""))
    
    success = db.delete_contest(contest_id)
    
    if success:
        await callback.message.edit_text(
            "✅ <b>Конкурс удален!</b>\n\n"
            "Конкурс и все связанные данные удалены.",
            parse_mode='HTML'
        )
    else:
        await callback.message.edit_text(
            "❌ Не удалось удалить конкурс",
            parse_mode='HTML'
        )

@dp.callback_query(F.data == "cancel_delete_contest")
async def admin_cancel_delete_contest(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    await callback.message.edit_text(
        "❌ Удаление конкурса отменено.",
        parse_mode='HTML'
    )

@dp.message(F.text == "⚙️ Настройки")
async def admin_settings_menu_handler(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    referral_bonus = int(db.get_setting('referral_bonus', 350))
    channels = db.get_subscription_channels(active_only=False)
    active_channels = len([c for c in channels if c['is_active'] == 1])
    subscription_required = "✅ ВКЛ" if db.get_setting('subscription_required', '1') == '1' else "❌ ВЫКЛ"
    
    text = f"""
⚙️ <b>Настройки бота</b>

💰 <b>Текущий реферальный бонус:</b> {referral_bonus} голды
📢 <b>Каналов для подписки:</b> {len(channels)} (активных: {active_channels})
🔔 <b>Обязательная подписка:</b> {subscription_required}

Выберите настройку для изменения:
    """
    
    await message.answer(text, reply_markup=admin_settings_menu(), parse_mode='HTML')

@dp.message(F.text == "💰 Изменить реф. бонус")
async def admin_change_referral_bonus(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    current_bonus = int(db.get_setting('referral_bonus', 350))
    await message.answer(
        f"💰 <b>Изменение реферального бонуса</b>\n\n"
        f"Текущий бонус: {current_bonus} голды\n\n"
        f"Введите новое количество голды за одного реферала:",
        parse_mode='HTML'
    )
    await state.set_state(AdminSettingsState.changing_referral_bonus)

@dp.message(AdminSettingsState.changing_referral_bonus)
async def admin_save_referral_bonus(message: types.Message, state: FSMContext):
    try:
        new_bonus = int(message.text.strip())
        if new_bonus < 0:
            await message.answer("❌ Бонус не может быть отрицательным. Введите снова:")
            return
        
        db.update_setting('referral_bonus', str(new_bonus))
        
        await message.answer(
            f"✅ <b>Реферальный бонус изменен!</b>\n\n"
            f"💰 <b>Новый бонус:</b> {new_bonus} голды за одного реферала\n\n"
            f"Теперь за каждого приглашенного друга пользователи будут получать {new_bonus} голды.",
            parse_mode='HTML',
            reply_markup=admin_main_menu()
        )
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите целое число:")

@dp.message(F.text == "📢 Управление каналами")
async def admin_manage_channels_menu(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "📢 <b>Управление каналами для подписки</b>\n\n"
        "Здесь вы можете добавлять, редактировать и удалять каналы, "
        "на которые пользователи должны подписаться для использования бота.",
        reply_markup=admin_channels_menu(),
        parse_mode='HTML'
    )

@dp.message(F.text == "📋 Список каналов")
async def admin_list_channels(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    channels = db.get_subscription_channels(active_only=False)
    
    if not channels:
        await message.answer("📭 Нет добавленных каналов")
        return
    
    text = "📢 <b>Список каналов для подписки:</b>\n\n"
    
    for i, channel in enumerate(channels, 1):
        status = "✅ Активен" if channel['is_active'] == 1 else "❌ Неактивен"
        text += f"{i}. {channel['channel_username']}\n"
        text += f"   Ссылка: {channel['channel_link']}\n"
        text += f"   Статус: {status}\n"
        text += f"   ID канала: {channel['id']}\n\n"
    
    text += "⚡ <b>Быстрые действия:</b>\n"
    text += "/activate_channel_1 - Активировать канал\n"
    text += "/deactivate_channel_1 - Деактивировать канал\n"
    text += "/delete_channel_1 - Удалить канал\n"
    
    await message.answer(text, parse_mode='HTML')

@dp.message(F.text == "➕ Добавить канал")
async def admin_add_channel_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "➕ <b>Добавление нового канала</b>\n\n"
        "Введите @username канала (например: @my_channel):",
        parse_mode='HTML'
    )
    await state.set_state(AdminChannelState.adding_channel_username)

@dp.message(AdminChannelState.adding_channel_username)
async def admin_add_channel_username(message: types.Message, state: FSMContext):
    channel_username = message.text.strip()
    
    # Проверяем формат
    if not channel_username.startswith('@'):
        await message.answer("❌ Username должен начинаться с @ (например: @my_channel). Введите снова:")
        return
    
    await state.update_data(channel_username=channel_username)
    
    await message.answer(
        f"📢 <b>Username канала:</b> {channel_username}\n\n"
        f"Введите ссылку на канал (можно просто username без @):",
        parse_mode='HTML'
    )
    await state.set_state(AdminChannelState.adding_channel_link)

@dp.message(AdminChannelState.adding_channel_link)
async def admin_add_channel_link(message: types.Message, state: FSMContext):
    channel_link = message.text.strip()
    data = await state.get_data()
    
    # Если пользователь ввел username вместо ссылки, преобразуем
    if channel_link.startswith('@'):
        username = channel_link.replace('@', '').strip()
        channel_link = f"https://t.me/{username}"
    elif not channel_link.startswith('http') and not '/' in channel_link:
        # Предполагаем что это username без @
        channel_link = f"https://t.me/{channel_link}"
    elif not channel_link.startswith('http'):
        await message.answer("❌ Ссылка должна начинаться с http:// или https://. Введите снова:")
        return
    
    # Добавляем канал в базу
    success = db.add_subscription_channel(data['channel_username'], channel_link)
    
    if success:
        await message.answer(
            f"✅ <b>Канал успешно добавлен!</b>\n\n"
            f"📢 <b>Канал:</b> {data['channel_username']}\n"
            f"🔗 <b>Ссылка:</b> {channel_link}\n\n"
            f"Теперь пользователям необходимо подписаться на этот канал.",
            parse_mode='HTML',
            reply_markup=admin_channels_menu()
        )
    else:
        await message.answer(
            "❌ Не удалось добавить канал. Возможно, канал с таким username уже существует.",
            reply_markup=admin_channels_menu()
        )
    
    await state.clear()

@dp.message(F.text == "🔧 Вкл/Выкл подписку")
async def admin_toggle_subscription(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    current_status = db.get_setting('subscription_required', '1')
    new_status = '0' if current_status == '1' else '1'
    
    status_text = "отключена" if new_status == '0' else "включена"
    status_emoji = "❌" if new_status == '0' else "✅"
    
    db.update_setting('subscription_required', new_status)
    
    await message.answer(
        f"{status_emoji} <b>Обязательная подписка {status_text}!</b>\n\n"
        f"Теперь пользователям {'НЕ ' if new_status == '0' else ''}нужно подписываться на каналы для использования бота.",
        parse_mode='HTML',
        reply_markup=admin_main_menu()
    )

@dp.message(F.text == "⬅️ Назад в настройки")
async def admin_back_to_settings(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    await admin_settings_menu_handler(message)

@dp.message(F.text == "⬅️ Назад в админку")
async def admin_back_to_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer("👑 <b>Панель администратора Project Evolution</b>", reply_markup=admin_main_menu(), parse_mode='HTML')

@dp.message(F.text == "🎁 Промокоды")
async def admin_promo_codes_menu(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Список промокодов")],
            [KeyboardButton(text="✨ Создать промокод")],
            [KeyboardButton(text="🗑️ Удалить промокод")],
            [KeyboardButton(text="⬅️ Назад в админку")]
        ],
        resize_keyboard=True
    )
    
    await message.answer("🎁 <b>Управление промокодами</b>", reply_markup=keyboard, parse_mode='HTML')

@dp.message(F.text == "📋 Список промокодов")
async def admin_list_promo_codes(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    promo_codes = db.get_promo_codes()
    
    if not promo_codes:
        await message.answer("📭 Нет активных промокодов")
        return
    
    text = "🎁 <b>Активные промокоды:</b>\n\n"
    
    for promo in promo_codes:
        text += (
            f"<code>{promo['code']}</code>\n"
            f"💰 {promo['amount']} голды\n"
            f"🔄 {promo['max_uses'] - promo['uses_left']}/{promo['max_uses']} использований\n"
            f"📅 {promo['created_at'][:10]}\n\n"
        )
    
    await message.answer(text, parse_mode='HTML')

@dp.message(F.text == "✨ Создать промокод")
async def admin_create_promo_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "✨ <b>Создание промокода</b>\n\n"
        "Введите количество голды для промокода:",
        parse_mode='HTML'
    )
    await state.set_state(AdminCreatePromoState.entering_amount)

@dp.message(AdminCreatePromoState.entering_amount)
async def admin_create_promo_amount(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text.strip())
        if amount <= 0:
            await message.answer("❌ Количество должно быть больше 0. Введите снова:")
            return
        
        await state.update_data(amount=amount)
        await message.answer(
            f"💰 <b>Сумма:</b> {amount} голды\n\n"
            f"Введите количество использований (макс. 1000):",
            parse_mode='HTML'
        )
        await state.set_state(AdminCreatePromoState.entering_uses)
    except ValueError:
        await message.answer("❌ Введите целое число:")

@dp.message(AdminCreatePromoState.entering_uses)
async def admin_create_promo_uses(message: types.Message, state: FSMContext):
    try:
        uses = int(message.text.strip())
        if uses <= 0 or uses > 1000:
            await message.answer("❌ Количество использований должно быть от 1 до 1000. Введите снова:")
            return
        
        data = await state.get_data()
        
        # Генерируем промокод
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
        # Создаем промокод в базе
        success = db.create_promo_code(code, data['amount'], uses, ADMIN_ID)
        
        if success:
            await message.answer(
                f"✅ <b>Промокод создан!</b>\n\n"
                f"🎁 <b>Код:</b> <code>{code}</code>\n"
                f"💰 <b>Сумма:</b> {data['amount']} голды\n"
                f"🔄 <b>Использований:</b> {uses}\n\n"
                f"📋 Для активации: /promo или кнопка '🎁 Промокод'",
                parse_mode='HTML',
                reply_markup=admin_main_menu()
            )
        else:
            await message.answer("❌ Ошибка при создании промокода (возможно, такой код уже существует)")
        
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите целое число:")

@dp.message(F.text == "🗑️ Удалить промокод")
async def admin_delete_promo_start(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    promo_codes = db.get_promo_codes()
    
    if not promo_codes:
        await message.answer("📭 Нет промокодов для удаления")
        return
    
    keyboard = InlineKeyboardMarkup(row_width=2)
    buttons = []
    for promo in promo_codes[:10]:  # Показываем первые 10
        buttons.append(InlineKeyboardButton(
            text=f"{promo['code']} ({promo['amount']}G)",
            callback_data=f"delete_promo_{promo['code']}"
        ))
    
    # Разделяем на строки по 2 кнопки
    for i in range(0, len(buttons), 2):
        if i + 1 < len(buttons):
            keyboard.row(buttons[i], buttons[i+1])
        else:
            keyboard.row(buttons[i])
    
    await message.answer(
        "🗑️ <b>Выберите промокод для удаления:</b>",
        reply_markup=keyboard,
        parse_mode='HTML'
    )

@dp.callback_query(F.data.startswith("delete_promo_"))
async def admin_delete_promo_confirm(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    code = callback.data.replace("delete_promo_", "")
    
    success = db.delete_promo_code(code)
    
    if success:
        await callback.message.edit_text(f"✅ Промокод <code>{code}</code> удален!", parse_mode='HTML')
    else:
        await callback.message.edit_text(f"❌ Не удалось удалить промокод <code>{code}</code>", parse_mode='HTML')

@dp.message(F.text == "📢 Рассылка")
async def admin_start_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    await message.answer(
        "📢 <b>Введите сообщение для рассылки:</b>\n"
        "Можно использовать HTML-разметку.\n"
        "Для отмены: /cancel",
        parse_mode='HTML'
    )
    await state.set_state(BroadcastState.waiting_for_message)

@dp.message(BroadcastState.waiting_for_message, Command("cancel"))
async def admin_cancel_broadcast(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Рассылка отменена.", reply_markup=admin_main_menu())

@dp.message(BroadcastState.waiting_for_message)
async def admin_send_broadcast(message: types.Message, state: FSMContext):
    users = db.get_all_users()
    total = len(users)
    success = 0
    failed = 0
    
    await message.answer(f"📤 Рассылка для {total} пользователей...")
    
    for user in users:
        try:
            await bot.send_message(user['user_id'], message.text, parse_mode='HTML')
            success += 1
            await asyncio.sleep(0.05)  # Небольшая задержка чтобы не превысить лимиты
        except:
            failed += 1
    
    await message.answer(
        f"✅ Рассылка завершена!\n\n"
        f"📊 Статистика:\n"
        f"• Всего пользователей: {total}\n"
        f"• Успешно: {success}\n"
        f"• Не удалось: {failed}",
        reply_markup=admin_main_menu()
    )
    await state.clear()

# ========== ИСПРАВЛЕННЫЕ КОМАНДЫ ДЛЯ БЫСТРОГО УПРАВЛЕНИЯ КАНАЛАМИ ==========
@dp.message(Command("activate_channel_"))
async def quick_activate_channel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        channel_id = int(message.text.replace("/activate_channel_", ""))
        if db.update_subscription_channel(channel_id, is_active=1):
            await message.answer(f"✅ Канал #{channel_id} активирован")
        else:
            await message.answer(f"❌ Не удалось активировать канал #{channel_id}")
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте: /activate_channel_1")

@dp.message(Command("deactivate_channel_"))
async def quick_deactivate_channel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        channel_id = int(message.text.replace("/deactivate_channel_", ""))
        if db.update_subscription_channel(channel_id, is_active=0):
            await message.answer(f"❌ Канал #{channel_id} деактивирован")
        else:
            await message.answer(f"❌ Не удалось деактивировать канал #{channel_id}")
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте: /deactivate_channel_1")

@dp.message(Command("delete_channel_"))
async def quick_delete_channel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        channel_id = int(message.text.replace("/delete_channel_", ""))
        if db.delete_subscription_channel(channel_id):
            await message.answer(f"🗑️ Канал #{channel_id} удален")
        else:
            await message.answer(f"❌ Не удалось удалить канал #{channel_id}")
    except ValueError:
        await message.answer("❌ Неверный формат. Используйте: /delete_channel_1")

# ========== ЗАПУСК БОТА ==========
async def main():
    logger.info("=" * 60)
    logger.info("🎮 ЗАПУСК PROJECT EVOLUTION БОТА С КОНКУРСАМИ")
    logger.info(f"👑 Админ ID: {ADMIN_ID}")
    logger.info(f"💰 Реферальный бонус: {db.get_setting('referral_bonus', 350)} голды")
    logger.info(f"🎮 Минимальный вывод: {MIN_WITHDRAWAL} голды")
    logger.info(f"📢 Канал для конкурсов: {CONTESTS_CHANNEL_ID}")
    
    # Получаем список каналов
    channels = db.get_subscription_channels(active_only=True)
    logger.info(f"📢 Каналов для подписки: {len(channels)}")
    for i, channel in enumerate(channels, 1):
        logger.info(f"   {i}. {channel['channel_username']} -> {channel['channel_link']}")
    
    # Логируем добавленные фотографии
    logger.info("📸 Фотографии для разделов:")
    logger.info(f"   Баланс: {db.get_setting('balance_image_url', BALANCE_IMAGE_URL)}")
    logger.info(f"   Вывод: {db.get_setting('withdrawal_image_url', WITHDRAWAL_IMAGE_URL)}")
    logger.info(f"   Игры: {db.get_setting('games_image_url', GAMES_IMAGE_URL)}")
    logger.info(f"   Рефералы: {db.get_setting('referrals_image_url', REFERRALS_IMAGE_URL)}")
    
    logger.info("=" * 60)
    
    try:
        bot_info = await bot.get_me()
        logger.info(f"🤖 Бот: @{bot_info.username} - {bot_info.full_name}")
        
        # Запускаем периодическую проверку конкурсов
        asyncio.create_task(periodic_contest_check())
        
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске бота: {e}")

async def periodic_contest_check():
    """Периодически проверяет и завершает конкурсы"""
    while True:
        try:
            await check_and_end_contests()
            await asyncio.sleep(300)  # Проверяем каждые 5 минут
        except Exception as e:
            logger.error(f"Ошибка в периодической проверке конкурсов: {e}")
            await asyncio.sleep(300)

if __name__ == "__main__":
    asyncio.run(main())
