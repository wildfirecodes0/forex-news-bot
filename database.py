import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

DEFAULT_SETTINGS = {
    "impact": {"High": True, "Medium": True, "Low": False, "None": False},
    "currencies": {"USD": True, "EUR": True, "GBP": True, "JPY": False, "AUD": False, "CAD": False, "CHF": False, "NZD": False, "CNY": False},
    "event_types": {"Growth": True, "Inflation": True, "Employment": True, "Central Bank": True, "Bonds": False, "Housing": False, "Consumer Surveys": False, "Business Surveys": False, "Speeches": True, "Misc": True}
}

def get_user_with_status(user_id: int) -> tuple[dict, bool]:
    response = supabase.table("users").select("*").eq("user_id", user_id).execute()
    if response.data:
        return response.data[0], False
    else:
        new_user = {"user_id": user_id, **DEFAULT_SETTINGS}
        supabase.table("users").insert(new_user).execute()
        return new_user, True

def get_user(user_id: int) -> dict:
    return get_user_with_status(user_id)[0]

def update_user_filter(user_id: int, category: str, item: str, current_val: bool):
    user = get_user(user_id)
    user[category][item] = not current_val
    supabase.table("users").update({category: user[category]}).eq("user_id", user_id).execute()

def get_all_users() -> list:
    return supabase.table("users").select("*").execute().data

def get_users_count() -> int:
    response = supabase.table("users").select("user_id", count="exact").execute()
    return response.count
