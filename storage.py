import os
from supabase import create_client
from datetime import datetime

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_KEY']

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def upload_file_to_supabase(file_path, user_email, filename):
    folder = user_email.replace('@', '_at_')
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    storage_path = f"{folder}/{timestamp}_{filename}"

    with open(file_path, "rb") as f:
        supabase.storage.from_("attachments").upload(storage_path, f, {"content-type": "application/octet-stream"})

def list_user_files(user_email):
    folder = user_email.replace('@', '_at_')
    try:
        files = supabase.storage.from_("attachments").list(folder)
        file_list = []
        for file in files:
            file_url = f"{SUPABASE_URL}/storage/v1/object/public/attachments/{folder}/{file['name']}"
            file_list.append({"name": file['name'], "url": file_url})
        return file_list
    except Exception:
        return []
