from __future__ import print_function
import os.path
import base64
from email.utils import parsedate_to_datetime
from datetime import datetime

import pickle

SCOPES = ['https://www.googleapis.com/']


def _decode_b64(data):
    if not data:
        return ""
    try:
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _extract_plain_text(payload):
    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {})
    data = body.get("data")

    if mime_type == "text/plain" and data:
        return _decode_b64(data)

    parts = payload.get("parts", []) or []
    for part in parts:
        text = _extract_plain_text(part)
        if text:
            return text
    return ""


def _header_value(headers, name):
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _load_google_deps():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Missing Gmail dependencies. Install with: "
            "pip install google-api-python-client google-auth google-auth-oauthlib"
        ) from exc
    return InstalledAppFlow, build, Request, Credentials


def authenticate():
    InstalledAppFlow, _, Request, _ = _load_google_deps()
    creds = None

    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if not os.path.exists("gmailcred.json"):
            raise FileNotFoundError(
                "Missing gmailcred.json in project root. "
                "Download OAuth client credentials from Google Cloud Console."
            )
        flow = InstalledAppFlow.from_client_secrets_file(
            'gmailcred.json', SCOPES)
        creds = flow.run_local_server(port=0)

    with open('token.pickle', 'wb') as token:
        pickle.dump(creds, token)

    return creds


def fetch_emails(max_results=5, query=None):
    _, build, _, _ = _load_google_deps()
    creds = authenticate()
    service = build('gmail', 'v1', credentials=creds)

    params = {"userId": "me", "maxResults": max_results}
    effective_query = (query or "").strip()
    if effective_query:
        params["q"] = effective_query
    results = service.users().messages().list(**params).execute()


    messages = results.get('messages', [])

    extracted = []

    for msg in messages:
        msg_data = service.users().messages().get(
            userId='me',
            id=msg['id'],
            format='full'
        ).execute()

        payload = msg_data.get("payload", {})
        headers = payload.get("headers", [])
        subject = _header_value(headers, "Subject")
        sender = _header_value(headers, "From")
        date_header = _header_value(headers, "Date")
        snippet = msg_data.get("snippet", "")
        body_text = _extract_plain_text(payload)

        timestamp = ""
        if date_header:
            try:
                timestamp = parsedate_to_datetime(date_header).isoformat()
            except Exception:
                timestamp = ""

        extracted.append({
            "text": subject,  # keep subject as primary task extraction text
            "subject": subject,
            "snippet": snippet,
            "body": body_text,
            "full_text": "\n".join([x for x in [subject, snippet, body_text] if x]).strip(),
            "sender": sender,
            "timestamp": timestamp,
            "thread_id": msg_data.get("threadId", ""),
            "message_id": msg_data.get("id", ""),
        })

    return extracted


def _serialize_expiry(value):
    if not value:
        return ""
    if isinstance(value, str):
        return value
    try:
        return value.isoformat()
    except Exception:
        return ""


def _build_creds_from_account(account):
    _, _, _, Credentials = _load_google_deps()
    scopes = (account.get("scopes") or "").split()
    if not scopes:
        scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
    creds = Credentials(
        token=account.get("access_token", ""),
        refresh_token=account.get("refresh_token", ""),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
        client_secret=os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
        scopes=scopes,
    )
    return creds


def _refresh_connected_account_if_needed(account, creds):
    _, _, Request, _ = _load_google_deps()
    if creds.valid:
        return creds, account

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        account["access_token"] = creds.token or account.get("access_token", "")
        account["refresh_token"] = creds.refresh_token or account.get("refresh_token", "")
        account["token_expiry"] = _serialize_expiry(creds.expiry)
    return creds, account


def fetch_emails_for_account(account, max_results=5, query=None):
    """
    Fetch emails for a previously connected Gmail account.

    `account` must include access/refresh token fields from `connected_accounts`.
    """
    _, build, _, _ = _load_google_deps()
    creds = _build_creds_from_account(account)
    creds, updated_account = _refresh_connected_account_if_needed(account, creds)
    service = build("gmail", "v1", credentials=creds)

    effective_query = (query or account.get("query_filter") or "").strip()
    params = {"userId": "me", "maxResults": int(max_results)}
    if effective_query:
        params["q"] = effective_query

    results = service.users().messages().list(**params).execute()
    messages = results.get("messages", [])
    extracted = []

    for msg in messages:
        msg_data = service.users().messages().get(
            userId="me",
            id=msg["id"],
            format="full",
        ).execute()

        payload = msg_data.get("payload", {})
        headers = payload.get("headers", [])
        subject = _header_value(headers, "Subject")
        sender = _header_value(headers, "From")
        date_header = _header_value(headers, "Date")
        snippet = msg_data.get("snippet", "")
        body_text = _extract_plain_text(payload)

        timestamp = ""
        if date_header:
            try:
                timestamp = parsedate_to_datetime(date_header).isoformat()
            except Exception:
                timestamp = ""

        extracted.append(
            {
                "text": subject,
                "subject": subject,
                "snippet": snippet,
                "body": body_text,
                "full_text": "\n".join([x for x in [subject, snippet, body_text] if x]).strip(),
                "sender": sender,
                "timestamp": timestamp,
                "thread_id": msg_data.get("threadId", ""),
                "message_id": msg_data.get("id", ""),
            }
        )

    updated_account["last_fetched_at"] = datetime.now().isoformat()
    return extracted, updated_account


if __name__ == "__main__":
    emails = fetch_emails()
    for e in emails:
        print(e)
