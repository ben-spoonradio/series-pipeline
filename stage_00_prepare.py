#!/usr/bin/env python3
"""
Stage 0: File Conversion and Metadata Matching
Prepare source file for processing by converting to text and matching series metadata
"""

import sys
import json
from pathlib import Path
from typing import Optional
from tqdm import tqdm

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from config import Config, get_output_dir, get_source_dir
from processors.file_converter import FileConverter
from processors.series_metadata_matcher import SeriesMetadataMatcher


def detect_source_language(text: str) -> str:
    """
    Detect the source language of text using Unicode character analysis.

    Args:
        text: Text to analyze

    Returns:
        'korean' or 'japanese'
    """
    if not text:
        return 'korean'  # Default

    # Sample first 2000 chars for efficiency
    sample = text[:2000]

    korean_count = 0
    japanese_count = 0

    for char in sample:
        code = ord(char)
        # Korean Hangul (AC00-D7AF: Syllables, 1100-11FF: Jamo)
        if (0xAC00 <= code <= 0xD7AF) or (0x1100 <= code <= 0x11FF):
            korean_count += 1
        # Japanese Hiragana (3040-309F) and Katakana (30A0-30FF)
        elif (0x3040 <= code <= 0x309F) or (0x30A0 <= code <= 0x30FF):
            japanese_count += 1

    if japanese_count > korean_count:
        return 'japanese'
    else:
        return 'korean'


def run_stage_0(
    file_path: Path,
    output_base: Path = None,
    source_lang: Optional[str] = None
):
    """
    Run Stage 0: File Conversion and Metadata Matching

    Args:
        file_path: Path to source file (DOCX/PDF/TXT)
        output_base: Base directory for output (default: from config.py)
        source_lang: Source language ('korean', 'japanese', or 'auto' for auto-detect)

    Returns:
        tuple: (series_folder, converted_text, series_metadata)
    """
    # Use config default if not specified
    if output_base is None:
        output_base = get_output_dir()
    print(f"\n{'='*80}")
    print(f"  Stage 0: File Conversion and Metadata Matching")
    print(f"{'='*80}\n")

    # Step 1: Match series metadata
    print("📊 Step 1: Matching series metadata...")
    series_name = file_path.stem
    matcher = SeriesMetadataMatcher()

    match_result = matcher.match(series_name)

    if not match_result['matched']:
        print(f"⚠️  No metadata match found for: {series_name}")
        print(f"   Creating series folder with default settings")
        series_metadata = {
            'series_name': match_result['series_name'],
            'publisher': match_result.get('publisher') or 'Unknown',
            'original_title': series_name,
            'default_voice_id': None,
            'default_voice_id_jp': None
        }
    else:
        series_metadata = match_result
        print(f"✅ Metadata Matching 완료 ({series_metadata['series_name']}, score: {series_metadata['match_score']:.2f})")

    # Derive output paths by finding _SOURCE in path and extracting structure
    # Structure: _SOURCE/KR/Peex/[시리즈폴더/]file.docx
    # Expected: parts = (KR, Peex, ...) where KR=language, Peex=publisher
    source_dir = get_source_dir()

    # Resolve both paths to handle symlinks and normalize
    # Use NFC normalization to handle macOS NFD vs NFC unicode differences
    import unicodedata
    file_path_resolved = Path(unicodedata.normalize('NFC', str(file_path.resolve())))
    source_dir_resolved = Path(unicodedata.normalize('NFC', str(source_dir.resolve())))

    try:
        parts = file_path_resolved.relative_to(source_dir_resolved).parts
        # parts = (KR, Peex, [시리즈폴더,] file.docx)
        language_code = parts[0] if len(parts) > 0 else 'Unknown'
        publisher = parts[1] if len(parts) > 1 else series_metadata.get('publisher', 'Unknown')
    except ValueError:
        # File is not under source_dir, use fallback
        language_code = 'Unknown'
        publisher = series_metadata.get('publisher', 'Unknown')

    series_folder = output_base / language_code / publisher / series_metadata['series_name']

    # Store language_code and publisher in metadata for later use
    series_metadata['language_code'] = language_code
    series_metadata['publisher'] = publisher

    # Create series folder and subfolders
    series_folder.mkdir(parents=True, exist_ok=True)

    # Create music folder for background music files
    music_folder = series_folder / 'music'
    music_folder.mkdir(parents=True, exist_ok=True)

    # Save metadata
    metadata_file = series_folder / 'series_metadata.json'
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(series_metadata, f, ensure_ascii=False, indent=2)

    print(f"   Country: {language_code}")
    print(f"   Publisher: {publisher}")
    print(f"   Series: {series_metadata['series_name']}")
    print(f"   Output: {series_folder}")
    print()

    # Step 2: Convert file to text
    print("📄 Step 2: Converting file to text...")
    converter = FileConverter()

    try:
        with tqdm(total=100, desc="   Converting", bar_format='{desc}: {percentage:3.0f}%|{bar}| [{elapsed}<{remaining}]') as pbar:
            pbar.update(30)
            convert_result = converter.execute({
                'file_path': str(file_path),
                'language': 'korean'
            })
            pbar.update(40)
            text = convert_result['output']
            pbar.update(30)
    except Exception as e:
        raise Exception(f"File conversion failed: {e}")
    file_size = len(text.encode('utf-8'))

    print(f"✅ File Conversion 완료 ({file_size:,} bytes)")
    print(f"   Characters: {len(text):,}")
    print(f"   Format: {file_path.suffix}")
    print()

    # Step 3: Detect source language
    print("🌐 Step 3: Detecting source language...")
    if source_lang and source_lang.lower() in ('korean', 'japanese'):
        detected_language = source_lang.lower()
        print(f"   Using specified language: {detected_language}")
    else:
        detected_language = detect_source_language(text)
        print(f"   Auto-detected language: {detected_language}")

    # Update metadata with source language
    series_metadata['source_language'] = detected_language
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(series_metadata, f, ensure_ascii=False, indent=2)
    print(f"✅ Source language saved: {detected_language}")
    print()

    # Summary
    print(f"{'='*80}")
    print(f"  Stage 0 Complete")
    print(f"{'='*80}\n")
    print(f"✅ Metadata matched and saved")
    print(f"✅ File converted to text")
    print(f"✅ Source language: {detected_language}")
    print(f"📂 Output folder: {series_folder}")
    print(f"📊 Metadata: {metadata_file}")
    print()

    return series_folder, text, series_metadata


if __name__ == '__main__':
    import argparse
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(
        description='Stage 0: File Conversion and Metadata Matching',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Examples:
  python stage_00_prepare.py "origin/KR/Peex/버추얼 러브 수정본.docx"
  python stage_00_prepare.py "origin/JP/Publisher/作品名.docx" --source-lang japanese
  python stage_00_prepare.py "origin/KR/Peex/작품.docx" --output-dir ./custom_output

Configuration:
  Default paths can be set via environment variables or .env file:
    SERIES_SOURCE_DIR: Source folder (default: {Config.SOURCE_DIR})
    SERIES_OUTPUT_DIR: Output folder (default: {Config.OUTPUT_DIR})

This stage:
  1. Matches series metadata from CSV
  2. Converts source file to text
  3. Detects source language (korean/japanese)
  4. Creates series folder structure
  5. Saves metadata and converted text
        """
    )
    parser.add_argument('source_file', nargs='?', help='Path to source file (DOCX/PDF/TXT)')
    parser.add_argument(
        '--source-lang',
        choices=['korean', 'japanese', 'auto'],
        default='auto',
        help='Source language (default: auto-detect)'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=None,
        help=f'Output directory (default: {Config.OUTPUT_DIR})'
    )
    parser.add_argument(
        '--show-config',
        action='store_true',
        help='Show current configuration and exit'
    )

    args = parser.parse_args()

    if args.show_config:
        Config.print_config()
        sys.exit(0)

    if not args.source_file:
        parser.print_help()
        sys.exit(1)

    file_path = Path(args.source_file)

    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        sys.exit(1)

    # Convert 'auto' to None for auto-detection
    source_lang = None if args.source_lang == 'auto' else args.source_lang
    output_base = args.output_dir if args.output_dir else get_output_dir()

    try:
        series_folder, text, metadata = run_stage_0(
            file_path,
            output_base=output_base,
            source_lang=source_lang
        )
        print(f"\n🎉 Ready for Stage 1: Episode Splitting")
        print(f"   Next: python stage_01_split.py \"{file_path}\"")
        print()
    except Exception as e:
        print(f"\n❌ Stage 0 failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
