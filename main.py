import os
import asyncio
from datetime import datetime, timedelta
import pytz
from aiogram import Bot, Dispatcher, F, Router, BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

from database import get_user, update_user_filter, get_all_users
from scraper import fetch_forex_events
from keyboards import (main_inline_menu, settings_keyboard, pagination_keyboard, 
                       MainMenuCB, SettingsCB, PaginationCB, force_join_keyboard)
from admin import admin_router

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME") # e.g., @YourChannelUsername
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
router = Router()

EVENTS_CACHE =[]
ALERTED_EVENTS = set()

# --- FORCE JOIN MIDDLEWARE ---
class ForceJoinMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        # Allow checking if event is message or callback
        user = data.get("event_from_user")
        if not user: return await handler(event, data)
        
        try:
            member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user.id)
            if member.status in ['left', 'kicked', 'restricted']:
                msg = "🛑 <b>Action Required!</b>\n\nYou must join our official channel to use Algo Forex News Bot."
                if isinstance(event, Message):
                    await event.answer(msg, reply_markup=force_join_keyboard())
                elif isinstance(event, CallbackQuery) and event.data != "check_sub":
                    await event.message.answer(msg, reply_markup=force_join_keyboard())
                    await event.answer()
                return # Stop propagation
        except Exception as e:
            print(f"Middleware Error: {e}")
            
        return await handler(event, data)

dp.message.middleware(ForceJoinMiddleware())
dp.callback_query.middleware(ForceJoinMiddleware())

# --- HELPER FUNCTIONS ---
def format_event_msg(event: dict) -> str:
    emojis = {"High": "🔴", "Medium": "🟠", "Low": "🟡", "None": "⚪"}
    emj = emojis.get(event["impact"], "⚪")
    return (
        f"<b>{event['title']}</b>\n"
        f"💵 <b>Currency:</b> <code>{event['currency']}</code> | 📊 <b>Impact:</b> {emj} <code>{event['impact']}</code>\n"
        f"🕒 <b>Time:</b> <code>{event['time_ist'].strftime('%d %b, %I:%M %p')}</code>\n"
        f"<code>───────────────</code>"
    )

def get_paginated_events(user_id: int, period: str, page: int = 0):
    user = get_user(user_id)
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    
    # Period logic
    end_date = now
    if period == "today": end_date = now.replace(hour=23, minute=59)
    elif period == "week": end_date = now + timedelta(days=7)
    elif period == "month": end_date = now + timedelta(days=30)

    filtered =[]
    for e in EVENTS_CACHE:
        if not user["impact"].get(e["impact"], False): continue
        if not user["currencies"].get(e["currency"], False): continue
        if not user["event_types"].get(e["event_type"], False): continue
        
        if e["time_ist"] < now: continue
        if e["time_ist"] > end_date: continue
        filtered.append(e)

    # Chunk into pages of 5
    items_per_page = 5
    total_pages = max(1, (len(filtered) + items_per_page - 1) // items_per_page)
    chunk = filtered[page * items_per_page : (page + 1) * items_per_page]
    
    return chunk, total_pages, len(filtered)

# --- HANDLERS ---
@router.message(CommandStart())
async def cmd_start(message: Message):
    get_user(message.from_user.id)
    await message.answer(
        "🤖 <b>Algo Forex News Bot</b>\n\n"
        "Your premium assistant for tracking Forex Markets. Select an option below:",
        reply_markup=main_inline_menu()
    )

@router.callback_query(F.data == "check_sub")
async def check_subscription(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("Thank you for joining! You can now use the bot.", reply_markup=main_inline_menu())

@router.callback_query(MainMenuCB.filter())
async def handle_main_menu(callback: CallbackQuery, callback_data: MainMenuCB):
    if callback_data.action == "settings":
        await callback.message.edit_text("🎛 <b>Filter Settings</b>\nToggle what news you want to receive:", reply_markup=settings_keyboard(callback.from_user.id))
    elif callback_data.action == "back_main":
        await callback.message.edit_text("🤖 <b>Algo Forex News Bot</b>\nSelect an option below:", reply_markup=main_inline_menu())
    else:
        # Handling today, week, month
        chunk, total_pages, total_items = get_paginated_events(callback.from_user.id, callback_data.action, 0)
        
        if total_items == 0:
            await callback.answer("No events match your filters.", show_alert=True)
            return
            
        text = f"📰 <b>Events ({callback_data.action.capitalize()})</b> - Page 1/{total_pages}\n\n"
        text += "\n".join([format_event_msg(e) for e in chunk])
        
        await callback.message.edit_text(text, reply_markup=pagination_keyboard(0, total_pages, callback_data.action))

@router.callback_query(PaginationCB.filter())
async def handle_pagination(callback: CallbackQuery, callback_data: PaginationCB):
    if callback_data.action == "close":
        await callback.message.delete()
        return

    chunk, total_pages, _ = get_paginated_events(callback.from_user.id, callback_data.period, callback_data.page)
    text = f"📰 <b>Events ({callback_data.period.capitalize()})</b> - Page {callback_data.page + 1}/{total_pages}\n\n"
    text += "\n".join([format_event_msg(e) for e in chunk])
    
    await callback.message.edit_text(text, reply_markup=pagination_keyboard(callback_data.page, total_pages, callback_data.period))

@router.callback_query(SettingsCB.filter())
async def toggle_setting(callback: CallbackQuery, callback_data: SettingsCB):
    user = get_user(callback.from_user.id)
    current_val = user[callback_data.category].get(callback_data.item, False)
    update_user_filter(callback.from_user.id, callback_data.category, callback_data.item, current_val)
    await callback.message.edit_reply_markup(reply_markup=settings_keyboard(callback.from_user.id))

# --- ADMIN SCRAPE OVERRIDE ---
@admin_router.callback_query(F.data == "admin_scrape")
async def force_scrape(callback: CallbackQuery):
    await callback.answer("Scraping in background...")
    global EVENTS_CACHE
    EVENTS_CACHE = fetch_forex_events()
    await callback.message.answer(f"✅ Scraper refreshed. Buffer holds {len(EVENTS_CACHE)} events.")

# --- BACKGROUND TASKS ---
def update_events_cache():
    global EVENTS_CACHE
    EVENTS_CACHE = fetch_forex_events()

async def dispatch_personalized_alerts():
    if not EVENTS_CACHE: return
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    users = get_all_users()
    
    for event in EVENTS_CACHE:
        if event["id"] in ALERTED_EVENTS: continue
        time_diff = (event["time_ist"] - now).total_seconds() / 60.0
        
        if 29.5 <= time_diff <= 30.5:
            ALERTED_EVENTS.add(event["id"])
            msg_text = f"⚠️ <b>ALGO ALERT: 30 MINS TO NEWS</b> ⚠️\n\n{format_event_msg(event)}"
            
            for u in users:
                if u["impact"].get(event["impact"], False) and u["currencies"].get(event["currency"], False) and u["event_types"].get(event["event_type"], False):
                    try:
                        await bot.send_message(u["user_id"], msg_text)
                    except Exception:
                        pass

async def main():
    update_events_cache()
    scheduler = AsyncIOScheduler(timezone=pytz.timezone('Asia/Kolkata'))
    scheduler.add_job(update_events_cache, 'interval', minutes=15)
    scheduler.add_job(dispatch_personalized_alerts, 'interval', minutes=1)
    scheduler.start()
    
    dp.include_router(admin_router)
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
