import json
from pathlib import Path
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
import csv
from typing import Dict, List, Set, Tuple, Optional, Any

# Configuratie
INPUT_FILE = Path("output/drive_index.json")
OUTPUT_DIR = Path("output")
STRUCTURE_OUTPUT = OUTPUT_DIR / "drive_structure.txt"
STATS_OUTPUT = OUTPUT_DIR / "drive_stats.json"
DUPLICATE_OUTPUT = OUTPUT_DIR / "potential_duplicates.csv"
EXACT_DUPES_OUTPUT = OUTPUT_DIR / "exact_duplicates.csv"
OLD_FILES_OUTPUT = OUTPUT_DIR / "old_files.csv"
UNUSED_FILES_OUTPUT = OUTPUT_DIR / "unused_files.csv"
CATEGORIES_OUTPUT = OUTPUT_DIR / "categorized_files.json"
REORG_PLAN_OUTPUT = OUTPUT_DIR / "reorganization_plan.txt"
SUGGESTIONS_OUTPUT = OUTPUT_DIR / "improvement_suggestions.txt"
VISUALIZATION_OUTPUT = OUTPUT_DIR / "folder_tree.html"

# Maak output directory
OUTPUT_DIR.mkdir(exist_ok=True)


class DriveAnalyzer:
    def __init__(self, input_file: Path):
        self.input_file = input_file
        self.files = []
        self.folders = []
        self.folder_map = {}  # id -> folder
        self.children_map = defaultdict(list)  # parent_id -> [children]
        self.root_folders = []
        self.orphan_folders = []
        self.file_types = defaultdict(int)
        self.largest_files = []
        self.potential_duplicates = []
        self.exact_duplicates = []
        self.old_files = []
        self.unused_files = []
        self.categories = {}
        self.loaded = False

        # Categorisatiepatronen
        self.category_patterns = {
            'Photos': [r'\.(jpg|jpeg|png|gif|bmp|heic)$', r'image/'],
            'Documents': [r'\.(pdf|doc|docx|txt|rtf|odt)$', r'document', r'text/plain'],
            'Spreadsheets': [r'\.(xls|xlsx|csv|ods)$', r'spreadsheet', r'text/csv'],
            'Presentations': [r'\.(ppt|pptx|key)$', r'presentation'],
            'Videos': [r'\.(mp4|mov|avi|mkv|3gpp)$', r'video/'],
            'Audio': [r'\.(mp3|wav|ogg|m4a)$', r'audio/'],
            'Archives': [r'\.(zip|rar|gz|7z|tar)$', r'application/.*zip'],
            'Code': [r'\.(py|java|js|html|css|php)$', r'text/.*script'], }

    def load_data(self) -> None:
        """Laad de JSON-data en initialiseer de basisstructuren"""
        print(f"Data laden uit {self.input_file}...")
        try:
            with open(self.input_file, "r", encoding="utf-8") as f:
                self.files = json.load(f)

            # Filter folders
            self.folders = [f for f in self.files if
                            f.get('mimeType') == 'application/vnd.google-apps.folder']

            # Maak een map van folder ID naar folder object
            self.folder_map = {folder['id']: folder for folder in self.folders}

            # Bouw parent-child relaties
            has_parent = set()
            for item in self.files:
                parents = item.get('parents', [])
                for parent_id in parents:
                    has_parent.add(item['id'])
                    self.children_map[parent_id].append(item)

            # Identificeer root folders en orphan folders
            folder_ids = set(self.folder_map.keys())
            for folder_id in folder_ids:
                folder = self.folder_map[folder_id]
                if not folder.get('parents'):
                    self.root_folders.append(folder)
                elif not any(parent in self.folder_map for parent in
                             folder.get('parents', [])):
                    self.orphan_folders.append(folder)

            # Categoriseer bestandstypes
            for file in self.files:
                if file.get('mimeType') != 'application/vnd.google-apps.folder':
                    self.file_types[file.get('mimeType', 'unknown')] += 1

            # Sorteer grootste bestanden
            non_folders = [f for f in self.files if f.get(
                'mimeType') != 'application/vnd.google-apps.folder' and 'size' in f]
            for f in non_folders:
                if 'size' in f:
                    try:
                        f['size'] = int(f['size'])
                    except ValueError:
                        f['size'] = 0

            self.largest_files = sorted(non_folders, key=lambda x: x.get('size', 0),
                                        reverse=True)[:100]

            self.loaded = True
            print(f"Data geladen: {len(self.files)} items, {len(self.folders)} mappen")

        except Exception as e:
            print(f"Fout bij laden van data: {e}")

    def get_folder_path(self, folder_id: str, visited: Set[str] = None) -> str:
        """Reconstrueer het pad van een map op basis van parent relaties"""
        if visited is None:
            visited = set()

        if folder_id in visited:
            return "/...cyclische referentie..."

        visited.add(folder_id)

        if folder_id not in self.folder_map:
            return "/onbekend"

        folder = self.folder_map[folder_id]
        parents = folder.get('parents', [])

        if not parents:
            return f"/{folder['name']}"

        # Neem de eerste parent
        parent_id = parents[0]
        parent_path = self.get_folder_path(parent_id, visited)

        return f"{parent_path}/{folder['name']}"

    def analyze_structure(self) -> None:
        """Analyseer en visualiseer de mapstructuur"""
        if not self.loaded:
            self.load_data()

        print("Mapstructuur analyseren...")

        with open(STRUCTURE_OUTPUT, "w", encoding="utf-8") as f:
            f.write(
                f"Google Drive Mapstructuur - Gegenereerd op {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            # Recursieve functie om folder tree te printen
            def print_folder_tree(folder_id, depth=0, file=f):
                if folder_id not in self.folder_map:
                    return

                folder = self.folder_map[folder_id]
                indent = "  " * depth
                file.write(f"{indent}- {folder['name']} (ID: {folder_id})\n")

                children = [item for item in self.children_map[folder_id] if item.get(
                    'mimeType') == 'application/vnd.google-apps.folder']

                for child in sorted(children, key=lambda x: x['name']):
                    print_folder_tree(child['id'], depth + 1, file)

            # Print root folders
            f.write("Root mappen:\n")
            for folder in sorted(self.root_folders, key=lambda x: x['name']):
                print_folder_tree(folder['id'])

            # Print orphan folders
            if self.orphan_folders:
                f.write("\nWezen mappen (geen geldige parent):\n")
                for folder in sorted(self.orphan_folders, key=lambda x: x['name']):
                    f.write(f"- {folder['name']} (ID: {folder['id']})\n")

        print(f"Mapstructuur geëxporteerd naar {STRUCTURE_OUTPUT}")

    def find_potential_duplicates(self) -> None:
        """Identificeer potentiële duplicaten op basis van bestandsnaam"""
        if not self.loaded:
            self.load_data()

        print("Zoeken naar mogelijke duplicaten...")

        # Groepeer bestanden op naam
        files_by_name = defaultdict(list)
        for file in self.files:
            if file.get('mimeType') != 'application/vnd.google-apps.folder':
                files_by_name[file['name']].append(file)

        # Filter voor namen met meerdere bestanden
        duplicates = {name: files for name, files in files_by_name.items() if
                      len(files) > 1}

        with open(DUPLICATE_OUTPUT, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Bestandsnaam', 'Aantal kopieën', 'Bestand IDs', 'Mappen'])

            for name, files in sorted(duplicates.items(), key=lambda x: len(x[1]),
                                      reverse=True):
                file_ids = [f['id'] for f in files]
                paths = []

                for file in files:
                    if 'parents' in file and file['parents']:
                        parent_id = file['parents'][0]
                        paths.append(self.get_folder_path(parent_id))
                    else:
                        paths.append("(geen parent)")

                writer.writerow(
                    [name, len(files), ', '.join(file_ids), ' | '.join(paths)])
                self.potential_duplicates.append(
                    {'name': name, 'count': len(files), 'files': files})

        print(
            f"Gevonden: {len(duplicates)} potentiële duplicaten, opgeslagen in {DUPLICATE_OUTPUT}")

    def find_exact_duplicates(self) -> None:
        """Identificeer exacte duplicaten op basis van naam én grootte"""
        if not self.loaded:
            self.load_data()

        print("Zoeken naar exacte duplicaten...")

        # Groepeer op naam en grootte
        name_size_groups = defaultdict(list)
        for file in self.files:
            if file.get(
                    'mimeType') != 'application/vnd.google-apps.folder' and 'size' in file:
                key = (file['name'], int(file['size']))
                name_size_groups[key].append(file)

        # Filter groepen met meer dan 1 bestand
        exact_dupes = []
        for (name, size), files in name_size_groups.items():
            if len(files) > 1:
                exact_dupes.append(
                    {'name': name, 'size': size, 'files': files, 'count': len(files)})

        self.exact_duplicates = sorted(exact_dupes, key=lambda x: x['size'],
                                       reverse=True)

        # Schrijf naar CSV
        with open(EXACT_DUPES_OUTPUT, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Bestandsnaam', 'Grootte', 'Aantal kopieën', 'Paden'])

            for dupe in self.exact_duplicates:
                paths = []
                for file in dupe['files']:
                    if 'parents' in file and file['parents']:
                        parent_id = file['parents'][0]
                        paths.append(self.get_folder_path(parent_id))
                    else:
                        paths.append("(geen parent)")

                writer.writerow(
                    [dupe['name'], self._bytes_to_readable(dupe['size']), dupe['count'],
                        ' | '.join(paths)])

        print(
            f"Gevonden: {len(self.exact_duplicates)} exacte duplicaten, opgeslagen in {EXACT_DUPES_OUTPUT}")

    def find_old_files(self, days_threshold=365) -> None:
        """Identificeer bestanden die ouder zijn dan de gegeven drempel"""
        if not self.loaded:
            self.load_data()

        print(f"Zoeken naar bestanden ouder dan {days_threshold} dagen...")

        # Fix: zorg dat beide datetimes timezone-aware zijn, of beide naive
        now = datetime.now()  # Offset-naive
        threshold_date = now - timedelta(days=days_threshold)
        old_files = []

        for file in self.files:
            if file.get('mimeType') == 'application/vnd.google-apps.folder':
                continue

            if 'createdTime' in file:
                # Maak created_date ook naive door de timezone info weg te halen
                created_time = file['createdTime'].replace('Z', '')
                created_date = datetime.fromisoformat(created_time)

                if created_date < threshold_date:
                    file_path = "/"
                    if 'parents' in file and file['parents']:
                        parent_id = file['parents'][0]
                        file_path = self.get_folder_path(parent_id)

                    old_files.append(
                        {'id': file['id'], 'name': file['name'], 'path': file_path,
                            'created': created_date,
                            'age_days': (now - created_date).days,
                            'size': int(file.get('size', 0)) if 'size' in file else 0})

        self.old_files = sorted(old_files, key=lambda x: x['age_days'], reverse=True)

        # Schrijf naar CSV
        with open(OLD_FILES_OUTPUT, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(
                ['Bestandsnaam', 'Leeftijd (dagen)', 'Aanmaakdatum', 'Grootte', 'Pad'])

            for file in self.old_files:
                writer.writerow([file['name'], file['age_days'],
                    file['created'].strftime('%Y-%m-%d'),
                    self._bytes_to_readable(file['size']), file['path']])

        print(
            f"Gevonden: {len(self.old_files)} oude bestanden, opgeslagen in {OLD_FILES_OUTPUT}")

    def find_unused_files(self) -> None:
        """Identificeer potentieel ongebruikte bestanden op basis van leeftijd, locatie en naampatronen"""
        if not self.loaded:
            self.load_data()

        print("Zoeken naar ongebruikte bestanden...")

        # Patronen die wijzen op tijdelijke of backup bestanden
        backup_patterns = [r'temp', r'tmp', r'cache', r'backup', r'bak', r'old',
            r'copy.*of', r'\(\d+\)', r'_\d{8}', r'\d{4}-\d{2}-\d{2}']
        compiled_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in
                             backup_patterns]

        # Zoek ongebruikte bestanden
        unused_files = []
        # Gebruik dezelfde timezone-aware strategie als in find_old_files
        now = datetime.now()

        for file in self.files:
            if file.get('mimeType') == 'application/vnd.google-apps.folder':
                continue

            score = 0
            reasons = []
            path = "/"

            # 1. Check leeftijd
            if 'createdTime' in file:
                # Maak created_date ook naive door de timezone info weg te halen
                created_time = file['createdTime'].replace('Z', '')
                created_date = datetime.fromisoformat(created_time)
                age_days = (now - created_date).days

                # Verhoogde drempels voor leeftijd
                if age_days > 1095:  # 3 jaar
                    score += 2
                    reasons.append(f"Zeer oud ({age_days} dagen)")
                elif age_days > 730:  # 2 jaar
                    score += 1
                    reasons.append(f"Oud ({age_days} dagen)")

            # 2. Check mapdiepte
            if 'parents' in file and file['parents']:
                parent_id = file['parents'][0]
                path = self.get_folder_path(parent_id)
                depth = path.count('/')

                if depth > 7:  # Verhoogde drempel voor diepte
                    score += 1
                    reasons.append(f"Diep genest (niveau {depth})")

            # 3. Check op backup/temp patronen in naam
            for pattern in compiled_patterns:
                if pattern.search(file['name']):
                    score += 2
                    reasons.append(f"Backup/temp patroon")
                    break

            # Verhoogde score threshold
            if score >= 3:  # Was 2
                unused_files.append(
                    {'id': file['id'], 'name': file['name'], 'score': score,
                        'reasons': reasons,
                        'size': int(file.get('size', 0)) if 'size' in file else 0,
                        'path': path})

        self.unused_files = sorted(unused_files, key=lambda x: x['score'], reverse=True)

        # Schrijf naar CSV
        with open(UNUSED_FILES_OUTPUT, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['Bestandsnaam', 'Score', 'Redenen', 'Grootte', 'Pad'])

            for file in self.unused_files:
                writer.writerow(
                    [file['name'], file['score'], ' | '.join(file['reasons']),
                        self._bytes_to_readable(file['size']), file['path']])

        print(
            f"Gevonden: {len(self.unused_files)} potentieel ongebruikte bestanden, opgeslagen in {UNUSED_FILES_OUTPUT}")

    def generate_reorganization_plan(self) -> None:
        """Genereer een reorganisatieplan op basis van de analyse"""
        if not hasattr(self, 'categories') or not self.categories:
            self.categorize_files()

        print("Reorganisatieplan genereren...")

        with open(REORG_PLAN_OUTPUT, 'w', encoding='utf-8') as f:
            f.write(
                f"Google Drive Reorganisatie Plan - Gegenereerd op {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            # 1. Hoofdstructuur
            f.write("## 1. VOORGESTELDE MAPSTRUCTUUR\n\n")
            f.write("```\n")
            f.write("Drive Root/\n")

            # Voorgestelde hoofdcategorieën
            main_categories = ['Documents', 'Photos', 'Videos', 'Spreadsheets',
                               'Presentations', 'Music', 'Archives', 'Code']
            for cat in main_categories:
                if cat in self.categories and len(self.categories[cat]) > 0:
                    file_count = len(self.categories[cat])
                    f.write(f"├── {cat}/ ({file_count} bestanden)\n")

                    # Suggesties voor submappen, afhankelijk van de categorie
                    if cat == "Photos":
                        f.write(
                            "│   ├── Persoonlijk/\n│   ├── Werk/\n│   └── Evenementen/\n")
                    elif cat == "Documents":
                        f.write(
                            "│   ├── Persoonlijk/\n│   ├── Werk/\n│   └── Archief/\n")
                    elif cat == "Videos":
                        f.write("│   ├── Persoonlijk/\n│   └── Werk/\n")

            # Overige categorie
            if "Other" in self.categories:
                f.write(f"└── Other/ ({len(self.categories['Other'])} bestanden)\n")

            f.write("```\n\n")

            # 2. Duplicaten aanpak
            f.write("## 2. DUPLICATEN OPRUIMEN\n\n")
            if self.exact_duplicates:
                f.write(
                    f"Er zijn {len(self.exact_duplicates)} sets exacte duplicaten gevonden.\n")
                f.write(
                    f"- Potentiële ruimtebesparing: {self._bytes_to_readable(sum(d['size'] * (d['count'] - 1) for d in self.exact_duplicates))}\n")
                f.write("- Zie exact_duplicates.csv voor details\n\n")

            # 3. Oude bestanden
            f.write("## 3. OUDE BESTANDEN BEOORDELEN\n\n")
            if hasattr(self, 'old_files') and self.old_files:
                f.write(
                    f"Er zijn {len(self.old_files)} bestanden ouder dan 1 jaar gevonden.\n")
                f.write("- Overweeg deze te archiveren of te verwijderen\n")
                f.write(f"- Zie {OLD_FILES_OUTPUT} voor details\n\n")
            else:
                f.write(
                    "Geen oude bestanden gedetecteerd of analyse is niet uitgevoerd.\n\n")

            # 4. Ongebruikte bestanden
            f.write("## 4. ONGEBRUIKTE BESTANDEN\n\n")
            if self.unused_files:
                f.write(
                    f"Er zijn {len(self.unused_files)} potentieel ongebruikte bestanden.\n")
                f.write(
                    "- Beoordeel deze bestanden om te bepalen of ze bewaard moeten worden\n")
                f.write("- Zie unused_files.csv voor details\n\n")

            # 5. Stapsgewijs plan
            f.write("## 5. STAPSGEWIJS OPRUIMPLAN\n\n")
            f.write("1. Begin met het verwijderen van duidelijke duplicaten\n")
            f.write("2. Creëer de hoofdcategorieën als ze nog niet bestaan\n")
            f.write("3. Verplaats bestanden systematisch naar de juiste categorieën\n")
            f.write(
                "4. Organiseer bestanden binnen categorieën in logische submappen\n")
            f.write(
                "5. Beoordeel oude en ongebruikte bestanden voor archivering of verwijdering\n")

        print(f"Reorganisatieplan opgeslagen in {REORG_PLAN_OUTPUT}")

    def categorize_files(self) -> None:
        """Categoriseer bestanden op basis van type, extensie en naam"""
        if not self.loaded:
            self.load_data()

        print("Bestanden categoriseren...")

        categories = defaultdict(list)

        for file in self.files:
            if file.get('mimeType') == 'application/vnd.google-apps.folder':
                continue

            file_name = file.get('name', '').lower()
            mime_type = file.get('mimeType', '').lower()

            # Bepaal categorie op basis van patronen
            categorized = False
            for category, patterns in self.category_patterns.items():
                for pattern in patterns:
                    if (re.search(pattern, file_name, re.IGNORECASE) or re.search(
                        pattern, mime_type, re.IGNORECASE)):
                        categories[category].append(file)
                        categorized = True
                        break
                if categorized:
                    break

            # Anders in 'Other' categorie
            if not categorized:
                categories['Other'].append(file)

        self.categories = {cat: files for cat, files in categories.items()}

        # Schrijf categorieën naar JSON
        category_stats = {cat: len(files) for cat, files in self.categories.items()}
        with open(CATEGORIES_OUTPUT, 'w', encoding='utf-8') as f:
            json.dump(category_stats, f, indent=2)

        print(f"Bestanden gecategoriseerd in {len(self.categories)} categorieën")
        for cat, files in self.categories.items():
            print(f"- {cat}: {len(files)} bestanden")

    def generate_statistics(self) -> None:
        """Genereer statistische informatie over de Drive inhoud"""
        if not self.loaded:
            self.load_data()

        print("Statistieken genereren...")

        # Bereken totale grootte
        total_size = sum(int(f.get('size', 0)) for f in self.files if 'size' in f)

        # Bereken diepte van mappenstructuur
        max_depth = 0
        for folder in self.folders:
            path = self.get_folder_path(folder['id'])
            depth = path.count('/')
            max_depth = max(max_depth, depth)

        # Vind mappen met de meeste directe kinderen
        folder_children_count = {folder_id: len(
            [f for f in self.children_map[folder_id] if
             f.get('mimeType') != 'application/vnd.google-apps.folder']) for folder_id
            in self.folder_map}

        crowded_folders = sorted(
            [(self.folder_map[fid]['name'], count, fid) for fid, count in
             folder_children_count.items()], key=lambda x: x[1], reverse=True)[:20]

        # Verzamel categoriegegevens indien beschikbaar
        category_stats = {}
        if hasattr(self, 'categories') and self.categories:
            category_stats = {cat: len(files) for cat, files in self.categories.items()}

        # Sla statistieken op
        stats = {'total_files': len(self.files) - len(self.folders),
            'total_folders': len(self.folders), 'total_size_bytes': total_size,
            'total_size_readable': self._bytes_to_readable(total_size),
            'max_folder_depth': max_depth, 'root_folders_count': len(self.root_folders),
            'orphan_folders_count': len(self.orphan_folders),
            'file_types': self.file_types, 'categories': category_stats,
            'duplicate_count': len(self.potential_duplicates),
            'exact_duplicate_count': len(self.exact_duplicates),
            'old_files_count': len(self.old_files),
            'unused_files_count': len(self.unused_files),
            'crowded_folders': [{'name': name, 'files_count': count, 'id': fid} for
                                name, count, fid in crowded_folders], 'largest_files': [
                {'name': f['name'], 'size_bytes': f.get('size', 0),
                 'size_readable': self._bytes_to_readable(int(f.get('size', 0))),
                 'id': f['id']} for f in self.largest_files[:20]]}

        with open(STATS_OUTPUT, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2)

        print(f"Statistieken opgeslagen in {STATS_OUTPUT}")

        # Korte samenvatting
        print("\nSamenvatting statistieken:")
        print(f"- Totaal bestanden: {stats['total_files']}")
        print(f"- Totaal mappen: {stats['total_folders']}")
        print(f"- Totale grootte: {stats['total_size_readable']}")
        print(f"- Maximale mapdiepte: {stats['max_folder_depth']}")

    def generate_suggestions(self) -> None:
        """Genereer suggesties voor verbetering van de Drive structuur"""
        if not self.loaded:
            self.load_data()

        print("Verbeteringsuggesties genereren...")

        suggestions = []

        # 1. Te veel root mappen?
        if len(self.root_folders) > 10:
            suggestions.append(
                f"Je hebt {len(self.root_folders)} root mappen. Overweeg deze te groeperen in "
                "categorieën zoals 'Werk', 'Persoonlijk', 'Projecten', etc.")

        # 2. Lege mappen
        empty_folders = []
        for folder_id, folder in self.folder_map.items():
            if folder_id not in self.children_map or not self.children_map[folder_id]:
                empty_folders.append(folder)

        if empty_folders:
            suggestions.append(
                f"Er zijn {len(empty_folders)} lege mappen. Overweeg deze te verwijderen of te "
                "gebruiken voor organisatie van losse bestanden.")

        # 3. Overbevolkte mappen
        crowded_threshold = 100
        crowded_folders = []

        for folder_id, items in self.children_map.items():
            if folder_id in self.folder_map:
                files = [i for i in items if
                         i.get('mimeType') != 'application/vnd.google-apps.folder']
                if len(files) > crowded_threshold:
                    folder = self.folder_map[folder_id]
                    crowded_folders.append((folder, len(files)))

        if crowded_folders:
            suggestions.append(
                f"Er zijn {len(crowded_folders)} mappen met meer dan {crowded_threshold} directe bestanden. "
                "Overweeg deze bestanden in submappen te organiseren voor betere structuur.")
            for folder, count in sorted(crowded_folders, key=lambda x: x[1],
                                        reverse=True)[:5]:
                suggestions.append(f"  - '{folder['name']}' bevat {count} bestanden")

        # 4. Duplicaten
        if self.potential_duplicates:
            dupe_count = sum(d['count'] for d in self.potential_duplicates)
            suggestions.append(
                f"Er zijn {len(self.potential_duplicates)} unieke bestandsnamen met potentiële duplicaten "
                f"({dupe_count} bestanden totaal). Zie {DUPLICATE_OUTPUT} voor details.")

        # 5. Exacte duplicaten
        if hasattr(self, 'exact_duplicates') and self.exact_duplicates:
            dupes_size = sum(
                d['size'] * (d['count'] - 1) for d in self.exact_duplicates)
            suggestions.append(
                f"Er zijn {len(self.exact_duplicates)} sets exacte duplicaten gevonden. "
                f"Verwijderen bespaart {self._bytes_to_readable(dupes_size)}. "
                f"Zie {EXACT_DUPES_OUTPUT} voor details.")

        # 6. Oude bestanden
        if hasattr(self, 'old_files') and self.old_files:
            suggestions.append(
                f"Er zijn {len(self.old_files)} bestanden ouder dan 1 jaar gevonden. "
                f"Overweeg deze te archiveren of te verwijderen. "
                f"Zie {OLD_FILES_OUTPUT} voor details.")

        # 7. Inconsistente naamgeving
        folder_names = [f['name'] for f in self.folders]
        prefixes = defaultdict(int)
        for name in folder_names:
            parts = name.split()
            if parts:
                prefixes[parts[0]] += 1

        common_prefixes = {prefix: count for prefix, count in prefixes.items() if
                           count > 3 and prefix.lower() not in ['the', 'a', 'de', 'het',
                                                                'een']}

        if common_prefixes:
            suggestions.append(
                "Er zijn mapnamen met gemeenschappelijke voorvoegsels. Overweeg naming conventions "
                "te standaardiseren voor betere organisatie:")
            for prefix, count in sorted(common_prefixes.items(), key=lambda x: x[1],
                                        reverse=True)[:5]:
                suggestions.append(f"  - '{prefix}' komt voor in {count} mapnamen")

        # Schrijf suggesties
        with open(SUGGESTIONS_OUTPUT, 'w', encoding='utf-8') as f:
            f.write(
                f"Google Drive Verbeteringsuggesties - Gegenereerd op {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            if suggestions:
                for i, suggestion in enumerate(suggestions, 1):
                    f.write(f"{i}. {suggestion}\n\n")
            else:
                f.write(
                    "Geen specifieke suggesties gevonden voor verbetering van de Drive structuur.\n")

        print(f"Verbeteringsuggesties opgeslagen in {SUGGESTIONS_OUTPUT}")

    def create_visualization(self) -> None:
        """Maak een HTML-visualisatie van de mapstructuur"""
        if not self.loaded:
            self.load_data()

        print("HTML-visualisatie genereren...")

        # Bereken max_depth correct
        max_depth = 0
        for folder in self.folders:
            path = self.get_folder_path(folder['id'])
            depth = path.count('/')
            max_depth = max(max_depth, depth)

        # Statistieken voor visualisatie
        stats = {'total_files': len(self.files) - len(self.folders),
                 'total_folders': len(self.folders),
                 'total_size': self._bytes_to_readable(
                     sum(int(f.get('size', 0)) for f in self.files if 'size' in f)),
                 'max_depth': max_depth  # Correcte waarde gebruiken
                 }

        # HTML template (verkort voor leesbaarheid)
        html_template = """<!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Google Drive Folder Structure</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .tree ul { list-style-type: none; }
                .tree li { margin: 5px 0; }
                .caret { cursor: pointer; user-select: none; }
                .caret::before { content: "▶"; color: black; display: inline-block; margin-right: 6px; }
                .caret-down::before { content: "▼"; }
                .nested { display: none; }
                .active { display: block; }
                .folder { color: #5475ca; }
                .file { color: #333; }
                .stats { background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-bottom: 20px; }
                h1, h2 { color: #333; }
                .search { margin: 10px 0; padding: 5px; width: 300px; }
                .filter-buttons { margin: 10px 0; }
                button { margin-right: 5px; padding: 5px 10px; }
            </style>
        </head>
        <body>
            <h1>Google Drive Mapstructuur Visualisatie</h1>

            <div class="stats">
                <h2>Statistieken</h2>
                <p>Totaal aantal bestanden: {{total_files}}</p>
                <p>Totaal aantal mappen: {{total_folders}}</p>
                <p>Totale grootte: {{total_size}}</p>
                <p>Maximale mapdiepte: {{max_depth}}</p>
            </div>

            <input type="text" class="search" placeholder="Zoeken in mappen en bestanden..." id="searchInput">

            <div class="filter-buttons">
                <button onclick="expandAll()">Alles uitklappen</button>
                <button onclick="collapseAll()">Alles inklappen</button>
            </div>

            <div class="tree">
                {{folder_tree}}
            </div>

            <script>
                // JavaScript functies voor uitklappen, zoeken, etc. hier
                document.addEventListener('DOMContentLoaded', function() {
                    var toggler = document.getElementsByClassName("caret");
                    for (var i = 0; i < toggler.length; i++) {
                        toggler[i].addEventListener("click", function() {
                            this.parentElement.querySelector(".nested").classList.toggle("active");
                            this.classList.toggle("caret-down");
                        });
                    }

                    document.getElementById('searchInput').addEventListener('input', function() {
                        var filter = this.value.toLowerCase();
                        search(filter);
                    });
                });

                function search(filter) {
                    var elements = document.querySelectorAll('.tree li');
                    if (filter === '') {
                        for (var i = 0; i < elements.length; i++) {
                            elements[i].style.display = '';
                        }
                        return;
                    }

                    for (var i = 0; i < elements.length; i++) {
                        elements[i].style.display = 'none';
                    }

                    var matches = document.querySelectorAll('.tree li[data-name*="' + filter + '"]');
                    for (var i = 0; i < matches.length; i++) {
                        showParents(matches[i]);
                        showContent(matches[i]);
                    }
                }

                function showParents(element) {
                    var parent = element;
                    while (parent) {
                        parent.style.display = '';
                        if (parent.querySelector('.nested')) {
                            parent.querySelector('.nested').classList.add('active');
                        }
                        if (parent.querySelector('.caret')) {
                            parent.querySelector('.caret').classList.add('caret-down');
                        }
                        parent = parent.parentElement.closest('li');
                    }
                }

                function showContent(element) {
                    element.style.display = '';
                    var nested = element.querySelector('.nested');
                    if (nested) {
                        nested.classList.add('active');
                        var children = nested.querySelectorAll('li');
                        for (var i = 0; i < children.length; i++) {
                            children[i].style.display = '';
                        }
                    }
                }

                function expandAll() {
                    var nested = document.querySelectorAll('.nested');
                    var carets = document.querySelectorAll('.caret');
                    for (var i = 0; i < nested.length; i++) {
                        nested[i].classList.add('active');
                    }
                    for (var i = 0; i < carets.length; i++) {
                        carets[i].classList.add('caret-down');
                    }
                }

                function collapseAll() {
                    var nested = document.querySelectorAll('.nested');
                    var carets = document.querySelectorAll('.caret');
                    for (var i = 0; i < nested.length; i++) {
                        nested[i].classList.remove('active');
                    }
                    for (var i = 0; i < carets.length; i++) {
                        carets[i].classList.remove('caret-down');
                    }
                }
            </script>
        </body>
        </html>"""

        # Recursieve functie om mappenstructuur als HTML te genereren
        def generate_folder_html(folder_id):
            if folder_id not in self.folder_map:
                return ""

            folder = self.folder_map[folder_id]
            folder_name = folder['name']

            # Kinderen ophalen en sorteren
            children = self.children_map[folder_id]
            subfolders = [c for c in children if
                          c.get('mimeType') == 'application/vnd.google-apps.folder']
            files = [c for c in children if
                     c.get('mimeType') != 'application/vnd.google-apps.folder']

            # Sorteren op naam
            subfolders.sort(key=lambda x: x['name'].lower())
            files.sort(key=lambda x: x['name'].lower())

            html = f'<li data-name="{folder_name.lower()}"><span class="caret folder">{folder_name}</span>'

            if subfolders or files:
                html += '<ul class="nested">'

                # Mappen eerst
                for subfolder in subfolders:
                    html += generate_folder_html(subfolder['id'])

                # Dan bestanden
                for file in files:
                    file_size = self._bytes_to_readable(
                        int(file.get('size', 0))) if 'size' in file else "?"
                    file_type = file.get('mimeType', 'unknown').split('/')[-1]
                    html += f'<li data-name="{file["name"].lower()}"><span class="file">{file["name"]} ({file_size}, {file_type})</span></li>'

                html += '</ul>'

            html += '</li>'
            return html

        # Genereer de mappenstructuur voor root mappen
        folder_tree_html = '<ul>'
        for folder in sorted(self.root_folders, key=lambda x: x['name'].lower()):
            folder_tree_html += generate_folder_html(folder['id'])
        folder_tree_html += '</ul>'

        # Vervang placeholders in template
        html_content = html_template.replace('{{folder_tree}}', folder_tree_html)
        html_content = html_content.replace('{{total_files}}',
                                            str(stats['total_files']))
        html_content = html_content.replace('{{total_folders}}',
                                            str(stats['total_folders']))
        html_content = html_content.replace('{{total_size}}', stats['total_size'])
        html_content = html_content.replace('{{max_depth}}', str(stats['max_depth']))

        # Schrijf HTML-bestand
        with open(VISUALIZATION_OUTPUT, 'w', encoding='utf-8') as f:
            f.write(html_content)

        print(f"HTML-visualisatie opgeslagen in {VISUALIZATION_OUTPUT}")

    def _bytes_to_readable(self, bytes_value: int) -> str:
        """Converteer bytes naar leesbare grootte (KB, MB, GB)"""
        sizes = ['B', 'KB', 'MB', 'GB', 'TB']
        if bytes_value == 0:
            return "0 B"
        i = 0
        while bytes_value >= 1024 and i < len(sizes) - 1:
            bytes_value /= 1024
            i += 1
        return f"{bytes_value:.2f} {sizes[i]}"

    def analyze_all(self) -> None:
        """Voer alle analyses uit en genereer alle outputs"""
        self.load_data()
        self.analyze_structure()
        self.find_potential_duplicates()
        self.find_exact_duplicates()
        self.categorize_files()
        self.find_old_files()
        self.find_unused_files()
        self.generate_statistics()
        self.generate_suggestions()
        self.generate_reorganization_plan()
        self.create_visualization()

        print("\nAnalyse voltooid! De volgende bestanden zijn gegenereerd:")
        print(f"1. Mapstructuur: {STRUCTURE_OUTPUT}")
        print(f"2. Statistieken: {STATS_OUTPUT}")
        print(f"3. Categorieën: {CATEGORIES_OUTPUT}")
        print(f"4. Potentiële duplicaten: {DUPLICATE_OUTPUT}")
        print(f"5. Exacte duplicaten: {EXACT_DUPES_OUTPUT}")
        print(f"6. Oude bestanden: {OLD_FILES_OUTPUT}")
        print(f"7. Ongebruikte bestanden: {UNUSED_FILES_OUTPUT}")
        print(f"8. Verbeteringsuggesties: {SUGGESTIONS_OUTPUT}")
        print(f"9. Reorganisatieplan: {REORG_PLAN_OUTPUT}")
        print(f"10. HTML-visualisatie: {VISUALIZATION_OUTPUT}")


def main():
    analyzer = DriveAnalyzer(INPUT_FILE)
    analyzer.analyze_all()


if __name__ == "__main__":
    main()