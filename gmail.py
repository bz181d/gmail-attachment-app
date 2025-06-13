import os
import base64
import mimetypes
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from storage import upload_file_to_supabase
import tempfile

def check_and_download_attachments(credentials):
    service = build('gmail', 'v1', credentials=credentials)
    results = service.users().messages().list(userId='me', labelIds=['INBOX'], q="has:attachment").execute()
    messages = results.get('messages', [])

    for msg in messages:
        msg_data = service.users().messages().get(userId='me', id=msg['id']).execute()
        parts = msg_data.get('payload', {}).get('parts', [])

        for part in parts:
            filename = part.get("filename")
            if not filename:
                continue
            if not (filename.endswith('.xls') or filename.endswith('.xlsx') or filename.endswith('.csv')):
                continue
            if 'data' in part['body']:
                file_data = base64.urlsafe_b64decode(part['body']['data'])
            elif 'attachmentId' in part['body']:
                attachment = service.users().messages().attachments().get(
                    userId='me', messageId=msg['id'], id=part['body']['attachmentId']
                ).execute()
                file_data = base64.urlsafe_b64decode(attachment['data'])
            else:
                continue

            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(file_data)
                temp_file_path = temp_file.name

            email_address = service.users().getProfile(userId='me').execute()['emailAddress']
            upload_file_to_supabase(temp_file_path, email_address, filename)

            os.remove(temp_file_path)
