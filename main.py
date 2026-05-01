import os
import asyncio
from datetime import datetime, timedelta
import pytz
from aiogram import Bot, Dispatcher, F, Router, BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web
from dotenv import load_dotenv

from database import get_user, update_user_filter, get_all_users, get_user_with_status
from scraper import fetch_forex_events
from keyboards import (main_inline_menu, settings_keyboard, pagination_keyboard, 
                       MainMenuCB, SettingsCB, PaginationCB, force_join_keyboard)
from admin import admin_router

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME") 
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
router = Router()

EVENTS_CACHE =[]
ALERTED_EVENTS = set()

async def health_check(request):
    return web.Response(text="Bot is running smoothly!", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Health check server running on port {port}")

class ForceJoinMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        user = data.get("event_from_user")
        if not user: return await handler(event, data)
        try:
            member = await bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user.id)
            if member.status in['left', 'kicked', 'restricted']:
                msg = "🛑 <b>Action Required!</b>\n\nYou must join our official channel to use Algo Forex News Bot."
                if isinstance(event, Message):
                    await event.answer(msg, reply_markup=force_join_keyboard())
                elif isinstance(event, CallbackQuery) and event.data != "check_sub":
                    await event.message.answer(msg, reply_markup=force_join_keyboard())
                    await event.answer()
                return 
        except Exception:
            pass
        return await handler(event, data)

dp.message.middleware(ForceJoinMiddleware())
dp.callback_query.middleware(ForceJoinMiddleware())

def format_event_msg(event: dict, now: datetime) -> str:
    emojis = {"High": "🔴", "Medium": "🟠", "Low": "🟡", "None": "⚪"}
    emj = emojis.get(event["impact"], "⚪")
    status = "✅ <i>Passed</i>" if event["time_ist"] < now else "⏳ <i>Upcoming</i>"
    
    return (
        f"📌 <b>{event['title']}</b>\n"
        f"💱 <b>Currency:</b> <code>{event['currency']}</code> | 💥 <b>Impact:</b> {emj} <code>{event['impact']}</code>\n"
        f"🕒 <b>Time:</b> <code>{event['time_ist'].strftime('%d %b, %I:%M %p')}</code> | {status}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )

def get_paginated_events(user_id: int, period: str, page: int = 0):
    user = get_user(user_id)
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)

    filtered =[]
    for e in EVENTS_CACHE:
        if not user["impact"].get(e["impact"], False): continue
        if not user["currencies"].get(e["currency"], False): continue
        
        event_date = e["time_ist"].date()
        if period == "today":
            if event_date != now.date(): continue
        elif period == "week":
            if event_date < now.date() or event_date > (now.date() + timedelta(days=7)): continue
        elif period == "month":
            if event_date < now.date() or event_date > (now.date() + timedelta(days=30)): continue

        filtered.append(e)

    items_per_page = 5
    total_pages = max(1, (len(filtered) + items_per_page - 1) // items_per_page)
    chunk = filtered[page * items_per_page : (page + 1) * items_per_page]
    
    return chunk, total_pages, len(filtered), now

@router.message(CommandStart())
async def cmd_start(message: Message):
    user, is_new = get_user_with_status(message.from_user.id)
    
    if is_new and ADMIN_ID != 0:
        try:
            await bot.send_message(
                ADMIN_ID, 
                f"🚨 <b>New User Joined</b>\n\n👤 Name: {message.from_user.full_name}\n🔗 Username: @{message.from_user.username}\n🆔 ID: <code>{message.from_user.id}</code>"
            )
        except Exception:
            pass

    msg = (
        "📊 <b>Algo Forex News Bot</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "<i>Your elite AI assistant for high-impact Forex events.</i>\n\n"
        "✨ <b>Features:</b>\n"
        "• ⏱ Auto-converts to IST (GMT+5:30).\n"
        "• 🎯 Custom filters for Currencies & Impact.\n"
        "• 🔔 Exact 30-minute advance notifications.\n\n"
        "👇 <b>Select an option to manage your feed:</b>"
    )
    await message.answer(msg, reply_markup=main_inline_menu())

@router.callback_query(F.data == "check_sub")
async def check_subscription(callback: CallbackQuery):
    await callback.message.delete()
    await callback.message.answer("Thank you for joining! You can now use the bot.", reply_markup=main_inline_menu())

@router.callback_query(MainMenuCB.filter())
async def handle_main_menu(callback: CallbackQuery, callback_data: MainMenuCB):
    if callback_data.action == "settings":
        await callback.message.edit_text(
            "🎛 <b>Filter Settings</b>\nToggle what news you want to receive:", 
            reply_markup=settings_keyboard(callback.from_user.id)
        )
    elif callback_data.action == "back_main":
        await callback.message.edit_text(
            "📊 <b>Algo Forex News Bot</b>\n👇 Select an option to manage your feed:", 
            reply_markup=main_inline_menu()
        )
    else:
        chunk, total_pages, total_items, now = get_paginated_events(callback.from_user.id, callback_data.action, 0)
        
        if total_items == 0:
            await callback.answer("📭 No events match your filters for this period.", show_alert=True)
            return
            
        text = f"📰 <b>Events ({callback_data.action.capitalize()})</b> - Page 1/{total_pages}\n\n"
        text += "\n".join([format_event_msg(e, now) for e in chunk])
        
        await callback.message.edit_text(text, reply_markup=pagination_keyboard(0, total_pages, callback_data.action))

@router.callback_query(PaginationCB.filter())
async def handle_pagination(callback: CallbackQuery, callback_data: PaginationCB):
    if callback_data.action == "close":
        await callback.message.delete()
        return

    chunk, total_pages, _, now = get_paginated_events(callback.from_user.id, callback_data.period, callback_data.page)
    text = f"📰 <b>Events ({callback_data.period.capitalize()})</b> - Page {callback_data.page + 1}/{total_pages}\n\n"
    text += "\n".join([format_event_msg(e, now) for e in chunk])
    
    await callback.message.edit_text(text, reply_markup=pagination_keyboard(callback_data.page, total_pages, callback_data.period))

@router.callback_query(SettingsCB.filter())
async def toggle_setting(callback: CallbackQuery, callback_data: SettingsCB):
    user = get_user(callback.from_user.id)
    current_val = user[callback_data.category].get(callback_data.item, False)
    update_user_filter(callback.from_user.id, callback_data.category, callback_data.item, current_val)
    await callback.message.edit_reply_markup(reply_markup=settings_keyboard(callback.from_user.id))

@admin_router.callback_query(F.data == "admin_scrape")
async def force_scrape(callback: CallbackQuery):
    await callback.answer("Scraping in background...")
    global EVENTS_CACHE
    EVENTS_CACHE = fetch_forex_events()
    await callback.message.answer(f"✅ Scraper refreshed. Buffer holds {len(EVENTS_CACHE)} events.")

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
            msg_text = f"⚠️ <b>ALGO ALERT: 30 MINS TO NEWS</b> ⚠️\n\n{format_event_msg(event, now)}"
            
            for u in users:
                if u["impact"].get(event["impact"], False) and u["currencies"].get(event["currency"], False):
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
    
    await start_web_server()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
