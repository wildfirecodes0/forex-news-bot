from curl_cffi import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import pytz

def clean_title(title: str) -> str:
    return re.sub(r'(?i)\s*(q/q|y/y|m/m|q[1-4]|m[1-9]).*$', '', title).strip()

def fetch_forex_events():
    # ForexFactory provides only current week data in this reliable XML format
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    
    events =[]
    eastern = pytz.timezone('US/Eastern')
    ist = pytz.timezone('Asia/Kolkata')
    
    impact_map = {"High": "High", "Medium": "Medium", "Low": "Low", "Non": "None", "Holiday": "None"}
    
    try:
        response = requests.get(url, impersonate="chrome", timeout=15)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'xml')
            
            for event in soup.find_all('event'):
                title = event.title.text.strip() if event.title and event.title.text else "Unknown"
                currency = event.country.text.strip().upper() if event.country and event.country.text else "UNK"
                date_str = event.date.text.strip() if event.date and event.date.text else ""
                time_str = event.time.text.strip().upper() if event.time and event.time.text else ""
                impact_raw = event.impact.text.strip() if event.impact and event.impact.text else "Non"
                
                if time_str in["ALL DAY", "TENTATIVE", ""]: continue
                
                impact = impact_map.get(impact_raw, "None")
                dt_str = f"{date_str} {time_str}"
                
                try:
                    dt_est = eastern.localize(datetime.strptime(dt_str, "%m-%d-%Y %I:%M%p"))
                    dt_ist = dt_est.astimezone(ist)
                except ValueError:
                    continue
                    
                clean_name = clean_title(title)
                events.append({
                    "id": f"{currency}_{int(dt_ist.timestamp())}_{clean_name[:5]}",
                    "title": clean_name,
                    "currency": currency,
                    "impact": impact,
                    "time_ist": dt_ist
                })
    except Exception as e:
        print(f"Scrape Error: {e}")
            
    unique_events = {e["id"]: e for e in events}
    return sorted(list(unique_events.values()), key=lambda x: x["time_ist"])
