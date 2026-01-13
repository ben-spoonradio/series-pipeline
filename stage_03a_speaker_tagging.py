#!/usr/bin/env python3
"""
Stage 3a: Speaker Tagging
Add speaker tags to formatted text using character dictionary.

2-Phase Approach:
1. Extract characters from Korean source (全シリーズスキャン)
2. Apply speaker tags per language using glossary for name mapping
"""

import sys
import json
import time
from pathlib import Path
from typing import List, Optional, Dict
from tqdm import tqdm
from processors.llm_processor import LLMProcessor

# Target languages
TARGET_LANGUAGES = ['korean', 'japanese', 'taiwanese']

# Language display names
LANGUAGE_DISPLAY = {
    'korean': '🇰🇷 Korean',
    'japanese': '🇯🇵 Japanese',
    'taiwanese': '🇹🇼 Taiwanese'
}


def load_glossary(series_folder: Path, language: str) -> Dict:
    """
    Load glossary for a specific language.

    Args:
        series_folder: Path to series folder
        language: Target language

    Returns:
        Glossary dict with 'terms' list
    """
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


def map_character_names(characters: List[Dict], glossary: Dict, language: str) -> List[Dict]:
    """
    Map character names to target language using glossary.

    Args:
        characters: List of character dicts from extraction
        glossary: Glossary dict with 'terms' list
        language: Target language

    Returns:
        Characters with translated names added
    """
    if language == 'korean':
        # Korean is source language, no mapping needed
        for char in characters:
            char['name_display'] = char['name']
        return characters

    # Build lookup from glossary
    name_map = {}
    for term in glossary.get('terms', []):
        original = term.get('original', '')
        translation = term.get('translation', '')
        if original and translation:
            name_map[original] = translation

    # Map character names
    for char in characters:
        korean_name = char.get('name', '')
        if korean_name in name_map:
            char['name_display'] = name_map[korean_name]
        else:
            # Keep original name if no translation found
            char['name_display'] = korean_name

        # Also map aliases
        mapped_aliases = []
        for alias in char.get('aliases', []):
            if alias in name_map:
                mapped_aliases.append(name_map[alias])
            else:
                mapped_aliases.append(alias)
        char['aliases_display'] = mapped_aliases

    return characters


def parse_speaker_line(line: str) -> tuple:
    """
    Parse a line to extract speaker prefix and content.

    Args:
        line: A single line of tagged text

    Returns:
        Tuple of (speaker_prefix, content) or (None, line) if no speaker
    """
    import re

    # Pattern: [SPEAKER_NAME(ROLE, GENDER)]: or [SPEAKER_NAME]: or [NARRATOR]:
    # Also supports legacy format without brackets
    # Examples:
    #   [민수(PROTAGONIST, MAN)]: "안녕"
    #   [NARRATOR]: 서술문
    #   [UNKNOWN(UNKNOWN)]: 대사

    # New bracketed format: [SPEAKER(ROLE, GENDER)]:
    bracket_pattern = r'^\[([A-Z가-힣\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+(?:\([^)]+\))?)\]\s*:\s*(.*)$'
    match = re.match(bracket_pattern, line.strip())

    if match:
        return f"[{match.group(1)}]", match.group(2)

    # Legacy format without brackets: SPEAKER(ROLE, GENDER):
    legacy_pattern = r'^([A-Z가-힣\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+(?:\([^)]+\))?)\s*:\s*(.*)$'
    match = re.match(legacy_pattern, line.strip())

    if match:
        return match.group(1), match.group(2)
    return None, line


def insert_linebreaks_before_speaker_tags(tagged_text: str) -> str:
    """
    Rule-based function to insert line breaks before speaker tags.
    This ensures each speaker tag starts on a new line, regardless of LLM output format.

    Args:
        tagged_text: Text with speaker tags (may be on single line or multiple lines)

    Returns:
        Text with line breaks inserted before each speaker tag
    """
    import re

    # Simple and flexible pattern for bracketed speaker tags
    # Matches: [anything]: when preceded by non-newline, non-bracket character
    # Examples: [NARRATOR]:, [민수(PROTAGONIST, MAN)]:, [남자 침입자(MINOR, MAN)]:
    bracket_pattern = r'([^\n\[])(\[[^\]]+\]:)'

    # Insert double newline before each speaker tag (except at start)
    result = re.sub(bracket_pattern, r'\1\n\n\2', tagged_text)

    # Clean up: remove multiple consecutive newlines (more than 2)
    result = re.sub(r'\n{3,}', '\n\n', result)

    # Clean up: remove leading newlines
    result = result.lstrip('\n')

    return result


def translate_speaker_tags_in_output(
    tagged_text: str,
    glossary: Dict,
    target_language: str
) -> str:
    """
    Post-process LLM output to translate Korean speaker names in tags.
    Uses glossary with fuzzy matching (handles spacing variations).

    Args:
        tagged_text: Text with speaker tags (may contain Korean names)
        glossary: Glossary dict with 'terms' list
        target_language: Target language ('japanese', 'taiwanese', etc.)

    Returns:
        Text with Korean speaker names translated
    """
    import re

    if target_language == 'korean':
        return tagged_text  # No translation needed

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
    # Pattern matches: starts with Korean, may contain Korean/Chinese/spaces/parentheses
    pattern = r'\[([가-힣][가-힣\u4e00-\u9fff\s\(\)（）]*)\(([A-Z_]+),\s*([A-Z]+)\)\]:'

    # Gender suffix mapping for target languages
    gender_suffix_map = {
        'japanese': {'남자': '（男）', '여자': '（女）', 'MAN': '（男）', 'WOMAN': '（女）'},
        'taiwanese': {'남자': '（男）', '여자': '（女）', 'MAN': '（男）', 'WOMAN': '（女）'},
    }
    gender_suffixes = gender_suffix_map.get(target_language, {})

    def extract_korean_base(name: str) -> str:
        """Extract Korean characters from a potentially mixed string."""
        korean_chars = ''.join(c for c in name if '\uac00' <= c <= '\ud7af')
        return korean_chars

    def find_partial_translation(mixed_name: str, name_map: dict) -> str:
        """
        Find translation for a partially-translated mixed string.
        e.g., "침入者" (Korean 침 + Chinese 入者) -> should match "침입자" -> "侵入者"
        """
        # Check if mixed_name contains both Korean and Chinese characters
        has_korean = any('\uac00' <= c <= '\ud7af' for c in mixed_name)
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in mixed_name)

        if not (has_korean and has_chinese):
            return None

        # Try to find a glossary entry where the translation contains the Chinese part
        chinese_part = ''.join(c for c in mixed_name if '\u4e00' <= c <= '\u9fff')

        for original, translation in name_map.items():
            # Check if the translation contains the Chinese part from mixed_name
            if chinese_part and chinese_part in translation:
                return translation

        return None

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

    Args:
        tagged_text: Text with speaker tags

    Returns:
        Text with each speaker on a separate line
    """
    import re

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
    Dialogue in quotes stays with speaker, narration after quotes goes to NARRATOR.

    Args:
        tagged_text: Text with speaker tags
        language: Target language for quote pattern detection

    Returns:
        Text with dialogue and narration properly separated
    """
    import re

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
                # Remove emotion tags like [calm], [dramatic] for checking
                narration_check = re.sub(r'\[[^\]]+\]', '', after_dialogue).strip()
                # Remove punctuation for checking
                narration_check = re.sub(r'[。、！？…\s]', '', narration_check)

                if len(narration_check) > 2:  # Has actual narration text
                    # Keep dialogue with speaker (include everything up to and including last dialogue)
                    dialogue_part = content[:last_idx + len(last_dialogue)].strip()
                    result_lines.append(f"{speaker_tag} {dialogue_part}")
                    result_lines.append('')  # Empty line for separation
                    result_lines.append(f"[NARRATOR]: {after_dialogue}")
                    continue

        result_lines.append(line)

    return '\n'.join(result_lines)


def consolidate_consecutive_speakers(tagged_text: str) -> str:
    """
    Consolidate consecutive lines with the same speaker into a single block.
    Add line break when speaker changes for better readability.

    Args:
        tagged_text: Text with speaker tags

    Returns:
        Consolidated text with line breaks between different speakers
    """
    # First, ensure line breaks exist before speaker tags (rule-based)
    tagged_text = insert_linebreaks_before_speaker_tags(tagged_text)

    lines = tagged_text.split('\n')
    result = []
    current_speaker = None
    current_content = []
    previous_speaker = None  # Track previous speaker for line break logic

    for line in lines:
        stripped = line.strip()

        # Handle empty lines - flush current and add empty line
        if not stripped:
            if current_speaker and current_content:
                result.append(f"{current_speaker}: {' '.join(current_content)}")
                previous_speaker = current_speaker
                current_speaker = None
                current_content = []
            result.append('')
            continue

        speaker, content = parse_speaker_line(stripped)

        if speaker is None:
            # Line without speaker tag - could be continuation or plain text
            if current_speaker and current_content:
                # Append to current content
                current_content.append(stripped)
            else:
                # Standalone line without speaker
                result.append(stripped)
        elif speaker == current_speaker:
            # Same speaker - consolidate
            if content:
                current_content.append(content)
        else:
            # Different speaker - flush previous and start new
            if current_speaker and current_content:
                result.append(f"{current_speaker}: {' '.join(current_content)}")
                previous_speaker = current_speaker

            # Add line break when speaker changes (if there was a previous speaker)
            if previous_speaker and previous_speaker != speaker:
                # Only add empty line if last line in result is not already empty
                if result and result[-1] != '':
                    result.append('')

            current_speaker = speaker
            current_content = [content] if content else []

    # Flush last speaker
    if current_speaker and current_content:
        result.append(f"{current_speaker}: {' '.join(current_content)}")

    return '\n'.join(result)


def extract_new_speakers_from_tagged(tagged_text: str, existing_names: set) -> List[str]:
    """
    Extract speaker names that appear as UNKNOWN or are not in existing glossary.

    Args:
        tagged_text: Text with speaker tags
        existing_names: Set of names already in glossary

    Returns:
        List of new speaker names to add to glossary
    """
    import re

    new_speakers = set()

    # Find all speaker tags - supports both bracketed and legacy formats
    # Bracketed: [민수(PROTAGONIST, MAN)]: or [NARRATOR]:
    # Legacy: 민수(PROTAGONIST, MAN): or NARRATOR:
    bracket_pattern = r'^\[([가-힣\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+)(?:\([^)]+\))?\]:'
    legacy_pattern = r'^([가-힣\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+)(?:\([^)]+\))?:'

    for line in tagged_text.split('\n'):
        stripped = line.strip()
        # Try bracketed format first
        match = re.match(bracket_pattern, stripped)
        if not match:
            # Try legacy format
            match = re.match(legacy_pattern, stripped)

        if match:
            speaker_name = match.group(1)
            # Check if it's not NARRATOR or already known
            if speaker_name != 'NARRATOR' and speaker_name not in existing_names:
                new_speakers.add(speaker_name)

    return list(new_speakers)


def update_glossary_with_speakers(
    glossary_path: Path,
    new_speakers: List[str],
    target_language: str,
    llm_processor
) -> int:
    """
    Translate new speakers and add to glossary.

    Args:
        glossary_path: Path to glossary JSON file
        new_speakers: List of new speaker names (in Korean)
        target_language: Target language for translation
        llm_processor: LLM processor instance

    Returns:
        Count of terms added
    """
    if not new_speakers or target_language == 'korean':
        return 0

    # Load existing glossary
    glossary_data = {'terms': []}
    if glossary_path.exists():
        try:
            with open(glossary_path, 'r', encoding='utf-8') as f:
                glossary_data = json.load(f)
        except Exception as e:
            print(f"  ⚠️  Could not load glossary: {e}")

    existing_originals = {t.get('original', '') for t in glossary_data.get('terms', [])}
    speakers_to_add = [s for s in new_speakers if s not in existing_originals]

    if not speakers_to_add:
        return 0

    added_count = 0

    # Translate each speaker name
    for speaker in speakers_to_add:
        try:
            # Use LLM to translate the name
            result = llm_processor.execute({
                'text': speaker,
                'operation': 'translate_term',
                'params': {
                    'source_language': 'korean',
                    'target_language': target_language
                }
            })

            translated = result.get('output', speaker).strip()

            # Add to glossary
            glossary_data['terms'].append({
                'original': speaker,
                'translation': translated,
                'category': 'character',
                'context': 'Auto-extracted speaker from Stage 03a',
                'first_appearance': ''
            })
            added_count += 1
            print(f"    + Added: {speaker} → {translated}")

        except Exception as e:
            print(f"    ⚠️  Failed to translate '{speaker}': {e}")
            # Add with original name as fallback
            glossary_data['terms'].append({
                'original': speaker,
                'translation': speaker,
                'category': 'character',
                'context': 'Auto-extracted speaker (translation failed)',
                'first_appearance': ''
            })
            added_count += 1

    # Save updated glossary
    if added_count > 0:
        try:
            from datetime import datetime
            glossary_data['last_updated'] = datetime.now().isoformat()

            with open(glossary_path, 'w', encoding='utf-8') as f:
                json.dump(glossary_data, f, ensure_ascii=False, indent=2)

            print(f"  💾 Updated glossary with {added_count} new speakers")
        except Exception as e:
            print(f"  ❌ Failed to save glossary: {e}")

    return added_count


def extract_characters_from_series(series_folder: Path, llm_processor: LLMProcessor) -> List[Dict]:
    """
    Phase 1: Extract character dictionary from entire series.

    Args:
        series_folder: Path to series folder
        llm_processor: LLM processor instance

    Returns:
        List of character dictionaries
    """
    print("=" * 60)
    print("  Phase 1: Character Extraction")
    print("=" * 60)
    print()

    # Load from Korean source (01_split/korean)
    korean_split = series_folder / '01_split' / 'korean'

    if not korean_split.exists():
        # Fallback to 03_formatted/korean
        korean_split = series_folder / '03_formatted' / 'korean'

    if not korean_split.exists():
        print(f"  ❌ Korean source not found: {korean_split}")
        return []

    # Load all episode content
    episodes = sorted(korean_split.glob('episode_*.json'))
    if not episodes:
        print(f"  ⚠️  No episodes found in {korean_split}")
        return []

    print(f"  📊 Scanning {len(episodes)} episodes for characters...")

    # Combine all episode text
    combined_text = ""
    for ep_file in episodes:
        try:
            with open(ep_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                content = data.get('content', '')
                ep_num = ep_file.stem.replace('episode_', '')
                combined_text += f"\n=== Episode {ep_num} ===\n{content}\n"
        except Exception as e:
            print(f"  ⚠️  Failed to load {ep_file.name}: {e}")

    if not combined_text:
        print("  ❌ No content found to extract characters from")
        return []

    print(f"  📝 Total text: {len(combined_text):,} characters")
    print()
    print("  🔍 Extracting characters with LLM...")

    # Extract characters
    try:
        result = llm_processor.execute({
            'text': combined_text,
            'operation': 'extract_characters',
            'params': {}
        })
        characters_json = result['output']
        characters = json.loads(characters_json)

        print(f"  ✅ Extracted {len(characters)} characters")
        print()

        # Display extracted characters
        for char in characters[:10]:  # Show first 10
            name = char.get('name', 'Unknown')
            gender = char.get('gender', 'UNKNOWN')
            role = char.get('role', 'UNKNOWN')
            print(f"     - {name} ({role}, {gender})")

        if len(characters) > 10:
            print(f"     ... and {len(characters) - 10} more")

        return characters

    except Exception as e:
        print(f"  ❌ Character extraction failed: {e}")
        return []


def run_stage_3a(
    series_folder: Path,
    target_languages: Optional[List[str]] = None,
    skip_phase1: bool = False,
    max_episodes: int = None
):
    """
    Run Stage 3a: Speaker Tagging for each target language.

    Args:
        series_folder: Path to series folder
        target_languages: List of target languages (default: all 3)
        skip_phase1: Skip character extraction if dictionary exists
        max_episodes: Maximum number of episodes to process (None = all)
    """
    if target_languages is None:
        target_languages = TARGET_LANGUAGES

    print("=" * 80)
    print("STAGE 3a: Speaker Tagging")
    print("=" * 80)
    print()

    stage_03_formatted = series_folder / '03_formatted'
    stage_03a_tagged = series_folder / '03a_speaker_tagged'
    character_dict_path = series_folder / 'character_dictionary.json'

    if not stage_03_formatted.exists():
        print(f"❌ Stage 3 output not found: {stage_03_formatted}")
        print("   Please run stage_03_format.py first")
        return False

    print(f"📁 Series: {series_folder.name}")
    print(f"🌏 Languages to tag: {', '.join(target_languages)}")
    print()

    llm_processor = LLMProcessor()

    # Phase 1: Extract character dictionary
    characters = []
    if skip_phase1 and character_dict_path.exists():
        print("⏭️  Skipping Phase 1 - Loading existing character dictionary")
        try:
            with open(character_dict_path, 'r', encoding='utf-8') as f:
                char_data = json.load(f)
                characters = char_data.get('characters', [])
                print(f"   Loaded {len(characters)} characters")
        except Exception as e:
            print(f"   ⚠️  Failed to load: {e}")
            print("   Running character extraction...")
            characters = extract_characters_from_series(series_folder, llm_processor)
    else:
        characters = extract_characters_from_series(series_folder, llm_processor)

    if not characters:
        print()
        print("⚠️  No characters extracted. Using empty dictionary.")
        characters = []

    # Save character dictionary
    char_dict_data = {
        'series_name': series_folder.name,
        'source_language': 'korean',
        'character_count': len(characters),
        'characters': characters
    }

    with open(character_dict_path, 'w', encoding='utf-8') as f:
        json.dump(char_dict_data, f, ensure_ascii=False, indent=2)

    print()
    print(f"💾 Character dictionary saved: {character_dict_path.name}")
    print()
    print("-" * 80)

    # Phase 2: Apply speaker tags per language
    print()
    print("=" * 60)
    print("  Phase 2: Speaker Tagging")
    print("=" * 60)
    print()

    overall_success = True

    for target_lang in target_languages:
        print(f"\n{'='*60}")
        print(f"  Tagging Speakers for {LANGUAGE_DISPLAY.get(target_lang, target_lang)}")
        print(f"{'='*60}\n")

        source_folder = stage_03_formatted / target_lang
        target_folder = stage_03a_tagged / target_lang

        if not source_folder.exists():
            print(f"  ⚠️  Source folder not found: {source_folder}")
            print(f"     Skipping {target_lang}...")
            continue

        target_folder.mkdir(parents=True, exist_ok=True)

        # Load glossary and map character names
        glossary = load_glossary(series_folder, target_lang)
        mapped_characters = map_character_names(
            [char.copy() for char in characters],
            glossary,
            target_lang
        )

        # Format character dict for this language
        lang_char_dict = []
        for char in mapped_characters:
            lang_char_dict.append({
                'name': char.get('name_display', char.get('name', '')),
                'gender': char.get('gender', 'UNKNOWN'),
                'role': char.get('role', 'UNKNOWN'),
                'description': char.get('description', ''),
                'aliases': char.get('aliases_display', char.get('aliases', []))
            })

        # Get all episode files
        episodes = sorted(source_folder.glob('episode_*.json'))

        if not episodes:
            print(f"  ⚠️  No episode files found in {source_folder}")
            continue

        # Apply max_episodes limit if specified
        total_episodes = len(episodes)
        if max_episodes and len(episodes) > max_episodes:
            print(f"  📋 Limiting to first {max_episodes} episodes (total: {total_episodes})")
            episodes = episodes[:max_episodes]

        print(f"  📊 Episodes to tag: {len(episodes)}")
        print(f"  👥 Characters available: {len(lang_char_dict)}")

        # Track progress
        failed_episodes = []
        skipped_episodes = []
        processed_count = 0

        # Track new speakers for glossary update
        all_new_speakers = set()
        existing_glossary_names = {
            t.get('original', '') for t in glossary.get('terms', [])
        }

        with tqdm(total=len(episodes), desc="  Tagging", bar_format='{desc}: {n}/{total}|{bar}| [{elapsed}<{remaining}]') as pbar:
            for episode_file in episodes:
                output_file = target_folder / episode_file.name

                # Skip if already processed
                if output_file.exists():
                    try:
                        with open(output_file, 'r', encoding='utf-8') as f:
                            existing_data = json.load(f)
                            if existing_data.get('metadata', {}).get('speaker_tags_applied'):
                                pbar.write(f"     ⏭️  Skipped {episode_file.name}")
                                skipped_episodes.append(episode_file.name)
                                pbar.update(1)
                                continue
                    except Exception:
                        pass

                try:
                    # Load episode
                    with open(episode_file, 'r', encoding='utf-8') as f:
                        episode_data = json.load(f)

                    content = episode_data['content']

                    # Tag speakers with retry logic
                    max_retries = 3
                    retry_delay = 10
                    tagged_text = None

                    for attempt in range(max_retries):
                        try:
                            tag_result = llm_processor.execute({
                                'text': content,
                                'operation': 'tag_speakers',
                                'params': {
                                    'character_dict': lang_char_dict,
                                    'language': target_lang
                                }
                            })
                            tagged_text = tag_result['output']
                            break
                        except Exception as e:
                            if attempt < max_retries - 1:
                                pbar.write(f"     ⚠️  Retry {attempt + 1}/{max_retries}: {e}")
                                time.sleep(retry_delay)
                            else:
                                raise

                    if tagged_text is None:
                        raise Exception("Speaker tagging failed after retries")

                    # Post-process 1: Translate Korean speaker names to target language
                    tagged_text = translate_speaker_tags_in_output(
                        tagged_text, glossary, target_lang
                    )

                    # Post-process 2: Split lines with multiple speakers
                    tagged_text = split_multiple_speakers_in_line(tagged_text)

                    # Post-process 3: Separate mixed dialogue/narration
                    tagged_text = separate_dialogue_and_narration(tagged_text, target_lang)

                    # Post-process 4: Consolidate consecutive same-speaker lines
                    tagged_text = consolidate_consecutive_speakers(tagged_text)

                    # Extract new speakers for glossary update
                    new_speakers = extract_new_speakers_from_tagged(
                        tagged_text, existing_glossary_names
                    )
                    all_new_speakers.update(new_speakers)

                    # Save tagged episode
                    episode_data['content'] = tagged_text
                    episode_data['metadata']['speaker_tags_applied'] = True
                    episode_data['metadata']['speaker_tagging_language'] = target_lang
                    episode_data['metadata']['character_count'] = len(lang_char_dict)
                    episode_data['metadata']['consolidated'] = True

                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(episode_data, f, ensure_ascii=False, indent=2)

                    processed_count += 1
                    pbar.set_postfix_str(f"{episode_file.name}")
                    pbar.update(1)

                except Exception as e:
                    pbar.write(f"     ❌ Failed {episode_file.name}: {e}")
                    failed_episodes.append((episode_file.name, str(e)))
                    pbar.update(1)

        # Update glossary with new speakers (from Korean tagging only)
        # Korean speakers are the original names that need to be translated
        if all_new_speakers and target_lang == 'korean':
            # Store Korean speakers for glossary updates
            korean_new_speakers = all_new_speakers.copy()

            # Update both Japanese and Taiwanese glossaries
            for glossary_lang, glossary_file in [
                ('japanese', 'glossary_japanese.json'),
                ('taiwanese', 'glossary_taiwanese.json')
            ]:
                glossary_path = series_folder / glossary_file
                if glossary_path.exists():
                    print()
                    print(f"  📝 Adding {len(korean_new_speakers)} new speakers to {glossary_lang} glossary")
                    added = update_glossary_with_speakers(
                        glossary_path,
                        list(korean_new_speakers),
                        glossary_lang,
                        llm_processor
                    )

        # Summary for this language
        print()
        print(f"  {LANGUAGE_DISPLAY.get(target_lang, target_lang)} Summary:")
        print(f"    Processed: {processed_count}")
        print(f"    Skipped: {len(skipped_episodes)}")
        print(f"    Failed: {len(failed_episodes)}")
        if all_new_speakers:
            print(f"    New speakers found: {len(all_new_speakers)}")

        if failed_episodes:
            overall_success = False
            print(f"    ⚠️  Failed episodes:")
            for ep_name, error in failed_episodes[:5]:
                print(f"       - {ep_name}: {error}")

    print()
    print("=" * 80)
    print("Stage 3a Complete")
    print("=" * 80)
    print()

    if overall_success:
        print("✅ All speaker tagging completed successfully!")
        print()
        print("📋 Next Steps:")
        print("   1. Review tagged files in: " + str(stage_03a_tagged))
        print("   2. Check speaker tag accuracy")
        print("   3. Run: python stage_04_tag_emotions.py")
    else:
        print("⚠️  Some speaker tagging failed. Review and retry.")

    return overall_success


if __name__ == '__main__':
    import argparse
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(
        description='Stage 3a: Speaker Tagging',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python stage_03a_speaker_tagging.py "processed/Publisher/Series"
  python stage_03a_speaker_tagging.py "processed/Publisher/Series" --langs korean japanese
  python stage_03a_speaker_tagging.py "processed/Publisher/Series" --skip-extraction

This stage:
  1. Phase 1: Extracts character dictionary from Korean source
  2. Phase 2: Applies speaker tags per language
  3. Outputs to 03a_speaker_tagged/{language}/
        """
    )
    parser.add_argument('series_folder', help='Path to series folder')
    parser.add_argument(
        '--langs',
        nargs='+',
        choices=['korean', 'japanese', 'taiwanese'],
        default=TARGET_LANGUAGES,
        help='Target languages (default: all three)'
    )
    parser.add_argument(
        '--skip-extraction',
        action='store_true',
        help='Skip character extraction if dictionary exists'
    )
    parser.add_argument(
        '--max-episodes',
        type=int,
        default=None,
        help='Maximum number of episodes to process'
    )

    args = parser.parse_args()
    series_folder = Path(args.series_folder)

    if not series_folder.exists():
        print(f"❌ Series folder not found: {series_folder}")
        sys.exit(1)

    success = run_stage_3a(
        series_folder,
        target_languages=args.langs,
        skip_phase1=args.skip_extraction,
        max_episodes=args.max_episodes
    )
    sys.exit(0 if success else 1)
