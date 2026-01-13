#!/usr/bin/env python3
"""
Fix Korean speaker tags in existing 03a_speaker_tagged and 04_tagged output files.
Translates Korean speaker names to target language using glossary.
Also separates mixed dialogue/narration lines.
"""

import sys
import json
import re
from pathlib import Path
from typing import Dict


def load_glossary(series_folder: Path, language: str) -> Dict:
    """Load glossary for a specific language."""
    glossary_map = {
        'japanese': 'glossary_japanese.json',
        'taiwanese': 'glossary_taiwanese.json'
    }

    glossary_file = glossary_map.get(language)
    if not glossary_file:
        return {'terms': []}

    glossary_path = series_folder / glossary_file
    if glossary_path.exists():
        try:
            with open(glossary_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"  ⚠️  Failed to load glossary: {e}")
    return {'terms': []}


def translate_speaker_tags_in_output(
    tagged_text: str,
    glossary: Dict,
    target_language: str
) -> str:
    """
    Post-process to translate Korean speaker names in tags.
    Uses glossary with fuzzy matching (handles spacing variations).
    Also handles compound names like "침입자 (남자)" or "침입자 (여자)".
    """
    if target_language == 'korean':
        return tagged_text

    # Build name map from glossary (including normalized versions)
    name_map = {}
    for term in glossary.get('terms', []):
        original = term.get('original', '')
        translation = term.get('translation', '')
        if original and translation:
            name_map[original] = translation
            # Also add normalized version (no spaces)
            normalized = original.replace(' ', '')
            if normalized != original:
                name_map[normalized] = translation

    if not name_map:
        return tagged_text

    # Pattern to find speaker tags with Korean names: [NAME(ROLE, GENDER)]:
    # Korean characters: 가-힣, also handle spaces, parentheses, and mixed CJK chars
    # Examples: [서연], [침입자 (남자)], [서 박사], [침入者 (남자)] (mixed Korean+Chinese)
    pattern = r'\[([가-힣][가-힣\u4e00-\u9fff\s\(\)（）]*)\(([A-Z_]+),\s*([A-Z]+)\)\]:'

    def extract_korean_base(name: str) -> str:
        """Extract Korean characters from a potentially mixed string."""
        korean_chars = ''.join(c for c in name if '\uac00' <= c <= '\ud7af')
        return korean_chars

    def find_partial_translation(mixed_name: str, name_map: dict) -> str:
        """
        Find translation for a partially-translated mixed string.
        e.g., "침入者" (Korean 침 + Chinese 入者) -> should match "침입자" -> "侵入者"
        """
        has_korean = any('\uac00' <= c <= '\ud7af' for c in mixed_name)
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in mixed_name)

        if not (has_korean and has_chinese):
            return None

        chinese_part = ''.join(c for c in mixed_name if '\u4e00' <= c <= '\u9fff')

        for original, translation in name_map.items():
            if chinese_part and chinese_part in translation:
                return translation

        return None

    # Gender suffix mapping for target languages
    gender_suffix_map = {
        'japanese': {'남자': '（男）', '여자': '（女）', 'MAN': '（男）', 'WOMAN': '（女）'},
        'taiwanese': {'남자': '（男）', '여자': '（女）', 'MAN': '（男）', 'WOMAN': '（女）'},
    }
    gender_suffixes = gender_suffix_map.get(target_language, {})

    def replace_korean_name(match):
        full_name = match.group(1).strip()
        role = match.group(2)
        gender = match.group(3)

        # Try exact match first
        if full_name in name_map:
            translated = name_map[full_name]
        # Try normalized (no spaces)
        elif full_name.replace(' ', '') in name_map:
            translated = name_map[full_name.replace(' ', '')]
        else:
            # Check for compound names like "침입자 (남자)" or "침入者 (남자)"
            # Extract base name and gender indicator
            compound_match = re.match(r'^(.+?)\s*[\(（](.+?)[\)）]$', full_name)
            if compound_match:
                base_name = compound_match.group(1).strip()
                gender_indicator = compound_match.group(2).strip()

                # Try to translate base name (exact or normalized)
                if base_name in name_map:
                    translated_base = name_map[base_name]
                elif base_name.replace(' ', '') in name_map:
                    translated_base = name_map[base_name.replace(' ', '')]
                else:
                    # Try finding partial translation for mixed strings (e.g., "침入者" -> "侵入者")
                    partial_trans = find_partial_translation(base_name, name_map)
                    if partial_trans:
                        translated_base = partial_trans
                    else:
                        # Try extracting Korean-only characters from mixed string
                        korean_only = extract_korean_base(base_name)
                        if korean_only and korean_only in name_map:
                            translated_base = name_map[korean_only]
                        elif korean_only and korean_only.replace(' ', '') in name_map:
                            translated_base = name_map[korean_only.replace(' ', '')]
                        else:
                            translated_base = base_name

                # Add translated gender suffix
                gender_suffix = gender_suffixes.get(gender_indicator, f'（{gender_indicator}）')
                translated = f'{translated_base}{gender_suffix}'
            else:
                # Try finding partial translation for mixed strings
                partial_trans = find_partial_translation(full_name, name_map)
                if partial_trans:
                    translated = partial_trans
                else:
                    # Try extracting Korean-only characters from the full name
                    korean_only = extract_korean_base(full_name)
                    if korean_only and korean_only in name_map:
                        translated = name_map[korean_only]
                    elif korean_only and korean_only.replace(' ', '') in name_map:
                        translated = name_map[korean_only.replace(' ', '')]
                    else:
                        translated = full_name  # Keep original if no match

        return f'[{translated}({role}, {gender})]:'

    return re.sub(pattern, replace_korean_name, tagged_text)


def split_multiple_speakers_in_line(tagged_text: str) -> str:
    """
    Split lines that contain multiple speaker tags into separate lines.
    e.g., "[NARRATOR]: text [Speaker]: dialogue" -> "[NARRATOR]: text\n\n[Speaker]: dialogue"
    """
    # Pattern to match speaker tags: [NAME(ROLE, GENDER)]: or [NARRATOR]:
    speaker_pattern = r'\[([^\]]+)\]:'

    result_lines = []
    for line in tagged_text.split('\n'):
        stripped = line.strip()
        if not stripped:
            result_lines.append(line)
            continue

        # Find all speaker tags in the line
        matches = list(re.finditer(speaker_pattern, stripped))

        if len(matches) <= 1:
            # Only one or no speaker tag, keep as is
            result_lines.append(line)
        else:
            # Multiple speaker tags found - split them
            for i, match in enumerate(matches):
                start_pos = match.start()

                if i == len(matches) - 1:
                    # Last speaker - take everything to the end
                    segment = stripped[start_pos:].strip()
                else:
                    # Not last - take until next speaker
                    next_start = matches[i + 1].start()
                    segment = stripped[start_pos:next_start].strip()

                if segment:
                    result_lines.append(segment)
                    # Add empty line for separation (except after last)
                    if i < len(matches) - 1:
                        result_lines.append('')

    return '\n'.join(result_lines)


def separate_dialogue_and_narration(tagged_text: str, language: str) -> str:
    """
    Separate dialogue and narration that are mixed in the same line.
    """
    # Quote patterns per language
    quote_patterns = {
        'japanese': r'「[^」]+」',
        'taiwanese': r'「[^」]+」',
        'korean': r'"[^"]+"'
    }

    quote_pattern = quote_patterns.get(language, r'"[^"]+"')

    result_lines = []
    for line in tagged_text.split('\n'):
        stripped = line.strip()
        if not stripped:
            result_lines.append(line)
            continue

        # Check if line has speaker tag (not NARRATOR)
        speaker_match = re.match(r'(\[[^\]]+\]:)\s*(.+)', stripped)
        if speaker_match and '[NARRATOR]' not in speaker_match.group(1):
            speaker_tag = speaker_match.group(1)
            content = speaker_match.group(2)

            # Find all quoted dialogue
            dialogues = re.findall(quote_pattern, content)

            if dialogues:
                # Extract text after last dialogue
                last_dialogue = dialogues[-1]
                last_idx = content.rfind(last_dialogue)
                after_dialogue = content[last_idx + len(last_dialogue):].strip()

                # Check if there's substantial narration after dialogue
                narration_check = re.sub(r'\[[^\]]+\]', '', after_dialogue).strip()
                narration_check = re.sub(r'[。、！？…\s]', '', narration_check)

                if len(narration_check) > 2:
                    dialogue_part = content[:last_idx + len(last_dialogue)].strip()
                    result_lines.append(f"{speaker_tag} {dialogue_part}")
                    result_lines.append('')
                    result_lines.append(f"[NARRATOR]: {after_dialogue}")
                    continue

        result_lines.append(line)

    return '\n'.join(result_lines)


def fix_episode_file(file_path: Path, glossary: Dict, language: str) -> bool:
    """Fix speaker tags in a single episode file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        original_content = data.get('content', '')

        # Apply fixes in order:
        # 1. Translate Korean speaker names to target language
        fixed_content = translate_speaker_tags_in_output(original_content, glossary, language)
        # 2. Split lines with multiple speakers into separate lines
        fixed_content = split_multiple_speakers_in_line(fixed_content)
        # 3. Separate dialogue and narration within single speaker lines
        fixed_content = separate_dialogue_and_narration(fixed_content, language)

        if fixed_content != original_content:
            data['content'] = fixed_content
            data['metadata']['speaker_tags_fixed'] = True

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            return True
        return False

    except Exception as e:
        print(f"  ❌ Error fixing {file_path.name}: {e}")
        return False


def fix_speaker_tags(series_folder: Path, stages: list = None, languages: list = None):
    """
    Fix Korean speaker tags in 03a and 04 output files.

    Args:
        series_folder: Path to series folder
        stages: List of stages to fix ('03a', '04') - default: both
        languages: List of languages to fix - default: japanese, taiwanese
    """
    if stages is None:
        stages = ['03a', '04']
    if languages is None:
        languages = ['japanese', 'taiwanese']

    stage_folders = {
        '03a': '03a_speaker_tagged',
        '04': '04_tagged'
    }

    print("=" * 60)
    print("  Fix Speaker Tags in Existing Files")
    print("=" * 60)
    print()
    print(f"📁 Series: {series_folder.name}")
    print(f"🔧 Stages: {', '.join(stages)}")
    print(f"🌏 Languages: {', '.join(languages)}")
    print()

    total_fixed = 0
    total_checked = 0

    for language in languages:
        print(f"\n{'='*50}")
        print(f"  Processing {language.upper()}")
        print(f"{'='*50}")

        # Load glossary for this language
        glossary = load_glossary(series_folder, language)
        term_count = len(glossary.get('terms', []))
        print(f"  📚 Glossary loaded: {term_count} terms")

        for stage in stages:
            folder_name = stage_folders.get(stage)
            if not folder_name:
                continue

            stage_folder = series_folder / folder_name / language

            if not stage_folder.exists():
                print(f"  ⚠️  Folder not found: {stage_folder}")
                continue

            episodes = sorted(stage_folder.glob('episode_*.json'))

            if not episodes:
                print(f"  ⚠️  No episodes in {folder_name}/{language}")
                continue

            print(f"\n  📂 {folder_name}/{language}: {len(episodes)} episodes")

            fixed_count = 0
            for ep_file in episodes:
                total_checked += 1
                if fix_episode_file(ep_file, glossary, language):
                    fixed_count += 1
                    total_fixed += 1
                    print(f"    ✅ Fixed: {ep_file.name}")

            if fixed_count == 0:
                print(f"    ℹ️  No changes needed")
            else:
                print(f"    📊 Fixed {fixed_count} files")

    print()
    print("=" * 60)
    print("  Summary")
    print("=" * 60)
    print(f"  Checked: {total_checked} files")
    print(f"  Fixed: {total_fixed} files")
    print()

    return total_fixed


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Fix Korean speaker tags in 03a/04 output files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python fix_speaker_tags.py "processed/Publisher/Series"
  python fix_speaker_tags.py "processed/Publisher/Series" --stages 03a
  python fix_speaker_tags.py "processed/Publisher/Series" --langs japanese
  python fix_speaker_tags.py "processed/Publisher/Series" --stages 03a 04 --langs japanese taiwanese
        """
    )
    parser.add_argument('series_folder', help='Path to series folder')
    parser.add_argument(
        '--stages',
        nargs='+',
        choices=['03a', '04'],
        default=['03a', '04'],
        help='Stages to fix (default: 03a 04)'
    )
    parser.add_argument(
        '--langs',
        nargs='+',
        choices=['japanese', 'taiwanese'],
        default=['japanese', 'taiwanese'],
        help='Languages to fix (default: japanese taiwanese)'
    )

    args = parser.parse_args()
    series_folder = Path(args.series_folder)

    if not series_folder.exists():
        print(f"❌ Series folder not found: {series_folder}")
        sys.exit(1)

    fixed = fix_speaker_tags(series_folder, stages=args.stages, languages=args.langs)
    print(f"✅ Done! Fixed {fixed} files.")
