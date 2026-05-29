import base64
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
import os
import time

SCOPES = ['https://www.googleapis.com/']

def authenticate():
    creds = None

    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            'gmailcred.json', SCOPES)
        creds = flow.run_local_server(port=0)

        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return creds


PREFIX = "cosai test"

def add_prefix(subject):
    if subject.startswith(PREFIX):
        return subject
    return f"{PREFIX} | {subject}"


def create_message(to, subject, body):
    subject = add_prefix(subject)

    message = MIMEText(body)
    message['to'] = to
    message['subject'] = subject

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {'raw': raw}


def send_message(service, user_id, message, thread_id=None):
    if thread_id:
        message['threadId'] = thread_id

    sent = service.users().messages().send(
        userId=user_id,
        body=message
    ).execute()

    return sent


def main():
    creds = authenticate()
    service = build('gmail', 'v1', credentials=creds)

    to_email = "sutonious@gmail.com"
    subject = "Draft Proposal for Acme Corp"

    # ---- First email (creates thread) ----
    msg1 = create_message(
        to_email,
        subject,
        "Please prepare the draft proposal by tomorrow morning."
    )

    sent1 = send_message(service, "me", msg1)
    thread_id = sent1['threadId']

    print("Thread created:", thread_id)
    time.sleep(2)

    # ---- Reply 1 ----
    msg2 = create_message(
        to_email,
        "Re: " + subject,
        "Working on it. Will share a draft by tonight."
    )

    send_message(service, "me", msg2, thread_id)
    time.sleep(2)

    # ---- Reply 2 ----
    msg3 = create_message(
        to_email,
        "Re: " + subject,
        "We need this sooner. Client requested it by 6 PM today."
    )

    send_message(service, "me", msg3, thread_id)
    time.sleep(2)

    # ---- Reply 3 ----
    msg4 = create_message(
        to_email,
        "Re: " + subject,
        "Draft proposal completed and shared."
    )

    send_message(service, "me", msg4, thread_id)

    print("All messages sent in one thread!")


if __name__ == '__main__':
    main()