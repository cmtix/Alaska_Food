import os
from email_server import send_email_alert

if __name__ == "__main__":
    send_email_alert(
        subject="[TEST] Pipeline email working",
        body="This is a test of the Alaska.edu pipeline email alert system."
    )


# To run: enter python test_email.py in console, no quotes.
