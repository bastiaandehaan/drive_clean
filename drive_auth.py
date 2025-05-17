from google_auth_oauthlib.flow import InstalledAppFlow  # Zorg dat dit pakket is geïnstalleerd
from googleapiclient.discovery import build  # Zorg dat dit pakket is geïnstalleerd
import pickle
from pathlib import Path

SCOPES = ['https://www.googleapis.com/auth/drive']  # Scope voor volledige toegang
TOKEN_PATH = Path("token_drive.pkl")
CONFIG_PATH = Path("drive_config.json")

def get_drive_service():
    if TOKEN_PATH.exists():
        with open(TOKEN_PATH, "rb") as token:
            creds = pickle.load(token)
    else:
        flow = InstalledAppFlow.from_client_secrets_file(str(CONFIG_PATH), SCOPES)
        creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "wb") as token:  # Binary write modus
            pickle.dump(creds, token)  # Geen typefout, werkt met "wb"
    return build('drive', 'v3', credentials=creds)