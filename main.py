import os
import asyncio
from datetime import datetime
import pytz
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

from database import get_user, update_user_filter, get_all_users
from scraper import fetch_forex_events
from keyboards import main_menu, settings_keyboard, SettingsCB

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
router = Router()

# In-memory cache for events to avoid spamming the API every minute
EVENTS_CACHE =[]
ALERTED_EVENTS = set() # Keeps track of dispatched alerts

IMPACT_EMOJIS = {"High": "🔴", "Medium": "🟠", "Low": "🟡", "None": "⚪"}

def format_event_msg(event: dict) -> str:
    """Formats event data cleanly using Monospace layout."""
    emj = IMPACT_EMOJIS.get(event["impact"], "⚪")
    return (
        f"<b>{event['title']}</b>\n"
        f"<code>-------------------------</code>\n"
        f"💵 <b>Currency:</b> <code>{event['currency']}</code>\n"
        f"📊 <b>Impact:</b>   {emj} <code>{event['impact']}</code>\n"
        f"🏷 <b>Type:</b>     <code>{event['event_type']}</code>\n"
        f"🕒 <b>Time:</b>     <code>{event['time_ist'].strftime('%I:%M %p (IST)')}</code>\n"
        f"<code>-------------------------</code>"
    )

@router.message(CommandStart())
async def cmd_start(message: Message):
    get_user(message.from_user.id)
    await message.answer(
        "👋 <b>Welcome to the Premium Forex Alerts Bot!</b>\n\n"
        "Configure your filters in the <b>⚙️ Settings</b> to receive personalized 30-minute advance notifications.",
        reply_markup=main_menu()
    )

@router.message(F.text == "⚙️ Settings")
async def show_settings(message: Message):
    await message.answer(
        "🎛 <b>Your Personalized Alerts Dashboard</b>\n"
        "<i>Tap a button to toggle (✅ ON / ❌ OFF)</i>",
        reply_markup=settings_keyboard(message.from_user.id)
    )

@router.callback_query(SettingsCB.filter())
async def toggle_setting(callback: CallbackQuery, callback_data: SettingsCB):
    user = get_user(callback.from_user.id)
    current_val = user[callback_data.category].get(callback_data.item, False)
    
    # Update Supabase Database
    update_user_filter(callback.from_user.id, callback_data.category, callback_data.item, current_val)
    
    # Dynamically update the inline keyboard UI
    await callback.message.edit_reply_markup(reply_markup=settings_keyboard(callback.from_user.id))
    await callback.answer(f"Toggled {callback_data.item}")

@router.message(F.text.in_({"📅 Today", "🗓 This Week"}))
async def show_schedule(message: Message):
    user = get_user(message.from_user.id)
    ist = pytz.timezone('Asia/Calcutta')
    now = datetime.now(ist)
    
    filtered =[]
    for e in EVENTS_CACHE:
        # Check User Filters
        if not user["impact"].get(e["impact"], False): continue
        if not user["currencies"].get(e["currency"], False): continue
        if not user["event_types"].get(e["event_type"], False): continue
        if e["time_ist"] < now: continue # Skip past events
        
        if message.text == "📅 Today" and e["time_ist"].date() != now.date(): continue
        
        filtered.append(e)
        
    if not filtered:
        await message.answer("📭 <i>No upcoming events match your active filters.</i>")
        return
        
    response = "\n\n".join([format_event_msg(e) for e in filtered[:5]])
    if len(filtered) > 5:
         response += f"\n\n<i>...and {len(filtered)-5} more.</i>"
         
    title = "📅 <b>Today's Events</b>" if message.text == "📅 Today" else "🗓 <b>This Week's Events</b>"
    await message.answer(f"{title}\n\n{response}")

# --- Background Tasks (APScheduler) ---

def update_events_cache():
    """Scrapes ForexFactory every 15 mins."""
    global EVENTS_CACHE
    EVENTS_CACHE = fetch_forex_events()
    print(f"[{datetime.now()}] Cache updated. Total events: {len(EVENTS_CACHE)}")

async def dispatch_personalized_alerts():
    """Runs every minute to check for events exactly 30 mins away."""
    if not EVENTS_CACHE: return
    
    ist = pytz.timezone('Asia/Calcutta')
    now = datetime.now(ist)
    users = get_all_users()
    
    for event in EVENTS_CACHE:
        if event["id"] in ALERTED_EVENTS:
            continue
            
        time_diff_minutes = (event["time_ist"] - now).total_seconds() / 60.0
        
        # Trigger if the event is 29 to 30 minutes away
        if 29 <= time_diff_minutes <= 30.5:
            ALERTED_EVENTS.add(event["id"])
            msg_text = f"⚠️ <b>UPCOMING EVENT IN 30 MINS</b> ⚠️\n\n{format_event_msg(event)}"
            
            # Find users whose filters match this specific event
            for u in users:
                impact_ok = u["impact"].get(event["impact"], False)
                curr_ok = u["currencies"].get(event["currency"], False)
                type_ok = u["event_types"].get(event["event_type"], False)
                
                if impact_ok and curr_ok and type_ok:
                    try:
                        await bot.send_message(u["user_id"], msg_text)
                    except Exception as e:
                        print(f"Failed to alert {u['user_id']}: {e}")

async def main():
    # Initial Cache population
    update_events_cache()
    
    # Scheduler Setup
    scheduler = AsyncIOScheduler(timezone=pytz.timezone('Asia/Calcutta'))
    
    # Update cache every 15 minutes (Reliable retry mechanism handled inside the cron timing)
    scheduler.add_job(update_events_cache, 'interval', minutes=15)
    
    # Check for dispatches every 1 minute
    scheduler.add_job(dispatch_personalized_alerts, 'interval', minutes=1)
    
    scheduler.start()
    
    # Aiogram startup
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
