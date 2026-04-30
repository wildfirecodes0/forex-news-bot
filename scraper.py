import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta
import pytz

def clean_title(title: str) -> str:
    """Removes standard suffixes like q/q, y/y, m/m from titles."""
    return re.sub(r'(?i)\s*(q/q|y/y|m/m|q1|q2|q3|q4).*$', '', title).strip()

def get_event_type(title: str) -> str:
    t = title.lower()
    if any(x in t for x in["gdp", "pmi", "production", "growth", "manufacturing", "services", "trade"]): return "Growth"
    if any(x in t for x in ["cpi", "ppi", "pce", "inflation", "price", "wage"]): return "Inflation"
    if any(x in t for x in["employment", "unemployment", "jobless", "payrolls", "nfp", "jolt", "claims"]): return "Employment"
    if any(x in t for x in["rate", "central bank", "fed", "ecb", "boe", "boj", "rba", "statement", "minutes"]): return "Central Bank"
    if any(x in t for x in["bond", "auction", "note", "bill"]): return "Bonds"
    if any(x in t for x in["housing", "home", "building", "mortgage"]): return "Housing"
    if any(x in t for x in ["consumer", "sentiment", "confidence", "michigan"]): return "Consumer Surveys"
    if any(x in t for x in ["business", "tankan", "ifo", "zew"]): return "Business Surveys"
    if any(x in t for x in ["speaks", "speech", "testifies"]): return "Speeches"
    return "Misc"

def fetch_forex_events():
    """Scrapes fair economy XML feed using BeautifulSoup4 to bypass strict Cloudflare checks."""
    urls =[
        "https://nfs.faireconomy.media/ff_calendar_thisweek.xml",
        "https://nfs.faireconomy.media/ff_calendar_nextweek.xml" # To simulate up to a month of available data
    ]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    events =[]
    eastern = pytz.timezone('US/Eastern')
    ist = pytz.timezone('Asia/Kolkata')
    impact_map = {"High": "High", "Medium": "Medium", "Low": "Low", "Non": "None"}
    
    for url in urls:
        try:
            response = requests.get(url, headers=headers, timeout=15)
            if response.status_code != 200: continue
            
            # BeautifulSoup 4 implementation
            soup = BeautifulSoup(response.content, 'xml')
            
            for event in soup.find_all('event'):
                title = event.title.text if event.title else "Unknown"
                currency = event.country.text if event.country else "UNK"
                date_str = event.date.text if event.date else ""
                time_str = event.time.text if event.time else ""
                impact_raw = event.impact.text if event.impact else "Non"
                
                if time_str in["All Day", "Tentative", ""]: continue
                
                impact = impact_map.get(impact_raw, "None")
                dt_str = f"{date_str} {time_str}"
                
                try:
                    dt_est = eastern.localize(datetime.strptime(dt_str, "%m-%d-%Y %I:%Mam"))
                    dt_ist = dt_est.astimezone(ist)
                except ValueError:
                    continue
                    
                clean_name = clean_title(title)
                
                events.append({
                    "id": f"{currency}_{int(dt_ist.timestamp())}_{clean_name[:5]}",
                    "title": clean_name,
                    "currency": currency,
                    "impact": impact,
                    "event_type": get_event_type(clean_name),
                    "time_ist": dt_ist
                })
        except Exception as e:
            print(f"BS4 Scrape Error on {url}: {e}")
            
    # Remove duplicates
    unique_events = {e["id"]: e for e in events}
    return sorted(list(unique_events.values()), key=lambda x: x["time_ist"])
