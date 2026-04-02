import smtplib
from email.message import EmailMessage
import os

def send_pdf_email(receiver_email: str, topic: str, pdf_filepath: str):
    """Sends an email with the generated PDF attached using Gmail's SMTP server."""
    
    # --- PUT YOUR CREDENTIALS HERE ---
    # In a real production app, these would be in a .env file!
    SENDER_EMAIL = os.getenv("SENDER_EMAIL")
    APP_PASSWORD = os.getenv("APP_PASSWORD")
    
    # 1. Verify the PDF actually exists
    if not os.path.exists(pdf_filepath):
        print(f"Error: Could not find PDF at {pdf_filepath}")
        return

    # 2. Construct the Email structure
    msg = EmailMessage()
    msg['Subject'] = f"Your AI Research Report: {topic.replace('_', ' ')}"
    msg['From'] = SENDER_EMAIL
    msg['To'] = receiver_email
    
    # The body text of the email
    body_text = f"""Hello,

Your autonomous research agent has finished compiling the report on '{topic.replace('_', ' ')}'.

Please find the requested PDF document attached to this email.

Best regards,
Your AI Agent Backend
"""
    msg.set_content(body_text)

    # 3. Read the PDF and attach it
    with open(pdf_filepath, 'rb') as f:
        pdf_data = f.read()

    msg.add_attachment(
        pdf_data, 
        maintype='application', 
        subtype='pdf', 
        filename=os.path.basename(pdf_filepath)
    )

    # 4. Connect to Gmail and Send!
    try:
        print("--- CONNECTING TO SMTP SERVER ---")
        # Port 587 is the standard secure port for TLS email submission
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls() # Encrypts the connection
            server.login(SENDER_EMAIL, APP_PASSWORD)
            server.send_message(msg)
            
        print(f"--- EMAIL SUCCESSFULLY SENT TO: {receiver_email} ---")
    except Exception as e:
        print(f"--- FAILED TO SEND EMAIL: {e} ---")