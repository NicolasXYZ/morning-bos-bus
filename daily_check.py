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
    print
