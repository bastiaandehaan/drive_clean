from drive_auth import get_drive_service
import json
from pathlib import Path

OUTPUT_FILE = Path("output/drive_index.json")
OUTPUT_FILE.parent.mkdir(exist_ok=True)

def list_all_files():
    service = get_drive_service()
    files = []
    page_token = None

    while True:
        response = service.files().list(
            fields="nextPageToken, files(id, name, mimeType, size, createdTime)",
            pageSize=1000,
            pageToken=page_token
        ).execute()

        files.extend(response.get('files', []))
        page_token = response.get('nextPageToken', None)

        if page_token is None:
            break

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(files, f, indent=2)

    print(f"Indexed {len(files)} files.")

if __name__ == "__main__":
    list_all_files()
