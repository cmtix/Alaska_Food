# --------------------- EMAIL ALERT SETTINGS --------------------- #
SMTP_SERVER   = "smtp.gmail.com"   # change if not Gmail
SMTP_PORT     = 587
SMTP_USER     = "vlcollier@alaska.edu"
SMTP_PASS     = os.getenv("aksc upcs gfai wxzt") # Note: this is specific to account;
              # must set up in Google Account under Security - it's called "App Specific Password" # safer: set in env var
EMAIL_TO      = "vlcollier@alaska.edu"
EMAIL_FROM    = SMTP_USER


import smtplib
from email.mime.text import MIMEText
import os


def send_email_alert(subject: str, body: str):
    """Send an email alert if the pipeline fails."""
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())
        print(f"[ALERT] Email sent to {EMAIL_TO}")
    except Exception as e:
        print(f"[WARN] Failed to send email alert: {e}")





# 
# # --------------------- EMAIL ALERT SETTINGS --------------------- #
# import smtplib
# from email.mime.text import MIMEText
# 
# SMTP_SERVER   = "smtp.gmail.com"
# SMTP_PORT     = 587
# SMTP_USER     = "vlcollier@alaska.edu"
# 
# # ⚠️ TEMPORARY: paste your Gmail App Password directly here
# SMTP_PASS     = "aksc upcs gfai wxzt"
# 
# EMAIL_TO      = "vlcollier@alaska.edu"
# EMAIL_FROM    = SMTP_USER
# 
# 
# def send_email_alert(subject: str, body: str):
#     """Send an email alert if the pipeline fails."""
#     try:
#         msg = MIMEText(body, "plain", "utf-8")
#         msg["Subject"] = subject
#         msg["From"] = EMAIL_FROM
#         msg["To"] = EMAIL_TO
# 
#         with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=30) as server:
#             server.starttls()
#             server.login(SMTP_USER, SMTP_PASS)
#             server.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())
#         print(f"[ALERT] Email sent to {EMAIL_TO}")
#     except Exception as e:
#         print(f"[WARN] Failed to send email alert: {e}")
