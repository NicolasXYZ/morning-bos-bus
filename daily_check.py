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
        3. If there is no relevant M2 news, reply exactly: "✅ No M2 shuttle advisories found."
        
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

def check_mbta():
    """
    Checks official MBTA API for Red Line and Bus 1.
    """
    print("Checking MBTA...")
    try:
        response = requests.get(MBTA_API_URL)
        alerts = response.json().get('data', [])
        
        relevant_alerts = []
        for alert in alerts:
            attrs = alert['attributes']
            # Filter for meaningful disruptions only
            if attrs['effect'] in ['DELAY', 'SUSPENSION', 'DETOUR', 'SNOW_ROUTE', 'SHUTTLE']:
                header = attrs['header']
                description = attrs['description']
                relevant_alerts.append(f"⚠️ {header}\nDetails: {description}")
        
        if not relevant_alerts:
            return "✅ MBTA (Red Line & Bus 1): Running normally."
        return "🚨 **MBTA ISSUES FOUND:**\n" + "\n\n".join(relevant_alerts)
    except Exception as e:
        return f"Error checking MBTA: {e}"

def check_m2_shuttle():
    """
    Scrapes Longwood Collective website for M2 alerts.
    """
    print("Checking M2 Shuttle...")
    try:
        # Fake a browser user-agent to avoid being blocked
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(M2_URL, headers=headers)
        
        if response.status_code != 200:
            return "⚠️ Could not access Longwood Collective website."

        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Get all text from the page body (limit to 6000 chars for AI)
        page_text = soup.get_text()[:6000] 
        
        return get_m2_summary(page_text)
    except Exception as e:
        return f"Error checking M2: {e}"

# --- THE MISSING PART IS BELOW ---

def send_email(subject, body):
    print("--- PREPARING EMAIL ---")
    
    # 1. Validation to prevent crashes if secrets are missing
    if not os.environ.get('EMAIL_USER') or not os.environ.get('EMAIL_PASSWORD'):
        print("❌ ERROR: Email secrets are missing. Cannot send.")
        return

    sender = os.environ['EMAIL_USER']
    password = os.environ['EMAIL_PASSWORD']
    
    # 2. Handle multiple recipients (split by comma)
    raw_to = os.environ.get('EMAIL_TO', sender) # Default to self if missing
    if ',' in raw_to:
        receivers = [e.strip() for e in raw_to.split(',')]
    else:
        receivers = [raw_to]

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = ", ".join(receivers) # This is just the visual header

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, password)
            server.sendmail(sender, receivers, msg.as_string()) # This actually sends it
        print(f"✅ Email successfully sent to {len(receivers)} recipient(s)!")
    except Exception as e:
        print(f"❌ Email failed: {e}")

if __name__ == "__main__":
    # 1. Gather Intelligence
    mbta_status = check_mbta()
    m2_status = check_m2_shuttle()

    # 2. Determine Subject Line (The "Smart" Part)
    today = datetime.now().strftime("%a, %b %d")
    
    # Check if strings contain "Normal" or "No ... advisories"
    mbta_bad = "ISSUES FOUND" in mbta_status
    m2_bad = "No M2 shuttle advisories" not in m2_status

    if not mbta_bad and not m2_bad:
        subject = f"✅ Commute Clear: All Normal ({today})"
    elif mbta_bad and m2_bad:
        subject = f"⚠️ Commute Alert: Issues on M2 AND MBTA ({today})"
    elif mbta_bad:
        # Extract just the header of the first MBTA issue for the subject
        # e.g., "⚠️ Commute Alert: Red Line Delay..."
        first_issue = mbta_status.split('\n')[1].replace('⚠️ ', '')[:30] 
        subject = f"⚠️ Commute Alert: MBTA {first_issue}... ({today})"
    elif m2_bad:
        subject = f"⚠️ Commute Alert: M2 Shuttle Issues ({today})"

    # 3. Construct Report
    email_body = f"""
    COMMUTE BRIEFING - {today}
    
    -------------------------------------------
    🚌 HARVARD M2 SHUTTLE
    {m2_status}
    
    -------------------------------------------
    🚇 MBTA (Red Line & Bus 1)
    {mbta_status}
    
    -------------------------------------------
    """

    print(f"Subject: {subject}")
    send_email(subject, email_body)
