from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData
from database import get_user

class SettingsCB(CallbackData, prefix="set"):
    category: str
    item: str

def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📅 Today"), KeyboardButton(text="🗓 This Week")],
            [KeyboardButton(text="⚙️ Settings")]
        ],
        resize_keyboard=True
    )

def settings_keyboard(user_id: int):
    user = get_user(user_id)
    builder = InlineKeyboardBuilder()
    
    # Impact Mapping
    impacts = {"High": "🔴 High", "Medium": "🟠 Med", "Low": "🟡 Low", "None": "⚪ None"}
    for key, label in impacts.items():
        val = user["impact"].get(key, False)
        icon = "✅" if val else "❌"
        builder.button(text=f"{icon} {label}", callback_data=SettingsCB(category="impact", item=key))
        
    # Currencies
    for curr, val in user["currencies"].items():
        icon = "✅" if val else "❌"
        builder.button(text=f"{icon} {curr}", callback_data=SettingsCB(category="currencies", item=curr))
        
    # Event Types
    for etype, val in user["event_types"].items():
        icon = "✅" if val else "❌"
        builder.button(text=f"{icon} {etype}", callback_data=SettingsCB(category="event_types", item=etype))
        
    # Adjusting row sizes for beautiful UI: (Impact: 4) (Currencies: 3x3) (Events: 2x5)
    builder.adjust(4, 3, 3, 3, 2, 2, 2, 2, 2)
    return builder.as_markup()
