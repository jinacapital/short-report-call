import requests
import json
from twilio.rest import Client
import pickle
import os

# Twilio credentials
account_sid = '#UPDATE TWILIO KEY'
auth_token = '#UPDATE TWILIO KEY'
client = Client(account_sid, auth_token)

# Anthropic API credentials
ANTHROPIC_API_KEY = '#UPDATE ANTHROPIC KEY'
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"

# URL to monitor (RSS feed URL)
URL = "https://muddywatersresearch.com/feed/?post_type=reports"

# File to store header values between cron executions
STATE_FILE = "muddy_waters_state.pkl"

def load_state():
    """Load previous ETag and Last-Modified values from file"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'rb') as f:
                return pickle.load(f)
        except Exception as e:
            print(f"Error loading state: {e}")
    return {"etag": None, "last_modified": None}

def save_state(state):
    """Save current ETag and Last-Modified values to file"""
    try:
        with open(STATE_FILE, 'wb') as f:
            pickle.dump(state, f)
    except Exception as e:
        print(f"Error saving state: {e}")

def check_for_update():
    """
    Performs an HTTP GET request with conditional headers.
    Returns (is_updated, content) tuple where:
    - is_updated: True if the feed has been updated, False otherwise
    - content: The RSS content if updated, None otherwise
    """
    state = load_state()
    headers = {}
    if state["etag"]:
        headers["If-None-Match"] = state["etag"]
    if state["last_modified"]:
        headers["If-Modified-Since"] = state["last_modified"]
    
    try:
        response = requests.get(URL, headers=headers)
    except Exception as e:
        print(f"Request error: {e}")
        return False, None
    
    if response.status_code == 304:
        print("No update detected (304 Not Modified).")
        return False, None
    elif response.status_code == 200:
        new_etag = response.headers.get("ETag")
        new_last_modified = response.headers.get("Last-Modified")
        
        # If the header values differ from our stored values, consider it an update.
        if new_etag != state["etag"] or new_last_modified != state["last_modified"]:
            print("Update detected! New data received.")
            # Save new state
            save_state({"etag": new_etag, "last_modified": new_last_modified})
            return True, response.text
        else:
            print("No header changes detected despite 200 response.")
            return False, None
    else:
        print(f"Unexpected status code: {response.status_code}")
        return False, None

def get_stock_name_from_rss(rss_content):
    """
    Uses Anthropic's Claude to extract the stock name from the RSS feed.
    Returns the extracted stock name as a string.
    """
    print("Sending RSS content to Anthropic API...")
    
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    
    # Current API format as of March 2024
    data = {
        "model": "claude-3-5-haiku-20241022",
        "messages": [
            {
                "role": "user",
                "content": f"Please tell the latest stock that has been mentioned. Please tell only the full stock name and no other information. Here is an RSS feed content: {rss_content}\n\n"
            }
        ],
        "max_tokens": 100,
        "temperature": 0.0
    }
    
    try:
        response = requests.post(ANTHROPIC_API_URL, headers=headers, json=data)
        response.raise_for_status()
        
        response_data = response.json()
        print(f"API Response: {json.dumps(response_data, indent=2)}")
        
        # Try to extract the stock name from the response
        stock_name = "unknown stock"
        
        # Check if content is in the response directly
        if "content" in response_data:
            content_list = response_data.get("content", [])
            if content_list and isinstance(content_list, list) and len(content_list) > 0:
                first_content = content_list[0]
                if isinstance(first_content, dict) and "text" in first_content:
                    stock_name = first_content.get("text", "").strip()
        
        # Alternative format: look for a response in the messages
        if stock_name == "unknown stock" and "messages" in response_data:
            messages = response_data.get("messages", [])
            if messages and len(messages) > 0:
                last_message = messages[-1]
                if "content" in last_message and isinstance(last_message["content"], list):
                    content_parts = last_message["content"]
                    for part in content_parts:
                        if "text" in part:
                            stock_name = part["text"].strip()
                            break
        
        # Try to extract from a direct completion field (older API version)
        if stock_name == "unknown stock" and "completion" in response_data:
            stock_name = response_data.get("completion", "").strip()
        
        print(f"Extracted stock name: {stock_name}")
        return stock_name
    except Exception as e:
        print(f"Error calling Anthropic API: {e}")
        print(f"Response content: {response.text if 'response' in locals() else 'No response'}")
        return "unknown stock"

def trigger_phone_calls(stock_name):
    """
    Triggers phone calls via Twilio to multiple numbers using inline TwiML to speak a custom message.
    Includes the stock name in the message.
    """
    # Create a pause between each letter for spelling
    spelling_text = ". ".join(list(stock_name)) + "."
    
    custom_twiml = (
        '<Response>'
            '<Pause length="1"/>'
            '<Say voice="alice" language="en-US">'
                f'Hello, Short report alert! Muddywaters has released a short report on {stock_name}. Muddywaters has released a short report on {stock_name}.'
            '</Say>'
            '<Say voice="alice" language="en-US">'
                f'{spelling_text}'
            '</Say>'
        '</Response>'
    )
    
    # List of phone numbers to call
    phone_numbers = [
        "+1XXXXXXXXXX"  # UPDATE WITH YOUR PHONE NUMBER
        "+1XXXXXXXXXX"  # UPDATE OTHER NUMBER TO BE ADDED, if any
    ]
    
    print(f"Triggering phone calls with stock information: {stock_name}")
    
    # Call each number in the list
    for phone_number in phone_numbers:
        call = client.calls.create(
            to=phone_number,
            from_="+1XXXXXXXXXX",  # Your Twilio number
            twiml=custom_twiml
        )
        print(f"Call initiated to {phone_number}. Call SID: {call.sid}")

def main():
    """Main function to be executed by cron"""
    print("--- Checking for RSS updates ---")
    is_updated, content = check_for_update()
    
    if is_updated and content:
        stock_name = get_stock_name_from_rss(content)
        trigger_phone_calls(stock_name)
    else:
        print("No update; nothing to do.")

if __name__ == "__main__":
    main()
