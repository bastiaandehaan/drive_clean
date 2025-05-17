from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import json
import pickle
from pathlib import Path
from googleapiclient.errors import HttpError
import sys
import time
import traceback
import requests

# Configuratie
SCOPES = ['https://www.googleapis.com/auth/photoslibrary.readonly']
CONFIG_PATH = Path("photos_config.json")
TOKEN_PATH = Path("token_photos.pkl")
OUTPUT_FILE = Path("output/photos_metadata.json")
OUTPUT_FILE.parent.mkdir(exist_ok=True)


def test_discovery_url():
    """Test of de discovery URL toegankelijk is."""
    discovery_url = "https://photoslibrary.googleapis.com/$discovery/rest?version=v1"
    print(f"Testen van discovery URL: {discovery_url}")
    try:
        response = requests.get(discovery_url)
        if response.status_code == 200:
            print("Discovery URL succesvol opgehaald:")
            print(response.json().get("id", "Geen ID gevonden"))
        else:
            print(
                f"Fout bij het ophalen van de discovery URL: Status code {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Fout bij het testen van de discovery URL: {e}")


def get_photos_service():
    """Authenticeer en maak een Google Photos API-service."""
    try:
        if TOKEN_PATH.exists():
            print(f"Tokenbestand {TOKEN_PATH} gevonden, laden...")
            with open(TOKEN_PATH, "rb") as token:
                creds = pickle.load(token)
            print("Credentials succesvol geladen uit tokenbestand.")
            print(f"Credentials valid: {creds.valid}")
        else:
            if not CONFIG_PATH.exists():
                print(f"Fout: Configuratiebestand {CONFIG_PATH} niet gevonden.")
                sys.exit(1)
            print(f"Configuratiebestand {CONFIG_PATH} gevonden, authenticeren...")
            flow = InstalledAppFlow.from_client_secrets_file(str(CONFIG_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
            print("Authenticatie succesvol, token opslaan...")
            with open(TOKEN_PATH, "wb") as token:
                pickle.dump(creds, token)
        print("Service bouwen...")
        service = build('photoslibrary', 'v1', credentials=creds, cache_discovery=False)
        print("Service succesvol aangemaakt.")
        return service
    except Exception as e:
        print(f"Fout bij het maken van de service: {e}")
        print("Volledige traceback:")
        print(traceback.format_exc())
        sys.exit(1)


def list_photos_metadata():
    """Haal metadata van alle foto's op uit Google Photos."""
    try:
        # Test de discovery URL voordat we de service bouwen
        test_discovery_url()

        service = get_photos_service()
        if not service:
            print(
                "Fout: Kan geen verbinding maken met Google Photos. Controleer je authenticatie.")
            sys.exit(1)

        print("Metadata ophalen van Google Photos...")
        photos = []
        page_token = None
        page_count = 0

        while True:
            try:
                response = service.mediaItems().list(pageSize=100, pageToken=page_token,
                    fields="nextPageToken,mediaItems(id,baseUrl,filename,mimeType,mediaMetadata,productUrl)").execute()

                batch = response.get('mediaItems', [])
                photos.extend(batch)

                page_count += 1
                print(
                    f"Batch {page_count} verwerkt: {len(batch)} items opgehaald (totaal: {len(photos)})")

                page_token = response.get('nextPageToken')
                if not page_token:
                    break

                time.sleep(0.1)

            except HttpError as e:
                print(f"API-fout: {e}")
                if e.resp.status == 403:
                    print("Toegang geweigerd. Controleer je API-rechten.")
                    sys.exit(1)
                elif e.resp.status == 429:
                    print("Rate limit bereikt. Wachten voordat we doorgaan...")
                    time.sleep(5)
                    continue
                else:
                    raise

    except Exception as e:
        print(f"Fout bij het verbinden met Google Photos: {e}")
        sys.exit(1)

    # Schrijf naar JSON-bestand
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(photos, f, indent=2)
        print(f"Geëxporteerd: {len(photos)} foto's naar {OUTPUT_FILE}")
    except Exception as e:
        print(f"Fout bij het schrijven naar {OUTPUT_FILE}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    if __name__ == "__main__":
        list_photos_metadata()