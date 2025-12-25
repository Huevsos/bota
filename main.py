import asyncio
import json
import random
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    User
)
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
    ContextTypes, 
    ConversationHandler,
    filters
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Ваши данные
OWNER_ID = 7546928092
ADMIN_GROUP_ID = -5197819981
NOTIFICATION_CHANNEL_ID = -1003663395719
TOKEN = "7939238322:AAEAN-l0srLH7YmNRCbWBDRWzwd-fwN025w"

# Состояния для ConversationHandler
class States(Enum):
    TEAM_NAME = 1
    TEAM_PHOTO = 2
    PLAYERS = 3
    PLAYER_USERNAMES = 4
    DEVICE_TYPE = 5
    CONFIRM_REGISTRATION = 6
    ADMIN_SETTINGS = 7
    ADMIN_TEAM_LIMIT = 8
    ADMIN_PLAYER_LIMIT = 9
    ADMIN_ADD_ADMIN = 10
    ADMIN_ADD_PLAYER = 11

# Хранилище данных
@dataclass
class Player:
    telegram_id: Optional[int]
    username: str
    full_name: str = ""
    device_type: str = ""  # PC или MOBILE
    cc_ms: str = ""  # CC/MS система для мобильных игроков
    contact_confirmed: bool = False
    
    def to_dict(self):
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data):
        return cls(**data)

@dataclass
class Team:
    name: str
    photo: str
    captain_id: int
    captain_username: str
    players: List[Player]
    device_type: str
    status: str = "pending"  # pending, approved, rejected
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
    
    def to_dict(self):
        data = asdict(self)
        data['players'] = [player.to_dict() for player in self.players]
        data['created_at'] = self.created_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data):
        data['players'] = [Player.from_dict(p) for p in data['players']]
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        return cls(**data)

class Storage:
    def __init__(self):
        self.teams: Dict[str, Team] = {}
        self.admins: List[int] = [OWNER_ID]  # Владелец автоматически админ
        self.config = {
            "max_teams": 16,
            "players_per_team": 5,
            "registration_open": True,
            "brackets_generated": False,
            "notification_channel": NOTIFICATION_CHANNEL_ID
        }
        self.registrations: Dict[int, dict] = {}
        self.matches = []
        
    def save_to_file(self, filename='tournament_data.json'):
        """Сохранить данные в файл"""
        data = {
            'teams': {name: team.to_dict() for name, team in self.teams.items()},
            'admins': self.admins,
            'config': self.config,
            'matches': self.matches
        }
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def load_from_file(self, filename='tournament_data.json'):
        """Загрузить данные из файла"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.teams = {
                name: Team.from_dict(team_data) 
                for name, team_data in data.get('teams', {}).items()
            }
            self.admins = data.get('admins', self.admins)
            self.config = data.get('config', self.config)
            self.matches = data.get('matches', [])
            logger.info("Данные загружены из файла")
        except FileNotFoundError:
            logger.info("Файл данных не найден, создан новый")
        except Exception as e:
            logger.error(f"Ошибка загрузки данных: {e}")

storage = Storage()

class TournamentBot:
    def __init__(self, token: str):
        self.token = token
        self.load_data()
    
    def load_data(self):
        """Загрузка данных при инициализации"""
        storage.load_from_file()
    
    def save_data(self):
        """Сохранение данных"""
        storage.save_to_file()
    
    async def is_admin(self, user_id: int) -> bool:
        """Проверка, является ли пользователь админом"""
        return user_id in storage.admins
    
    async def add_admin(self, user_id: int):
        """Добавить администратора"""
        if user_id not in storage.admins:
            storage.admins.append(user_id)
            self.save_data()
            return True
        return False
    
    async def remove_admin(self, user_id: int):
        """Удалить администратора"""
        if user_id in storage.admins and user_id != OWNER_ID:
            storage.admins.remove(user_id)
            self.save_data()
            return True
        return False
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.effective_user
        user_id = user.id
        
        if not storage.config["registration_open"]:
            await update.message.reply_text(
                "❌ Регистрация на турнир закрыта!",
                reply_markup=ReplyKeyboardRemove()
            )
            return
        
        # Проверяем, не зарегистрирована ли уже команда
        user_teams = [team for team in storage.teams.values() 
                     if any(player.telegram_id == user_id for player in team.players)]
        
        if user_teams:
            await update.message.reply_text(
                "⚠️ Вы уже зарегистрированы в команде!\n"
                f"Ваша команда: {user_teams[0].name}",
                reply_markup=ReplyKeyboardRemove()
            )
            return
        
        # Проверяем, не является ли пользователь капитаном другой команды
        for team in storage.teams.values():
            if team.captain_id == user_id:
                await update.message.reply_text(
                    "⚠️ Вы уже являетесь капитаном команды!\n"
                    f"Ваша команда: {team.name}",
                    reply_markup=ReplyKeyboardRemove()
                )
                return
        
        keyboard = [
            [InlineKeyboardButton("PC 🖥️", callback_data="device_pc")],
            [InlineKeyboardButton("MOBILE 📱", callback_data="device_mobile")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🎮 Добро пожаловать в регистрацию на турнир!\n\n"
            f"Текущие настройки турнира:\n"
            f"• Максимум команд: {storage.config['max_teams']}\n"
            f"• Игроков в команде: {storage.config['players_per_team']}\n"
            f"• Доступно мест: {storage.config['max_teams'] - len([t for t in storage.teams.values() if t.status == 'approved'])}\n\n"
            f"Выберите тип устройства для вашей команды:",
            reply_markup=reply_markup
        )
        
        return States.DEVICE_TYPE.value
    
    async def choose_device(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Выбор типа устройства"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        device_type = "PC" if "pc" in query.data else "MOBILE"
        
        # Сохраняем выбор устройства
        storage.registrations[user_id] = {
            "device_type": device_type,
            "captain_id": user_id,
            "captain_username": query.from_user.username or query.from_user.first_name,
            "captain_full_name": query.from_user.full_name
        }
        
        await query.edit_message_text(
            f"✅ Тип устройства выбран: {device_type}\n\n"
            "Теперь введите название вашей команды:"
        )
        
        return States.TEAM_NAME.value
    
    async def get_team_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение названия команды"""
        user_id = update.message.from_user.id
        team_name = update.message.text.strip()
        
        # Проверяем, не занято ли название
        if team_name in storage.teams:
            await update.message.reply_text(
                "❌ Это название команды уже занято! Пожалуйста, выберите другое название:"
            )
            return States.TEAM_NAME.value
        
        if len(team_name) < 3:
            await update.message.reply_text(
                "❌ Название команды должно быть не менее 3 символов!"
            )
            return States.TEAM_NAME.value
        
        storage.registrations[user_id]["team_name"] = team_name
        
        await update.message.reply_text(
            f"✅ Название команды сохранено: {team_name}\n\n"
            "Теперь отправьте фото для вашей команды (логотип, групповое фото и т.д.):"
        )
        
        return States.TEAM_PHOTO.value
    
    async def get_team_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение фото команды"""
        user_id = update.message.from_user.id
        
        if not update.message.photo:
            await update.message.reply_text("Пожалуйста, отправьте фото!")
            return States.TEAM_PHOTO.value
        
        # Берем последнее (самое большое) фото
        photo = update.message.photo[-1]
        photo_id = photo.file_id
        
        storage.registrations[user_id]["photo_id"] = photo_id
        
        await update.message.reply_text(
            "✅ Фото команды сохранено!\n\n"
            "Теперь введите количество игроков в команде (включая себя):"
        )
        
        return States.PLAYERS.value
    
    async def get_players_count(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение количества игроков"""
        user_id = update.message.from_user.id
        
        try:
            players_count = int(update.message.text)
            max_players = storage.config["players_per_team"]
            
            if players_count < 2:
                await update.message.reply_text(
                    "❌ В команде должно быть как минимум 2 игрока!\n"
                    "Введите количество игроков:"
                )
                return States.PLAYERS.value
            
            if players_count > max_players:
                await update.message.reply_text(
                    f"❌ Слишком много игроков! Максимум {max_players}\n"
                    "Введите количество игроков:"
                )
                return States.PLAYERS.value
            
            storage.registrations[user_id]["players_count"] = players_count
            storage.registrations[user_id]["players"] = []
            
            # Начинаем сбор информации об игроках
            context.user_data["current_player"] = 1
            context.user_data["total_players"] = players_count
            
            # Создаем капитана
            captain = Player(
                telegram_id=user_id,
                username=f"@{update.message.from_user.username}" if update.message.from_user.username else update.message.from_user.first_name,
                full_name=update.message.from_user.full_name,
                device_type=storage.registrations[user_id]["device_type"],
                contact_confirmed=True
            )
            
            # Назначаем CC/MS для капитана если MOBILE
            if captain.device_type == "MOBILE":
                captain.cc_ms = "CC"  # Капитан всегда CC
            
            storage.registrations[user_id]["players"].append(captain)
            
            if players_count > 1:
                context.user_data["current_player"] = 2
                
                await update.message.reply_text(
                    f"✅ Капитан добавлен!\n\n"
                    f"🎮 Игрок 2 из {players_count}\n"
                    "Введите Telegram username игрока (например, @username):"
                )
                return States.PLAYER_USERNAMES.value
            else:
                # Только капитан в команде
                return await self.show_confirmation(update, context)
            
        except ValueError:
            await update.message.reply_text("❌ Пожалуйста, введите число!")
            return States.PLAYERS.value
    
    async def get_player_usernames(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получение username игроков"""
        user_id = update.effective_user.id
        current_player = context.user_data.get("current_player", 1)
        total_players = context.user_data.get("total_players", 1)
        
        username = update.message.text.strip()
        
        # Добавляем @ если отсутствует
        if not username.startswith('@'):
            username = '@' + username
        
        # Сохраняем username
        context.user_data[f"player_{current_player}_username"] = username
        
        # Создаем игрока
        player = Player(
            telegram_id=None,  # Пока не привязан
            username=username,
            full_name="",  # Без имени
            device_type=storage.registrations[user_id]["device_type"],
            contact_confirmed=False
        )
        
        # Назначаем CC/MS для мобильных игроков
        if player.device_type == "MOBILE":
            # Четные игроки - MS, нечетные - CC (капитан уже CC)
            player.cc_ms = "MS" if current_player % 2 == 0 else "CC"
        
        storage.registrations[user_id]["players"].append(player)
        
        # Переходим к следующему игроку или завершаем
        if current_player < total_players:
            context.user_data["current_player"] = current_player + 1
            
            await update.message.reply_text(
                f"✅ Игрок {current_player} добавлен!\n\n"
                f"🎮 Игрок {current_player + 1} из {total_players}\n"
                "Введите Telegram username игрока (например, @username):"
            )
            return States.PLAYER_USERNAMES.value
        else:
            # Все игроки добавлены
            return await self.show_confirmation(update, context)
    
    async def show_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показ подтверждения регистрации"""
        user_id = update.effective_user.id
        
        if user_id not in storage.registrations:
            await update.message.reply_text("❌ Данные регистрации не найдены!")
            return ConversationHandler.END
        
        reg_data = storage.registrations[user_id]
        
        # Формируем текст подтверждения
        players_text = ""
        for i, player in enumerate(reg_data["players"], 1):
            device_info = player.device_type
            if player.device_type == "MOBILE" and player.cc_ms:
                device_info = f"{player.device_type} ({player.cc_ms})"
            
            contact_status = "✅" if player.contact_confirmed else "⚠️ Не подтвержден"
            
            players_text += (
                f"{i}. {player.username}\n"
                f"   Устройство: {device_info}\n"
                f"   Статус: {contact_status}\n\n"
            )
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_registration"),
                InlineKeyboardButton("🔄 Изменить", callback_data="edit_registration"),
                InlineKeyboardButton("❌ Отменить", callback_data="cancel_registration")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        caption = (
            f"📋 Подтверждение регистрации:\n\n"
            f"🏆 Название команды: {reg_data['team_name']}\n"
            f"📱 Тип устройства: {reg_data['device_type']}\n"
            f"👥 Игроков: {len(reg_data['players'])}/{storage.config['players_per_team']}\n\n"
            f"Состав команды:\n{players_text}\n"
            f"⚠️ Внимание: Другие игроки должны подтвердить участие через бота!"
        )
        
        if update.callback_query:
            await update.callback_query.message.reply_photo(
                photo=reg_data["photo_id"],
                caption=caption,
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_photo(
                photo=reg_data["photo_id"],
                caption=caption,
                reply_markup=reply_markup
            )
        
        return States.CONFIRM_REGISTRATION.value
    
    async def confirm_registration(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Подтверждение регистрации"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        
        if query.data == "cancel_registration":
            del storage.registrations[user_id]
            await query.edit_message_caption(
                caption="❌ Регистрация отменена.\nНажмите /start чтобы начать заново."
            )
            return ConversationHandler.END
        
        elif query.data == "edit_registration":
            await query.edit_message_caption(
                caption="Редактирование регистрации...\nВведите новое название команды:"
            )
            return States.TEAM_NAME.value
        
        # Проверяем, есть ли место для новых команд
        approved_count = len([t for t in storage.teams.values() if t.status == "approved"])
        if approved_count >= storage.config["max_teams"]:
            await query.edit_message_caption(
                caption="❌ Достигнут лимит команд! Регистрация закрыта."
            )
            del storage.registrations[user_id]
            return ConversationHandler.END
        
        # Создаем команду
        reg_data = storage.registrations[user_id]
        team = Team(
            name=reg_data["team_name"],
            photo=reg_data["photo_id"],
            captain_id=reg_data["captain_id"],
            captain_username=reg_data["captain_username"],
            players=reg_data["players"],
            device_type=reg_data["device_type"]
        )
        
        storage.teams[team.name] = team
        
        # Отправляем заявку в админскую группу
        admin_keyboard = [
            [
                InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{team.name}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{team.name}"),
                InlineKeyboardButton("ℹ️ Подробнее", callback_data=f"info_{team.name}")
            ]
        ]
        admin_reply_markup = InlineKeyboardMarkup(admin_keyboard)
        
        # Формируем текст для админов
        players_list = "\n".join([
            f"{i+1}. {p.username} - {p.device_type}"
            f"{' (' + p.cc_ms + ')' if p.cc_ms else ''}"
            f" - {'✅' if p.contact_confirmed else '⚠️'}"
            for i, p in enumerate(team.players)
        ])
        
        admin_text = (
            f"📨 НОВАЯ ЗАЯВКА НА ТУРНИР!\n\n"
            f"🏆 Команда: {team.name}\n"
            f"📱 Тип устройства: {team.device_type}\n"
            f"👤 Капитан: {team.captain_username}\n"
            f"👥 Игроков: {len(team.players)}/{storage.config['players_per_team']}\n"
            f"📅 Дата подачи: {team.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"Состав команды:\n{players_list}"
        )
        
        try:
            # Отправляем в админскую группу
            await context.bot.send_photo(
                chat_id=ADMIN_GROUP_ID,
                photo=team.photo,
                caption=admin_text,
                reply_markup=admin_reply_markup
            )
        except Exception as e:
            logger.error(f"Ошибка отправки в админ-группу: {e}")
        
        # Отправляем уведомления игрокам (кроме капитана)
        for i, player in enumerate(team.players[1:], 2):
            confirm_keyboard = [
                [
                    InlineKeyboardButton(
                        "✅ Подтвердить участие", 
                        callback_data=f"player_confirm_{team.name}_{i}"
                    ),
                    InlineKeyboardButton(
                        "❌ Отказаться", 
                        callback_data=f"player_decline_{team.name}_{i}"
                    )
                ]
            ]
            confirm_markup = InlineKeyboardMarkup(confirm_keyboard)
            
            try:
                # Отправляем сообщение с кнопкой подтверждения
                # Игрок должен нажать кнопку для подтверждения
                sent_message = await context.bot.send_message(
                    chat_id=team.captain_id,  # Отправляем капитану для теста
                    text=(
                        f"📨 Уведомление для игрока {player.username}:\n\n"
                        f"Вас добавили в команду '{team.name}' для участия в турнире!\n\n"
                        f"Капитан: {team.captain_username}\n"
                        f"Ваше устройство: {player.device_type}"
                        f"{' (' + player.cc_ms + ')' if player.cc_ms else ''}\n\n"
                        f"Пожалуйста, подтвердите свое участие нажав кнопку ниже:"
                    ),
                    reply_markup=confirm_markup
                )
                
                # Сохраняем message_id для возможности удаления/редактирования
                context.user_data[f"notify_msg_{team.name}_{i}"] = sent_message.message_id
                
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления игроку {player.username}: {e}")
        
        await query.edit_message_caption(
            caption=(
                "✅ Заявка отправлена на модерацию!\n\n"
                f"Команда: {team.name}\n"
                "Статус: ⏳ На рассмотрении\n\n"
                "Уведомления отправлены другим игрокам."
            )
        )
        
        del storage.registrations[user_id]
        self.save_data()
        return ConversationHandler.END
    
    async def player_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Подтверждение участия игроком"""
        query = update.callback_query
        await query.answer()
        
        _, action, team_name, player_idx = query.data.split('_')
        player_idx = int(player_idx) - 1  # Переводим в 0-based индекс
        
        if team_name not in storage.teams:
            await query.edit_message_text("❌ Команда не найдена!")
            return
        
        team = storage.teams[team_name]
        
        if player_idx >= len(team.players):
            await query.edit_message_text("❌ Игрок не найден!")
            return
        
        player = team.players[player_idx]
        
        if action == "confirm":
            # Привязываем Telegram ID игрока
            player.telegram_id = query.from_user.id
            player.contact_confirmed = True
            
            await query.edit_message_text(
                f"✅ Вы подтвердили участие в команде '{team.name}'!\n\n"
                f"Ваше устройство: {player.device_type}"
                f"{' (' + player.cc_ms + ')' if player.cc_ms else ''}\n\n"
                f"Ожидайте подтверждения команды администратором."
            )
            
            # Уведомляем капитана
            try:
                await context.bot.send_message(
                    chat_id=team.captain_id,
                    text=f"✅ Игрок {player.username} подтвердил участие в команде!"
                )
            except Exception as e:
                logger.error(f"Ошибка уведомления капитана: {e}")
                
        elif action == "decline":
            # Удаляем игрока из команды
            team.players.pop(player_idx)
            
            await query.edit_message_text(
                "❌ Вы отказались от участия в команде."
            )
            
            # Уведомляем капитана
            try:
                await context.bot.send_message(
                    chat_id=team.captain_id,
                    text=f"❌ Игрок {player.username} отказался от участия в команде!"
                )
            except Exception as e:
                logger.error(f"Ошибка уведомления капитана: {e}")
        
        self.save_data()
    
    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Панель администратора"""
        user_id = update.effective_user.id
        
        if not await self.is_admin(user_id):
            await update.message.reply_text("❌ Эта команда только для администраторов!")
            return
        
        keyboard = [
            [InlineKeyboardButton("⚙️ Настройки турнира", callback_data="admin_settings")],
            [InlineKeyboardButton("👥 Управление админами", callback_data="admin_manage")],
            [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton("🎮 Управление командами", callback_data="admin_teams")],
            [InlineKeyboardButton("🔧 Дополнительные функции", callback_data="admin_tools")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        approved_count = len([t for t in storage.teams.values() if t.status == "approved"])
        pending_count = len([t for t in storage.teams.values() if t.status == "pending"])
        
        await update.message.reply_text(
            f"👑 Панель администратора\n\n"
            f"📈 Статистика:\n"
            f"• Всего команд: {len(storage.teams)}\n"
            f"• Одобрено: {approved_count}\n"
            f"• На рассмотрении: {pending_count}\n"
            f"• Лимит команд: {storage.config['max_teams']}\n"
            f"• Свободно мест: {storage.config['max_teams'] - approved_count}\n"
            f"• Игроков в команде: {storage.config['players_per_team']}\n"
            f"• Регистрация: {'✅ Открыта' if storage.config['registration_open'] else '❌ Закрыта'}\n"
            f"• Сетка: {'✅ Сгенерирована' if storage.config['brackets_generated'] else '❌ Не сгенерирована'}",
            reply_markup=reply_markup
        )
    
    async def admin_settings_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню настроек турнира"""
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [
                InlineKeyboardButton("📊 Максимум команд", callback_data="setting_max_teams"),
                InlineKeyboardButton("👥 Игроков в команде", callback_data="setting_players_per_team")
            ],
            [
                InlineKeyboardButton("🔓 Открыть регистрацию", callback_data="setting_open_reg"),
                InlineKeyboardButton("🔒 Закрыть регистрацию", callback_data="setting_close_reg")
            ],
            [
                InlineKeyboardButton("🎮 Сгенерировать сетку", callback_data="setting_generate_brackets"),
                InlineKeyboardButton("📢 Опубликовать в канал", callback_data="setting_post_channel")
            ],
            [InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "⚙️ Настройки турнира:\n\n"
            f"1. Максимум команд: {storage.config['max_teams']}\n"
            f"2. Игроков в команде: {storage.config['players_per_team']}\n"
            f"3. Регистрация: {'✅ Открыта' if storage.config['registration_open'] else '❌ Закрыта'}\n"
            f"4. Сетка сгенерирована: {'✅ Да' if storage.config['brackets_generated'] else '❌ Нет'}\n"
            f"5. ID канала: {storage.config['notification_channel']}",
            reply_markup=reply_markup
        )
    
    async def admin_manage_admins(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Управление администраторами"""
        query = update.callback_query
        await query.answer()
        
        keyboard = [
            [InlineKeyboardButton("➕ Добавить админа", callback_data="admin_add")],
            [InlineKeyboardButton("➖ Удалить админа", callback_data="admin_remove")],
            [InlineKeyboardButton("📋 Список админов", callback_data="admin_list")],
            [InlineKeyboardButton("◀️ Назад", callback_data="admin_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        admin_list = "\n".join([f"• {admin_id}" for admin_id in storage.admins])
        
        await query.edit_message_text(
            "👥 Управление администраторами\n\n"
            f"Всего админов: {len(storage.admins)}\n\n"
            f"Список админов:\n{admin_list}",
            reply_markup=reply_markup
        )
    
    async def admin_add_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Добавление администратора"""
        query = update.callback_query
        await query.answer()
        
        await query.edit_message_text(
            "➕ Добавление администратора\n\n"
            "Отправьте мне:\n"
            "1. User ID пользователя (цифры)\n"
            "2. Или перешлите сообщение от пользователя\n\n"
            "Для отмены отправьте /cancel"
        )
        
        return States.ADMIN_ADD_ADMIN.value
    
    async def process_add_admin(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка добавления админа"""
        user_id = update.effective_user.id
        
        if update.message.text == '/cancel':
            await update.message.reply_text("❌ Добавление админа отменено.")
            return ConversationHandler.END
        
        # Пытаемся получить ID пользователя
        target_user_id = None
        
        if update.message.forward_from:
            # Если переслано сообщение
            target_user_id = update.message.forward_from.id
            username = update.message.forward_from.username or "без username"
            
        elif update.message.text and update.message.text.isdigit():
            # Если введен ID
            target_user_id = int(update.message.text)
            username = f"ID {target_user_id}"
            
        if target_user_id:
            success = await self.add_admin(target_user_id)
            if success:
                await update.message.reply_text(f"✅ Пользователь {username} (ID: {target_user_id}) добавлен в админы!")
            else:
                await update.message.reply_text("⚠️ Этот пользователь уже является админом!")
        else:
            await update.message.reply_text(
                "❌ Не удалось определить ID пользователя.\n"
                "Попробуйте еще раз или отправьте /cancel"
            )
            return States.ADMIN_ADD_ADMIN.value
        
        self.save_data()
        return ConversationHandler.END
    
    async def admin_change_setting(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Изменение настроек турнира"""
        query = update.callback_query
        await query.answer()
        
        setting = query.data.replace("setting_", "")
        
        if setting == "max_teams":
            await query.edit_message_text(
                "Введите новое максимальное количество команд:"
            )
            return States.ADMIN_TEAM_LIMIT.value
            
        elif setting == "players_per_team":
            await query.edit_message_text(
                "Введите новое количество игроков в команде:"
            )
            return States.ADMIN_PLAYER_LIMIT.value
            
        elif setting == "open_reg":
            storage.config["registration_open"] = True
            await query.edit_message_text("✅ Регистрация открыта!")
            
        elif setting == "close_reg":
            storage.config["registration_open"] = False
            await query.edit_message_text("❌ Регистрация закрыта!")
            
        elif setting == "generate_brackets":
            await self.generate_brackets(query, context)
            
        elif setting == "post_channel":
            await self.post_to_channel(query, context)
            
        self.save_data()
    
    async def process_team_limit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка изменения лимита команд"""
        try:
            max_teams = int(update.message.text)
            
            if max_teams < 2:
                await update.message.reply_text("❌ Минимум 2 команды!")
                return States.ADMIN_TEAM_LIMIT.value
            
            # Проверяем, не меньше ли текущее количество одобренных команд
            approved_count = len([t for t in storage.teams.values() if t.status == "approved"])
            if max_teams < approved_count:
                await update.message.reply_text(
                    f"❌ Нельзя установить меньше {approved_count} команд "
                    f"(столько уже одобрено)!"
                )
                return States.ADMIN_TEAM_LIMIT.value
            
            storage.config["max_teams"] = max_teams
            self.save_data()
            
            await update.message.reply_text(
                f"✅ Максимальное количество команд установлено: {max_teams}"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Пожалуйста, введите число!")
            return States.ADMIN_TEAM_LIMIT.value
        
        return ConversationHandler.END
    
    async def process_player_limit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка изменения лимита игроков"""
        try:
            players_per_team = int(update.message.text)
            
            if players_per_team < 2:
                await update.message.reply_text("❌ Минимум 2 игрока в команде!")
                return States.ADMIN_PLAYER_LIMIT.value
            
            storage.config["players_per_team"] = players_per_team
            self.save_data()
            
            await update.message.reply_text(
                f"✅ Количество игроков в команде установлено: {players_per_team}"
            )
            
        except ValueError:
            await update.message.reply_text("❌ Пожалуйста, введите число!")
            return States.ADMIN_PLAYER_LIMIT.value
        
        return ConversationHandler.END
    
    async def generate_brackets(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Генерация сетки турнира"""
        if isinstance(update, Update):
            message = update.message
        else:
            message = update
        
        approved_teams = [team for team in storage.teams.values() if team.status == "approved"]
        
        if len(approved_teams) < 2:
            if hasattr(message, 'reply_text'):
                await message.reply_text("❌ Недостаточно команд для генерации сетки!")
            else:
                await message.edit_message_text("❌ Недостаточно команд для генерации сетки!")
            return
        
        if storage.config["brackets_generated"]:
            if hasattr(message, 'reply_text'):
                await message.reply_text("⚠️ Сетка уже сгенерирована!")
            else:
                await message.edit_message_text("⚠️ Сетка уже сгенерирована!")
            return
        
        # Закрываем регистрацию
        storage.config["registration_open"] = False
        
        # Перемешиваем команды
        random.shuffle(approved_teams)
        
        # Создаем пары
        storage.matches.clear()
        for i in range(0, len(approved_teams), 2):
            if i + 1 < len(approved_teams):
                match = {
                    "team1": approved_teams[i].name,
                    "team2": approved_teams[i + 1].name,
                    "round": 1,
                    "winner": None
                }
                storage.matches.append(match)
        
        storage.config["brackets_generated"] = True
        self.save_data()
        
        # Формируем текст сетки
        brackets_text = "🎮 ТУРНИРНАЯ СЕТКА СГЕНЕРИРОВАНА!\n\n"
        brackets_text += f"Всего команд: {len(approved_teams)}\n\n"
        
        for idx, match in enumerate(storage.matches, 1):
            team1 = storage.teams[match['team1']]
            team2 = storage.teams[match['team2']]
            
            brackets_text += (
                f"⚔️ МАТЧ {idx}:\n"
                f"   {team1.name} ({team1.device_type})\n"
                f"   vs\n"
                f"   {team2.name} ({team2.device_type})\n\n"
            )
        
        brackets_text += "🎯 Удачи всем участникам!"
        
        # Отправляем всем капитанам
        for team in approved_teams:
            try:
                await context.bot.send_message(
                    chat_id=team.captain_id,
                    text=(
                        f"🎉 Турнирная сетка сгенерирована!\n\n"
                        f"Регистрация закрыта.\n"
                        f"{brackets_text}"
                    )
                )
            except Exception as e:
                logger.error(f"Ошибка отправки капитану {team.name}: {e}")
        
        # Публикуем в канал
        try:
            await context.bot.send_message(
                chat_id=NOTIFICATION_CHANNEL_ID,
                text=brackets_text
            )
        except Exception as e:
            logger.error(f"Ошибка отправки в канал: {e}")
        
        if hasattr(message, 'reply_text'):
            await message.reply_text(
                f"✅ Сетка турнира сгенерирована!\n\n"
                f"Уведомления отправлены всем капитанам и опубликованы в канал.\n\n"
                f"{brackets_text}"
            )
        else:
            await message.edit_message_text(
                f"✅ Сетка турнира сгенерирована!\n\n"
                f"Уведомления отправлены всем капитанам и опубликованы в канал.\n\n"
                f"{brackets_text}"
            )
    
    async def post_to_channel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Публикация информации в канал"""
        query = update.callback_query
        await query.answer()
        
        approved_teams = [team for team in storage.teams.values() if team.status == "approved"]
        
        if not approved_teams:
            await query.edit_message_text("❌ Нет одобренных команд для публикации!")
            return
        
        # Формируем текст для канала
        channel_text = "🏆 ТУРНИР - УЧАСТНИКИ\n\n"
        channel_text += f"Всего команд: {len(approved_teams)}\n\n"
        
        for i, team in enumerate(approved_teams, 1):
            confirmed_players = len([p for p in team.players if p.contact_confirmed])
            
            channel_text += (
                f"{i}. {team.name}\n"
                f"   Устройство: {team.device_type}\n"
                f"   Игроков: {confirmed_players}/{len(team.players)}\n"
                f"   Капитан: {team.captain_username}\n\n"
            )
        
        # Отправляем в канал
        try:
            await context.bot.send_message(
                chat_id=NOTIFICATION_CHANNEL_ID,
                text=channel_text
            )
            await query.edit_message_text(
                f"✅ Информация опубликована в канал!\n\n"
                f"{channel_text}"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки в канал: {e}")
            await query.edit_message_text("❌ Ошибка публикации в канал!")
    
    async def admin_stats_detailed(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Подробная статистика"""
        query = update.callback_query
        await query.answer()
        
        approved_teams = [t for t in storage.teams.values() if t.status == "approved"]
        pending_teams = [t for t in storage.teams.values() if t.status == "pending"]
        
        # Статистика по устройствам
        pc_count = len([t for t in approved_teams if t.device_type == "PC"])
        mobile_count = len([t for t in approved_teams if t.device_type == "MOBILE"])
        
        # Статистика по подтвержденным игрокам
        total_players = sum(len(t.players) for t in storage.teams.values())
        confirmed_players = sum(
            len([p for p in t.players if p.contact_confirmed]) 
            for t in storage.teams.values()
        )
        
        text = (
            "📊 ПОДРОБНАЯ СТАТИСТИКА\n\n"
            f"📈 Команды:\n"
            f"• Всего: {len(storage.teams)}\n"
            f"• Одобрено: {len(approved_teams)}\n"
            f"• На рассмотрении: {len(pending_teams)}\n"
            f"• Свободно мест: {storage.config['max_teams'] - len(approved_teams)}\n\n"
            f"👥 Игроки:\n"
            f"• Всего: {total_players}\n"
            f"• Подтвердили: {confirmed_players}\n"
            f"• Ждут подтверждения: {total_players - confirmed_players}\n\n"
            f"📱 По устройствам (одобренные):\n"
            f"• PC: {pc_count} команд\n"
            f"• MOBILE: {mobile_count} команд\n"
            f"• CC игроков: {sum(len([p for p in t.players if p.cc_ms == 'CC']) for t in approved_teams)}\n"
            f"• MS игроков: {sum(len([p for p in t.players if p.cc_ms == 'MS']) for t in approved_teams)}"
        )
        
        await query.edit_message_text(text)
    
    async def admin_back(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Возврат в главное меню админа"""
        query = update.callback_query
        await query.answer()
        
        await self.admin_panel(Update(
            update_id=update.update_id,
            message=query.message
        ), context)
    
    async def list_teams(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Список всех команд"""
        if not storage.teams:
            await update.message.reply_text("📭 Нет зарегистрированных команд.")
            return
        
        text = "🏆 СПИСОК КОМАНД\n\n"
        
        for team_name, team in storage.teams.items():
            status_emoji = {
                "pending": "⏳",
                "approved": "✅",
                "rejected": "❌"
            }.get(team.status, "❓")
            
            confirmed_players = len([p for p in team.players if p.contact_confirmed])
            
            text += (
                f"{status_emoji} {team_name}\n"
                f"   📱 Устройство: {team.device_type}\n"
                f"   👥 Игроков: {confirmed_players}/{len(team.players)}\n"
                f"   👑 Капитан: {team.captain_username}\n"
                f"   📅 Дата: {team.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
            )
        
        await update.message.reply_text(text)
    
    async def admin_approve_reject(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Одобрение/отклонение заявки админами"""
        query = update.callback_query
        await query.answer()
        
        parts = query.data.split("_", 1)
        if len(parts) < 2:
            return
        
        action, team_name = parts[0], parts[1]
        
        if team_name not in storage.teams:
            await query.edit_message_text("❌ Команда не найдена!")
            return
        
        team = storage.teams[team_name]
        
        if action == "approve":
            team.status = "approved"
            status_text = "✅ ОДОБРЕНО"
            
            # Уведомляем капитана
            try:
                await context.bot.send_message(
                    chat_id=team.captain_id,
                    text=f"🎉 Ваша команда '{team.name}' одобрена для участия в турнире!"
                )
                
                # Уведомляем подтвержденных игроков
                for player in team.players:
                    if player.telegram_id and player.contact_confirmed and player.telegram_id != team.captain_id:
                        try:
                            await context.bot.send_message(
                                chat_id=player.telegram_id,
                                text=f"🎉 Команда '{team.name}' одобрена для участия в турнире!"
                            )
                        except:
                            pass
                            
            except Exception as e:
                logger.error(f"Ошибка уведомления капитана: {e}")
                
        elif action == "reject":
            team.status = "rejected"
            status_text = "❌ ОТКЛОНЕНО"
            
            # Уведомляем капитана
            try:
                await context.bot.send_message(
                    chat_id=team.captain_id,
                    text=f"❌ Ваша команда '{team.name}' отклонена для участия в турнире."
                )
            except Exception as e:
                logger.error(f"Ошибка уведомления капитана: {e}")
        
        # Обновляем сообщение в админской группе
        original_text = query.message.caption
        new_text = f"{original_text}\n\n{status_text}"
        
        await query.edit_message_caption(
            caption=new_text,
            reply_markup=None
        )
        
        self.save_data()
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена регистрации"""
        user_id = update.effective_user.id
        
        if user_id in storage.registrations:
            del storage.registrations[user_id]
        
        await update.message.reply_text(
            "❌ Регистрация отменена.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    def setup_handlers(self, application):
        """Настройка всех обработчиков"""
        
        # Основной ConversationHandler для регистрации
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start)],
            states={
                States.DEVICE_TYPE.value: [
                    CallbackQueryHandler(self.choose_device, pattern="^device_")
                ],
                States.TEAM_NAME.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_team_name)
                ],
                States.TEAM_PHOTO.value: [
                    MessageHandler(filters.PHOTO, self.get_team_photo)
                ],
                States.PLAYERS.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_players_count)
                ],
                States.PLAYER_USERNAMES.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.get_player_usernames)
                ],
                States.CONFIRM_REGISTRATION.value: [
                    CallbackQueryHandler(self.confirm_registration, pattern="^(confirm|edit|cancel)_registration")
                ]
            },
            fallbacks=[CommandHandler('cancel', self.cancel)],
        )
        
        # ConversationHandler для админских настроек
        admin_conv_handler = ConversationHandler(
            entry_points=[
                CallbackQueryHandler(self.admin_add_admin, pattern="^admin_add$"),
                CallbackQueryHandler(self.admin_change_setting, pattern="^setting_(max_teams|players_per_team)$")
            ],
            states={
                States.ADMIN_ADD_ADMIN.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_add_admin)
                ],
                States.ADMIN_TEAM_LIMIT.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_team_limit)
                ],
                States.ADMIN_PLAYER_LIMIT.value: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.process_player_limit)
                ]
            },
            fallbacks=[CommandHandler('cancel', lambda u, c: ConversationHandler.END)]
        )
        
        # Основные команды
        application.add_handler(CommandHandler('admin', self.admin_panel))
        application.add_handler(CommandHandler('teams', self.list_teams))
        application.add_handler(CommandHandler('generate', self.generate_brackets))
        
        # Обработчики колбэков
        application.add_handler(CallbackQueryHandler(
            self.admin_settings_menu, pattern="^admin_settings$"
        ))
        application.add_handler(CallbackQueryHandler(
            self.admin_manage_admins, pattern="^admin_manage$"
        ))
        application.add_handler(CallbackQueryHandler(
            self.admin_stats_detailed, pattern="^admin_stats$"
        ))
        application.add_handler(CallbackQueryHandler(
            self.admin_change_setting, pattern="^setting_(open_reg|close_reg|generate_brackets|post_channel)$"
        ))
        application.add_handler(CallbackQueryHandler(
            self.admin_back, pattern="^admin_back$"
        ))
        application.add_handler(CallbackQueryHandler(
            self.player_confirmation, pattern="^player_(confirm|decline)_"
        ))
        
        # Добавляем ConversationHandlers
        application.add_handler(conv_handler)
        application.add_handler(admin_conv_handler)
        
        # Обработчик одобрения/отклонения команд (для админской группы)
        application.add_handler(CallbackQueryHandler(
            self.admin_approve_reject, pattern="^(approve|reject)_"
        ))
        
        # Обработчик информации о команде
        application.add_handler(CallbackQueryHandler(
            self.team_info, pattern="^info_"
        ))
    
    async def team_info(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Информация о команде"""
        query = update.callback_query
        await query.answer()
        
        team_name = query.data.replace("info_", "")
        
        if team_name not in storage.teams:
            await query.edit_message_text("❌ Команда не найдена!")
            return
        
        team = storage.teams[team_name]
        
        players_info = ""
        for i, player in enumerate(team.players, 1):
            status = "✅ Подтвержден" if player.contact_confirmed else "⚠️ Ожидает"
            device_info = f"{player.device_type}"
            if player.device_type == "MOBILE" and player.cc_ms:
                device_info = f"{player.device_type} ({player.cc_ms})"
            
            players_info += (
                f"{i}. {player.username}\n"
                f"   Устройство: {device_info}\n"
                f"   Статус: {status}\n"
                f"   ID: {player.telegram_id or 'Не привязан'}\n\n"
            )
        
        info_text = (
            f"📋 ИНФОРМАЦИЯ О КОМАНДЕ\n\n"
            f"🏆 Название: {team.name}\n"
            f"📱 Устройство: {team.device_type}\n"
            f"👑 Капитан: {team.captain_username}\n"
            f"📅 Дата регистрации: {team.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"📊 Статус: {team.status}\n\n"
            f"👥 Состав команды:\n{players_info}"
        )
        
        await query.message.reply_text(info_text)
    
    def run(self):
        """Запуск бота"""
        application = Application.builder().token(self.token).build()
        
        self.setup_handlers(application)
        
        print(f"Бот запущен...")
        print(f"Владелец: {OWNER_ID}")
        print(f"Админ группа: {ADMIN_GROUP_ID}")
        print(f"Канал: {NOTIFICATION_CHANNEL_ID}")
        
        application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    bot = TournamentBot(TOKEN)
    bot.run()
