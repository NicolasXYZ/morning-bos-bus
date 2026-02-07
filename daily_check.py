import feedparser
import smtplib
import os
import requests
from email.mime.text import MIMEText
from datetime import datetime
from groq import Groq
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
# Flights
RSS_URL = "https://news.google.com/rss/search?q=(Boston+OR+DC)+AND+(airport+OR+flight+OR+delay+OR+storm+OR+FAA)+when:1d&hl=en-US&gl=US&ceid=US:en"

# Transit (MBTA Route IDs: Red Line = "Red", Bus 1 = "1")
MBTA_API_URL = "https://api-v3.mbta.com/alerts?filter[route]=Red,1&filter[activity]=BOARD,RIDE,PARK"

# M2 Shuttle (Longwood Collective Advisories)
M2_URL = "https://www.longwoodcollective.org/advisories"

def get_groq_summary(text_data, context):
    """
    Asks Groq to summarize raw text.
    context: "flights" or "shuttle"
    """
    try:
        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        
        if context == "flights":
            prompt = f"""
            Summarize flight disruptions for Boston (BOS) or DC (DCA/IAD) based on these headlines. 
            Ignore irrelevant news. If none, say "No major flight issues."
            Data: {text_data}
            """
        elif context == "shuttle":
            prompt = f"""
            Check this text for any delays, detours, or cancellations regarding the "M2 Shuttle" or "Harvard Shuttle".
            If the text mentions holidays, snow, or schedule changes, note them.
            If nothing is relevant to M2, simply say "No M2 shuttle advisories found."
            Data: {text_data}
            """

        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
        )
        return chat.choices[0].message.content
    except Exception as e:
        return f"Error asking AI: {e}"

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
            # Filter out minor things like elevator closures
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
        # Fake a browser user-agent so they don't block us
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(M2_URL, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Get all text from the page body
        page_text = soup.get_text()[:5000] # Limit to first 5000 chars to save AI tokens
        
        # Ask Groq if there is anything worrying in that text
        return get_groq_summary(page_text, context="shuttle")
    except Exception as e:
        return f"Error checking M2: {e}"

def check_flights():
    print("Checking Flights...")
    feed = feedparser.parse(RSS_URL)
    hits = [entry.title for entry in feed.entries][:15]
    
    if hits:
        return get_groq_summary("\n".join(hits), context="flights")
    else:
        return "✅ No major flight news found."

def send_email(subject, body):
    sender = os.environ['EMAIL_USER']
    password = os.environ['EMAIL_PASSWORD']
    # Split the string by comma to get a list of emails
    receivers = os.environ['EMAIL_TO'].split(',')

    # ... (later in the send_email function) ...

    # The 'To' header in the email needs a string, not a list
    msg['To'] = ", ".join(receivers) 

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, password)
            # sendmail expects a LIST of recipients to actually deliver to all of them
            server.sendmail(sender, receivers, msg.as_string())
        print(f"✅ Email sent to {len(receivers)} people!")

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = receiver

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, password)
            server.sendmail(sender, receiver, msg.as_string())
        print("✅ Email sent!")
    except Exception as e:
        print(f"❌ Email failed: {e}")

if __name__ == "__main__":
    # 1. Gather Intelligence
    flight_status = check_flights()
    mbta_status = check_mbta()
    m2_status = check_m2_shuttle()

    # 2. Construct Report
    today = datetime.now().strftime("%A, %B %d")
    
    email_body = f"""
    MORNING BRIEFING - {today}
    -------------------------------------------
    
    🚌 HARVARD M2 SHUTTLE
    {m2_status}
    
    -------------------------------------------
    
    🚇 MBTA (Red Line & Bus 1)
    {mbta_status}
    
    -------------------------------------------
    
    ✈️ FLIGHTS (Boston/DC)
    {flight_status}
    """

    # 3. Logic: Send email ONLY if there is something non-generic
    # OR you can just force send it every day since it now contains transit info
    # which is useful even if "All Clear".
    
    print(email_body)
    send_email(f"Morning Briefing: {today}", email_body)
