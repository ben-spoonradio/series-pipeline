#!/usr/bin/env python3
"""
CSV to Glossary JSON Converter
Converts edited glossary CSV back to JSON format for translation pipeline.

Automatically syncs to both _REVIEW and _PROCESSED folders.
"""

import csv
import json
import sys
from pathlib import Path
from datetime import datetime


def find_processed_json_path(csv_path: Path) -> Path:
    """
    Find corresponding JSON path in _PROCESSED folder.

    CSV is in: _REVIEW/{lang}/{publisher}/{series}/glossary_{lang}.csv
    JSON is in: _PROCESSED/{lang}/{publisher}/{series}/glossary_{lang}.json

    Args:
        csv_path: Path to CSV file in _REVIEW folder

    Returns:
        Path to JSON file in _PROCESSED folder, or None if not determinable
    """
    csv_str = str(csv_path)

    # Check if CSV is in _REVIEW folder
    if '_REVIEW' in csv_str:
        processed_path = csv_str.replace('_REVIEW', '_PROCESSED')
        return Path(processed_path).with_suffix('.json')

    return None


def csv_to_glossary(csv_path: Path) -> bool:
    """
    Convert glossary CSV to JSON format.

    Automatically syncs to both:
    1. Same folder as CSV (for _REVIEW)
    2. Corresponding _PROCESSED folder (for translation pipeline)

    Args:
        csv_path: Path to CSV file (e.g., glossary_taiwanese.csv)

    Returns:
        True if successful, False otherwise
    """
    if not csv_path.exists():
        print(f"❌ CSV file not found: {csv_path}")
        return False

    # Determine output JSON paths
    # 1. Same folder as CSV
    json_path_review = csv_path.with_suffix('.json')

    # 2. Corresponding _PROCESSED folder
    json_path_processed = find_processed_json_path(csv_path)

    # Load existing JSON to preserve metadata (prefer _PROCESSED version)
    existing_metadata = {}
    metadata_source = json_path_processed if json_path_processed and json_path_processed.exists() else json_path_review
    if metadata_source and metadata_source.exists():
        try:
            with open(metadata_source, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                existing_metadata = {
                    'series_name': existing_data.get('series_name', ''),
                    'source_language': existing_data.get('source_language', ''),
                    'target_language': existing_data.get('target_language', ''),
                    'created_date': existing_data.get('created_date', ''),
                }
        except Exception as e:
            print(f"⚠️  Could not load existing JSON: {e}")

    # Read CSV
    terms = []
    current_category = None

    try:
        with open(csv_path, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)

            for row in reader:
                # Skip empty rows (category separators)
                if not row.get('Original') and not row.get('Translation'):
                    continue

                category = row.get('Category', '').strip()
                original = row.get('Original', '').strip()
                translation = row.get('Translation', '').strip()
                context = row.get('Context', '').strip()

                if not original or not translation:
                    continue

                terms.append({
                    'original': original,
                    'translation': translation,
                    'category': category.lower() if category else 'term',
                    'context': context,
                    'first_appearance': ''
                })

        print(f"📊 Loaded {len(terms)} terms from CSV")

    except Exception as e:
        print(f"❌ Error reading CSV: {e}")
        return False

    # Create glossary JSON
    glossary_data = {
        'series_name': existing_metadata.get('series_name', ''),
        'source_language': existing_metadata.get('source_language', 'korean'),
        'target_language': existing_metadata.get('target_language', ''),
        'created_date': existing_metadata.get('created_date', datetime.now().isoformat()),
        'last_updated': datetime.now().isoformat(),
        'terms': terms
    }

    import shutil

    # Save to both locations
    saved_paths = []

    # 1. Save to _PROCESSED folder (primary - used by translation pipeline)
    if json_path_processed:
        try:
            # Backup existing
            if json_path_processed.exists():
                backup_path = json_path_processed.with_suffix('.json.bak')
                shutil.copy2(json_path_processed, backup_path)

            with open(json_path_processed, 'w', encoding='utf-8') as f:
                json.dump(glossary_data, f, ensure_ascii=False, indent=2)
            saved_paths.append(('_PROCESSED', json_path_processed))
        except Exception as e:
            print(f"⚠️  Could not save to _PROCESSED: {e}")

    # 2. Save to _REVIEW folder (for reference)
    try:
        # Backup existing
        if json_path_review.exists():
            backup_path = json_path_review.with_suffix('.json.bak')
            shutil.copy2(json_path_review, backup_path)

        with open(json_path_review, 'w', encoding='utf-8') as f:
            json.dump(glossary_data, f, ensure_ascii=False, indent=2)
        saved_paths.append(('_REVIEW', json_path_review))
    except Exception as e:
        print(f"⚠️  Could not save to _REVIEW: {e}")

    # Report results
    if saved_paths:
        print(f"✅ Saved glossary JSON ({len(terms)} terms):")
        for folder_name, path in saved_paths:
            print(f"   📝 {folder_name}: {path}")
        return True
    else:
        print(f"❌ Failed to save JSON to any location")
        return False


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python csv_to_glossary.py <csv_file>")
        print()
        print("Example:")
        print('  python csv_to_glossary.py "processed/Publisher/Series/glossary_taiwanese.csv"')
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    success = csv_to_glossary(csv_path)
    sys.exit(0 if success else 1)
