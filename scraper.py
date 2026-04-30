import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import pytz

def get_event_type(title: str) -> str:
    """Categorize the event based on its title."""
    t = title.lower()
    if any(x in t for x in["gdp", "pmi", "production", "growth", "manufacturing", "services", "trade"]):
        return "Growth"
    if any(x in t for x in ["cpi", "ppi", "pce", "inflation", "price", "wage"]):
        return "Inflation"
    if any(x in t for x in["employment", "unemployment", "jobless", "payrolls", "nfp", "jolt", "claims"]):
        return "Employment"
    if any(x in t for x in["rate", "central bank", "fed", "ecb", "boe", "boj", "rba", "statement", "minutes"]):
        return "Central Bank"
    if any(x in t for x in ["bond", "auction", "note", "bill"]):
        return "Bonds"
    if any(x in t for x in ["housing", "home", "building", "mortgage"]):
        return "Housing"
    if any(x in t for x in["consumer", "sentiment", "confidence", "michigan"]):
        return "Consumer Surveys"
    if any(x in t for x in["business", "tankan", "ifo", "zew"]):
        return "Business Surveys"
    if any(x in t for x in ["speaks", "speech", "powell", "lagarde", "bailey", "testifies"]):
        return "Speeches"
    return "Misc"

def fetch_forex_events():
    """Scrape and parse ForexFactory XML, converting times to IST."""
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except Exception as e:
        print(f"Scraper Error: {e}")
        return[]

    root = ET.fromstring(response.content)
    events =[]
    
    eastern = pytz.timezone('US/Eastern')
    ist = pytz.timezone('Asia/Calcutta')
    
    # Standardize Impact Names
    impact_map = {"High": "High", "Medium": "Medium", "Low": "Low", "Non": "None"}
    
    for event in root.findall('event'):
        title = event.find('title').text or "Unknown"
        currency = event.find('country').text or "UNK"
        date_str = event.find('date').text or ""
        time_str = event.find('time').text or ""
        impact_raw = event.find('impact').text or "Non"
        
        impact = impact_map.get(impact_raw, "None")
        
        # Skip events without exact timings
        if time_str in ["All Day", "Tentative", ""]:
            continue
            
        dt_str = f"{date_str} {time_str}"
        try:
            dt_est = eastern.localize(datetime.strptime(dt_str, "%m-%d-%Y %I:%Mam"))
            dt_ist = dt_est.astimezone(ist)
        except ValueError:
            continue
            
        events.append({
            "id": f"{currency}_{dt_ist.timestamp()}_{title[:5]}",
            "title": title,
            "currency": currency,
            "impact": impact,
            "event_type": get_event_type(title),
            "time_ist": dt_ist
        })
        
    return sorted(events, key=lambda x: x["time_ist"])
