from drive_auth import get_drive_service
import json
from pathlib import Path
import sys
import time
from googleapiclient.errors import HttpError

OUTPUT_FILE = Path("output/drive_index.json")
OUTPUT_FILE.parent.mkdir(exist_ok=True)

def list_all_files():
    try:
        service = get_drive_service()
        if not service:
            print("Fout: Kan geen verbinding maken met Google Drive. Controleer je authenticatie.")
            sys.exit(1)

        print("Bestanden ophalen van Google Drive...")
        files = []
        page_token = None
        page_count = 0

        while True:
            try:
                response = service.files().list(
                    fields="nextPageToken, files(id, name, mimeType, size, createdTime, parents)",
                    pageSize=1000,
                    pageToken=page_token
                ).execute()

                batch = response.get('files', [])
                files.extend(batch)

                page_count += 1
                print(f"Batch {page_count} verwerkt: {len(batch)} bestanden opgehaald (totaal: {len(files)})")

                page_token = response.get('nextPageToken', None)
                if page_token is None:
                    break

                # Optioneel: kleine pauze om rate limits te vermijden
                time.sleep(0.1)

            except HttpError as e:
                print(f"API-fout: {e}")
                if e.resp.status == 403:
                    print("Toegang geweigerd of rate limit bereikt. Controleer je API-rechten of wacht even.")
                    sys.exit(1)
                elif e.resp.status == 429:
                    print("Rate limit bereikt. Wachten voordat we doorgaan...")
                    time.sleep(5)
                    continue
                else:
                    raise

    except Exception as e:
        print(f"Fout bij het verbinden met Google Drive: {e}")
        sys.exit(1)

    # Schrijf naar JSON-bestand
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(files, f, indent=2)
        print(f"Geïndexeerd: {len(files)} bestanden opgeslagen in {OUTPUT_FILE}.")
    except Exception as e:
        print(f"Fout bij het schrijven naar {OUTPUT_FILE}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    list_all_files()