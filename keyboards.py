from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData
from database import get_user
import os

CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/algoraushan")

class MainMenuCB(CallbackData, prefix="menu"):
    action: str

class SettingsCB(CallbackData, prefix="set"):
    category: str
    item: str

class PaginationCB(CallbackData, prefix="pg"):
    action: str
    page: int
    period: str

def force_join_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="📢 Join Channel", url=CHANNEL_URL)
    builder.button(text="🔄 Check Subscription", callback_data="check_sub")
    builder.adjust(1)
    return builder.as_markup()

def main_inline_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Today", callback_data=MainMenuCB(action="today"))
    builder.button(text="🗓 This Week", callback_data=MainMenuCB(action="week"))
    builder.button(text="⚙️ Settings", callback_data=MainMenuCB(action="settings"))
    builder.adjust(2, 1) # Clean 2-1 layout
    return builder.as_markup()

def settings_keyboard(user_id: int):
    user = get_user(user_id)
    builder = InlineKeyboardBuilder()
    
    impacts = {"High": "🔴 High", "Medium": "🟠 Med", "Low": "🟡 Low", "None": "⚪ None"}
    for key, label in impacts.items():
        icon = "✅" if user["impact"].get(key, False) else "❌"
        builder.button(text=f"{icon} {label}", callback_data=SettingsCB(category="impact", item=key))
        
    for curr in user["currencies"].keys():
        icon = "✅" if user["currencies"].get(curr, False) else "❌"
        builder.button(text=f"{icon} {curr}", callback_data=SettingsCB(category="currencies", item=curr))
        
    builder.button(text="🔙 Back to Menu", callback_data=MainMenuCB(action="back_main"))
    builder.adjust(4, 3, 3, 3, 1)
    return builder.as_markup()

def pagination_keyboard(current_page: int, total_pages: int, period: str):
    builder = InlineKeyboardBuilder()
    
    # Navigation Row (Prev & Next)
    nav_count = 0
    if current_page > 0:
        builder.button(text="⬅️ Prev", callback_data=PaginationCB(action="prev", page=current_page-1, period=period))
        nav_count += 1
    
    if current_page < total_pages - 1:
        builder.button(text="Next ➡️", callback_data=PaginationCB(action="next", page=current_page+1, period=period))
        nav_count += 1
        
    # Actions Row (Back & Close)
    builder.button(text="🔙 Back", callback_data=MainMenuCB(action="back_main"))
    builder.button(text="❌ Close", callback_data=PaginationCB(action="close", page=0, period=""))
    
    # Adjust alignment based on buttons available
    if nav_count == 0:
        builder.adjust(2) # Only Back and Close side-by-side
    elif nav_count == 1:
        builder.adjust(1, 2)
    else:
        builder.adjust(2, 2)
        
    return builder.as_markup()
