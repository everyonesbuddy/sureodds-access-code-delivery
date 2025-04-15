from flask import Flask, request, jsonify
import stripe
import requests
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content
from postmarker.core import PostmarkClient
import os
from dotenv import load_dotenv  # Import dotenv to load local .env files

# Initialize Flask app
app = Flask(__name__)

# Load environment variables from a .env file if available (for local development)
load_dotenv()

# Set up API keys from environment variables
stripe.api_key = os.getenv("STRIPE_API_KEY")  # Stripe API secret key
endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")  # Stripe webhook secret
POSTMARK_API_TOKEN = os.getenv("POSTMARK_API_TOKEN")
POSTMARK_SENDER_EMAIL = os.getenv("POSTMARK_SENDER_EMAIL")  # verified sender

def generate_code():
    """Fetch an unused code from the API."""
    url = "https://sure-odds-be-482948f2bda5.herokuapp.com/api/v1/codes/"

    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        codes = response.json()

        for code_entry in codes["data"]:
            if code_entry.get("isUsed") == False and code_entry.get("isSent") == False:
                return code_entry.get("code"), code_entry.get("_id")  # Return both code and _id

        print("No unused codes available.")
        return None, None  # Return None if no unused codes are found
    except requests.exceptions.RequestException as e:
        print(f"Error fetching codes from API: {e}")
        return None, None  # Return None if there was an error

def update_code_status(code, code_id):
    """Update the code's status to used."""
    url = f"https://sure-odds-be-482948f2bda5.herokuapp.com/api/v1/codes/{code_id}"
    headers = {
        "Content-Type": "application/json",
    }
    data = {
        "code": code,
        "isSent": True,
    }

    try:
        response = requests.patch(url, headers=headers, json=data)
        response.raise_for_status()  # Raise an exception for HTTP errors
        print(f"Code {code} status updated to used.")
    except requests.exceptions.RequestException as e:
        print(f"Error updating code status: {e}")

def send_email(to_email, code, code_id):
    """Send the generated code to the user's email using Postmark."""
    client = PostmarkClient(server_token=POSTMARK_API_TOKEN)

    try:
        response = client.emails.send(
            From=POSTMARK_SENDER_EMAIL,
            To=to_email,
            Subject="Your Unblock Code",
            TextBody=f"Thank you for your payment! Here is your 10 minutes unblock code: {code}\n\nEnjoy unlimited entries once applied."
        )
        print(f"Email sent to {to_email} with code {code}")
        print(f"Postmark Response: {response}")
        update_code_status(code, code_id)  # Update the code's status after sending the email
    except Exception as e:
        print(f"Error sending email via Postmark: {e}")

@app.route('/')
def index():
    """Default route to show a welcome message."""
    return "Welcome to Access Code Delivery!"

@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    """Stripe webhook to handle successful payments."""
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, endpoint_secret)
        print("Stripe webhook event successfully verified.")
    except ValueError:
        print("Invalid payload received.")
        return "Invalid payload", 400
    except stripe.error.SignatureVerificationError:
        print("Invalid signature received.")
        return "Invalid signature", 400

    if event['type'] == 'charge.succeeded':
        payment_intent = event['data']['object']
        email = payment_intent.get('receipt_email') or payment_intent.get('billing_details', {}).get('email')

        print(f"Payment Intent ID: {payment_intent['id']}")
        print(f"Payment Intent status: {payment_intent['status']}")

        if email:
            print(f"Payment succeeded for email: {email}")
            code, code_id = generate_code()  # Unpack the tuple returned by generate_code
            if code and code_id:
                send_email(email, code, code_id)
                print(f"Code {code} (ID: {code_id}) sent to {email}")
            else:
                print("No unused code available to send.")
        else:
            print("No email found in payment intent.")

    else:
        print(f"Unhandled event type: {event['type']}")

    return jsonify({'status': 'success'})

if __name__ == '__main__':
    # Heroku provides PORT as an environment variable
    port = int(os.environ.get("PORT", 4242))
    app.run(host="0.0.0.0", port=port)
