import os
import time
import requests

WHAPI_TOKEN = os.environ.get("WHAPI_TOKEN")
WHAPI_URL = os.environ.get("WHAPI_URL", "https://gate.whapi.cloud")
WHATSAPP_NUMBER = os.environ.get("WHATSAPP_NUMBER", "919500055366")


def send_message(text, retries=3, timeout=45):
    if not WHAPI_TOKEN:
        print("WHAPI_TOKEN not set")
        return False

    url = f"{WHAPI_URL}/messages/text"
    headers = {
        "Authorization": f"Bearer {WHAPI_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "to": WHATSAPP_NUMBER,
        "body": text,
    }

    for attempt in range(1, retries + 1):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=timeout)
            if response.status_code in (200, 201):
                print("Message sent successfully")
                return True
            else:
                print(f"Failed to send message: {response.status_code} {response.text}")
                return False
        except requests.exceptions.Timeout:
            print(f"Timeout on attempt {attempt}/{retries}")
            if attempt < retries:
                time.sleep(5 * attempt)
    print("All retries exhausted, message not sent")
    return False


def send_in_chunks(text, chunk_size=4000):
    lines = text.split("\n")
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) + 1 > chunk_size:
            send_message(chunk.strip())
            chunk = line + "\n"
        else:
            chunk += line + "\n"
    if chunk.strip():
        send_message(chunk.strip())
