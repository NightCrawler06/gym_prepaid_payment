import smtplib
import ssl
from email.message import EmailMessage

sender_email = "euelv720@gmail.com"
receiver_email = "villavicencio.franc@gmail.com"
app_password = "sxhe lswp plkm wqck"  

subject = "Test Email"
body = "Hello, this is a test email sent via Gmail SMTP."

msg = EmailMessage()
msg["From"] = sender_email
msg["To"] = receiver_email
msg["Subject"] = subject
msg.set_content(body)

context = ssl.create_default_context()

with smtplib.SMTP("smtp.gmail.com", 587) as server:
    server.starttls(context=context)
    server.login(sender_email, app_password)
    server.send_message(msg)

print("Email sent successfully.")