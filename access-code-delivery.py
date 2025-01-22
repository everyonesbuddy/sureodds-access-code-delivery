from flask import Flask, request, jsonify
import stripe
import requests
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content
import os
from dotenv import load_dotenv  # Import dotenv to load local .env files

# Initialize Flask app
app = Flask(__name__)

# Load environment variables from a .env file if available (for local development)
load_dotenv()

# Set up API keys from environment variables
stripe.api_key = os.getenv("STRIPE_API_KEY")  # Stripe API secret key
endpoint_secret = os.getenv("STRIPE_WEBHOOK_SECRET")  # Stripe webhook secret
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")  # SendGrid API key

def generate_code():
    """Fetch an unused code from the API."""
    url = "https://api.sheetbest.com/sheets/ef14d1b6-72df-47a9-8be8-9046b19cfa87"

    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        codes = response.json()

        for code_entry in codes:
            if code_entry.get("isUsed") == "FALSE" and code_entry.get("isSent") == "FALSE":
                return code_entry.get("Code")

        print("No unused codes available.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching codes from API: {e}")
        return None

def update_code_status(code):
    """Update the code's status to used."""
    url = f"https://api.sheetbest.com/sheets/ef14d1b6-72df-47a9-8be8-9046b19cfa87/Code/{code}"
    headers = {
        "Content-Type": "application/json",
    }
    data = {
        "Code": code,
        "isSent": "TRUE",
    }

    try:
        response = requests.patch(url, headers=headers, json=data)
        response.raise_for_status()  # Raise an exception for HTTP errors
        print(f"Code {code} status updated to used.")
    except requests.exceptions.RequestException as e:
        print(f"Error updating code status: {e}")

def send_email(to_email, code):
    """Send the generated code to the user's email using SendGrid."""
    sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
    from_email = Email("info@sure-odds.com")  # Your verified sender email
    to_email = To(to_email)
    subject = "Your Unblock Code"
    content = Content("text/plain", f"Thank you for your payment! Here is your unblock code: {code}\n\nUse this code to unblock your sites for 10 minutes.")
    mail = Mail(from_email, to_email, subject, content)

    try:
        response = sg.send(mail)
        print(f"Email sent to {to_email.email} with code {code}")
        print(f"SendGrid Response Status: {response.status_code}")
        print(f"SendGrid Response Body: {response.body}")
        update_code_status(code)  # Update the code's status after sending the email
    except Exception as e:
        print(f"Error sending email: {e}")

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
            code = generate_code()
            if code:
                send_email(email, code)
                print(f"Code {code} sent to {email}")
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
