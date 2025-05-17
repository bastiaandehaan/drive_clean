import json
from pathlib import Path
import os
from collections import defaultdict
from datetime import datetime
import csv
from typing import Dict, List, Set, Tuple, Optional, Any

# Configuratie
INPUT_FILE = Path("output/drive_index.json")
OUTPUT_DIR = Path("output")
FOLDERS_OUTPUT = OUTPUT_DIR / "drive_folders.json"
STRUCTURE_OUTPUT = OUTPUT_DIR / "drive_structure.txt"
STATS_OUTPUT = OUTPUT_DIR / "drive_stats.json"
DUPLICATE_OUTPUT = OUTPUT_DIR / "potential_duplicates.csv"
SUGGESTIONS_OUTPUT = OUTPUT_DIR / "improvement_suggestions.txt"
VISUALIZATION_OUTPUT = OUTPUT_DIR / "folder_tree.html"

# Maak output directory als deze niet bestaat
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
        self.loaded = False

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
                elif not any(
                        parent in self.folder_map for parent in folder.get('parents', [])):
                    self.orphan_folders.append(folder)

            # Categoriseer bestandstypes
            for file in self.files:
                if file.get('mimeType') != 'application/vnd.google-apps.folder':
                    self.file_types[file.get('mimeType', 'unknown')] += 1

            # Sorteer grootste bestanden
            non_folders = [f for f in self.files if f.get(
                'mimeType') != 'application/vnd.google-apps.folder' and 'size' in f]
            # Converteer size naar int als het bestaat
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

        # Neem de eerste parent (Drive kan meerdere parents hebben, maar we focussen op de eerste)
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

                # Print alleen mappen (folders) als children, niet alle bestanden
                children = [item for item in self.children_map[folder_id] if item.get(
                    'mimeType') == 'application/vnd.google-apps.folder']

                for child in sorted(children, key=lambda x: x['name']):
                    print_folder_tree(child['id'], depth + 1, file)

            # Print root folders
            f.write("Root mappen:\n")
            for folder in sorted(self.root_folders, key=lambda x: x['name']):
                print_folder_tree(folder['id'])

            # Print orphan folders als die er zijn
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

                # Bewaar voor later gebruik
                self.potential_duplicates.append(
                    {'name': name, 'count': len(files), 'files': files})

        print(
            f"Gevonden: {len(duplicates)} potentiële duplicaten, opgeslagen in {DUPLICATE_OUTPUT}")

    def generate_statistics(self) -> None:
        """Genereer statistische informatie over de Drive inhoud"""
        if not self.loaded:
            self.load_data()

        print("Statistieken genereren...")

        # Bereken totale grootte
        total_size = sum(int(f.get('size', 0)) for f in self.files if 'size' in f)

        # Bereken diepte van mappenstructuur
        max_depth = 0
        paths = []

        for folder in self.folders:
            path = self.get_folder_path(folder['id'])
            paths.append(path)
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

        # Sla statistieken op
        stats = {'total_files': len(self.files) - len(self.folders),
            'total_folders': len(self.folders), 'total_size_bytes': total_size,
            'total_size_readable': self._bytes_to_readable(total_size),
            'max_folder_depth': max_depth, 'root_folders_count': len(self.root_folders),
            'orphan_folders_count': len(self.orphan_folders),
            'file_types': self.file_types,
            'crowded_folders': [{'name': name, 'files_count': count, 'id': fid} for
                                name, count, fid in crowded_folders], 'largest_files': [
                {'name': f['name'], 'size_bytes': f.get('size', 0),
                 'size_readable': self._bytes_to_readable(int(f.get('size', 0))),
                 'id': f['id']} for f in self.largest_files[:20]]}

        with open(STATS_OUTPUT, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2)

        print(f"Statistieken opgeslagen in {STATS_OUTPUT}")

        # Geef een korte samenvatting
        print("\nSamenvatting statistieken:")
        print(f"- Totaal aantal bestanden: {stats['total_files']}")
        print(f"- Totaal aantal mappen: {stats['total_folders']}")
        print(f"- Totale grootte: {stats['total_size_readable']}")
        print(f"- Maximale mapdiepte: {stats['max_folder_depth']}")
        print(f"- Aantal root mappen: {stats['root_folders_count']}")
        if stats['orphan_folders_count'] > 0:
            print(f"- Wezen mappen: {stats['orphan_folders_count']}")

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

        # 3. Overbevolkte mappen (te veel directe bestanden)
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

        # 5. Inconsistente naamgeving
        # Vind prefixen en suffixen in mapnamen voor consistentie-check
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

        # Print een aantal suggesties
        if suggestions:
            print("\nTop suggesties voor verbetering:")
            for suggestion in suggestions[:3]:
                print(f"- {suggestion}")
            print(f"Zie {SUGGESTIONS_OUTPUT} voor alle suggesties.")

    def create_visualization(self) -> None:
        """Maak een HTML-visualisatie van de mapstructuur"""
        if not self.loaded:
            self.load_data()

        print("HTML-visualisatie genereren...")

        # Eenvoudige HTML template voor een opvouwbare mapstructuur
        html_template = """
        <!DOCTYPE html>
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
                document.addEventListener('DOMContentLoaded', function() {
                    var toggler = document.getElementsByClassName("caret");
                    for (var i = 0; i < toggler.length; i++) {
                        toggler[i].addEventListener("click", function() {
                            this.parentElement.querySelector(".nested").classList.toggle("active");
                            this.classList.toggle("caret-down");
                        });
                    }

                    // Zoekfunctionaliteit
                    document.getElementById('searchInput').addEventListener('input', function() {
                        var filter = this.value.toLowerCase();
                        search(filter);
                    });
                });

                function search(filter) {
                    var elements = document.querySelectorAll('.tree li');

                    if (filter === '') {
                        // Als geen zoekterm, alles inzichtelijk maken
                        for (var i = 0; i < elements.length; i++) {
                            elements[i].style.display = '';
                        }
                        return;
                    }

                    // Verberg alles eerst
                    for (var i = 0; i < elements.length; i++) {
                        elements[i].style.display = 'none';
                    }

                    // Toon items die matchen met de zoekterm en hun ouders
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
        </html>
        """

        # Laad statistieken als die bestaan
        stats = {'total_files': len(self.files) - len(self.folders),
            'total_folders': len(self.folders), 'total_size': self._bytes_to_readable(
                sum(int(f.get('size', 0)) for f in self.files if 'size' in f)),
            'max_depth': 0  # Dit wordt later berekend
        }

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
        self.generate_statistics()
        self.generate_suggestions()
        self.create_visualization()

        print("\nAnalyse voltooid! De volgende bestanden zijn gegenereerd:")
        print(f"1. Mapstructuur: {STRUCTURE_OUTPUT}")
        print(f"2. Potentiële duplicaten: {DUPLICATE_OUTPUT}")
        print(f"3. Statistieken: {STATS_OUTPUT}")
        print(f"4. Verbeteringsuggesties: {SUGGESTIONS_OUTPUT}")
        print(f"5. HTML-visualisatie: {VISUALIZATION_OUTPUT}")
        print(
            "\nBekijk de HTML-visualisatie in je browser voor een interactief overzicht.")


def main():
    analyzer = DriveAnalyzer(INPUT_FILE)
    analyzer.analyze_all()


if __name__ == "__main__":
    main()