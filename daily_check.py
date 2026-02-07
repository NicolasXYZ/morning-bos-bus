import smtplib
import os
import requests
from email.mime.text import MIMEText
from datetime import datetime
from groq import Groq
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
# MBTA (Red Line = "Red", Bus 1 = "1")
MBTA_API_URL = "https://api-v3.mbta.com/alerts?filter[route]=Red,1&filter[activity]=BOARD,RIDE,PARK"

# M2 Shuttle (Longwood Collective Advisories)
M2_URL = "https://www.longwoodcollective.org/advisories"

def get_m2_summary(text_data):
    """
    Asks Groq to analyze the shuttle advisory text.
    """
    try:
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        
        prompt = f"""
        You are a transit assistant for a Harvard student.
        Check the following text from the "Longwood Collective" advisories page.
        Look specifically for news about the "M2 Shuttle" or "Harvard Shuttle".
        
        RULES:
        1. If there are delays, snow routes, or holiday schedule changes for M2, summarize them clearly.
        2. If the text mentions other shuttles (Fenway, Landmark) but NOT M2, ignore them.
        3. If there is no relevant M2 news, reply exactly: "✅ Service Normal"
        
        DATA:
        {text_data}
        """

        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
        )
        return chat.choices[0].message.content
    except Exception as e:
        return f"⚠️ Error asking AI about M2: {e}"

def check_mbta_split():
    """
    Checks MBTA and separates Red Line vs Bus 1 updates.
    Returns two strings: (red_status, bus_status)
    """
    print("Checking MBTA...")
    try:
        response = requests.get(MBTA_API_URL)
        alerts = response.json().get('data', [])
        
        red_alerts = []
        bus_alerts = []
        
        # KEY LOCATIONS: We only care about Red Line if it hits these
        target_zone = ["Kendall", "MIT", "Central", "Harvard"]

        for alert in alerts:
            attrs = alert['attributes']
            
            # 1. Filter: Only look at significant issues
            if attrs['effect'] in ['DELAY', 'SUSPENSION', 'DETOUR', 'SNOW_ROUTE', 'SHUTTLE']:
                
                header = attrs['header']
                description = attrs['description']
                
                # Check which route this alert belongs to
                # The API returns a list of informed entities; we check the first one
                informed = alert['attributes'].get('informed_entity', [{}])
                route_id = informed[0].get('route_id') if informed else None

                # 2. Logic for Red Line (Kendall <-> Harvard Filter)
                if route_id == "Red":
                    # Check if the text mentions our stations OR "all" (global delay)
                    text_to_check = (header + description).lower()
                    affects_my_commute = any(stop.lower() in text_to_check for stop in target_zone)
                    is_global = "all" in text_to_check or "global" in text_to_check

                    if affects_my_commute or is_global:
                        red_alerts.append(f"⚠️ {header}")

                # 3. Logic for Bus 1 (Always report)
                elif route_id == "1":
                    bus_alerts.append(f"⚠️ {header}")

        # Construct Status Strings
        if not red_alerts:
            red_status = "✅ Service Normal (Kendall <-> Harvard)"
        else:
            red_status = "🚨 **RED LINE ISSUES:**\n" + "\n".join(red_alerts)

        if not bus_alerts:
            bus_status = "✅ Service Normal"
        else:
            bus_status = "🚨 **BUS 1 ISSUES:**\n" + "\n".join(bus_alerts)
            
        return red_status, bus_status

    except Exception as e:
        error_msg = f"Error checking MBTA: {e}"
        return error_msg, error_msg

def check_m2_shuttle():
    """
    Scrapes Longwood Collective website for M2 alerts.
    """
    print("Checking M2 Shuttle...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(M2_URL, headers=headers)
        
        if response.status_code != 200:
            return "⚠️ Could not access Longwood Collective website."

        soup = BeautifulSoup(response.text, 'html.parser')
        page_text = soup.get_text()[:6000] 
        return get_m2_summary(page_text)
    except Exception as e:
        return f"Error checking M2: {e}"

def send_email(subject, body):
    sender = os.environ['EMAIL_USER']
    password = os.environ['EMAIL_PASSWORD']
    
    raw_to = os.environ.get('EMAIL_TO', sender)
    if ',' in raw_to:
        receivers = [e.strip() for e in raw_to.split(',')]
    else:
        receivers = [raw_to]

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = ", ".join(receivers)

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, password)
            server.sendmail(sender, receivers, msg.as_string())
        print(f"✅ Email sent to {len(receivers)} recipient(s)!")
    except Exception as e:
        print(f"❌ Email failed: {e}")

if __name__ == "__main__":
    # 1. Gather Intelligence
    red_status, bus_status = check_mbta_split()
    m2_status = check_m2_shuttle()

    # 2. Determine Subject Line (Smart Logic)
    today = datetime.now().strftime("%a, %b %d")
    
    # Define "Bad News" conditions
    red_bad = "ISSUES" in red_status
    bus_bad = "ISSUES" in bus_status
    m2_bad = "Service Normal" not in m2_status

    if not red_bad and not bus_bad and not m2_bad:
        subject = f"✅ Commute Clear: All Normal ({today})"
    elif red_bad:
        # Prioritize Red Line in subject because it's the most critical
        subject = f"⚠️ Commute Alert: Red Line Issues ({today})"
    elif bus_bad:
        subject = f"⚠️ Commute Alert: Bus 1 Issues ({today})"
    elif m2_bad:
        subject = f"⚠️ Commute Alert: M2 Shuttle Issues ({today})"
    else:
        subject = f"⚠️ Commute Update ({today})"

    # 3. Construct Report
    email_body = f"""
    COMMUTE BRIEFING - {today}
    
    -------------------------------------------
    🚇 RED LINE (Subway)
    {red_status}
    
    -------------------------------------------
    🚌 BUS 1 (Backup)
    {bus_status}

    -------------------------------------------
    🚐 HARVARD M2 SHUTTLE
    {m2_status}
    
    -------------------------------------------
    """

    print(f"Subject: {subject}")
    print(email_body)
    send_email(subject, email_body)
