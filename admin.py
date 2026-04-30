from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database import get_users_count, get_all_users
import os

admin_router = Router()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()

def admin_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="📢 Broadcast", callback_data="admin_broadcast")
    builder.button(text="📊 Total Users", callback_data="admin_stats")
    builder.button(text="🔄 Force Scrape", callback_data="admin_scrape")
    builder.adjust(1)
    return builder.as_markup()

@admin_router.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: Message):
    await message.answer("🛠 <b>Admin Panel</b>", reply_markup=admin_keyboard())

@admin_router.callback_query(F.data == "admin_stats", F.from_user.id == ADMIN_ID)
async def show_stats(callback: CallbackQuery):
    users = get_users_count()
    await callback.message.edit_text(f"📊 <b>Total Users:</b> {users}", reply_markup=admin_keyboard())

@admin_router.callback_query(F.data == "admin_broadcast", F.from_user.id == ADMIN_ID)
async def broadcast_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Enter the message you want to broadcast (HTML supported):")
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.answer()

@admin_router.message(AdminStates.waiting_for_broadcast, F.from_user.id == ADMIN_ID)
async def broadcast_send(message: Message, state: FSMContext, bot: Bot):
    users = get_all_users()
    sent = 0
    await message.answer("Broadcast started...")
    for u in users:
        try:
            await bot.send_message(u["user_id"], message.html_text)
            sent += 1
        except Exception:
            pass
    await message.answer(f"✅ Broadcast finished. Sent to {sent} users.")
    await state.clear()
