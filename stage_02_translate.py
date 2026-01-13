#!/usr/bin/env python3
"""
Stage 2: Multi-Language Translation
Translate split episodes to 3 target languages (Korean, Japanese, Taiwanese)
"""

import sys
import json
import time
import shutil
from pathlib import Path
from typing import List, Optional, Dict
from tqdm import tqdm
from processors.llm_processor import LLMProcessor
from processors.glossary_manager import GlossaryManager


def enforce_name_consistency(terms: List[Dict], target_lang: str) -> List[Dict]:
    """
    Enforce consistency between full names (성+이름) and first names (이름만).

    When a full name like "이서연" is translated to "イ・ソヨン" (JP) or "李書妍" (TW),
    the first name "서연" must be translated to match: "ソヨン" or "書妍".

    Also handles:
    - Compound terms like "서연의 고모" → "ソヨンの叔母" or "書妍的姑姑"
    - Foreign names with spaces like "아이든 시몬 오르피어스" → "아이든"

    Args:
        terms: List of term dictionaries with 'original' and 'translation'
        target_lang: Target language ('japanese' or 'taiwanese')

    Returns:
        Updated terms list with consistent name translations
    """
    # Build mapping of full names to their translations
    full_name_map = {}  # {full_name_korean: (first_name_korean, first_name_translation)}
    first_name_map = {}  # {first_name_korean: correct_translation}
    foreign_name_map = {}  # {short_name_korean: correct_translation} for foreign names

    # Common Korean surnames (성씨)
    korean_surnames = [
        '김', '이', '박', '최', '정', '강', '조', '윤', '장', '임',
        '한', '오', '서', '신', '권', '황', '안', '송', '류', '전',
        '홍', '고', '문', '양', '손', '배', '백', '허', '유', '남',
        '심', '노', '하', '곽', '성', '차', '주', '우', '구', '민',
        '진', '나', '지', '엄', '변', '채', '원', '천', '방', '공'
    ]

    # First pass: identify full names and extract first name translations
    # Only consider names with 3+ characters as full names (surname + given name of 2+ chars)
    # This avoids misidentifying "서연" (given name) as "서" (surname) + "연" (given name)
    for term in terms:
        if term.get('category') != 'character':
            continue

        original = term.get('original', '')
        translation = term.get('translation', '')

        # Check if this is a full name (surname + given name)
        # Full names should be 3+ characters (1 char surname + 2+ char given name)
        if len(original) >= 3:
            potential_surname = original[0]
            if potential_surname in korean_surnames:
                first_name = original[1:]  # 이름만 (given name)
                if len(first_name) >= 2:  # Given name should be at least 2 characters
                    # Extract the first name part from translation
                    if target_lang == 'japanese':
                        # For Japanese: イ・ソヨン -> ソヨン
                        if '・' in translation:
                            parts = translation.split('・', 1)
                            if len(parts) == 2:
                                first_name_translation = parts[1]
                                full_name_map[original] = (first_name, first_name_translation)
                                first_name_map[first_name] = first_name_translation
                    elif target_lang == 'taiwanese':
                        # For Taiwanese: 李瑞妍 -> 瑞妍
                        if len(translation) >= 3:
                            # First character is surname, rest is given name
                            first_name_translation = translation[1:]
                            if first_name_translation:
                                full_name_map[original] = (first_name, first_name_translation)
                                first_name_map[first_name] = first_name_translation

    # Handle foreign names with spaces (e.g., "아이든 시몬 오르피어스" → "아이든")
    # These are common in fantasy/romance novels
    for term in terms:
        if term.get('category') != 'character':
            continue

        original = term.get('original', '')
        translation = term.get('translation', '')

        # Check if this is a multi-part foreign name (contains space)
        if ' ' in original and len(original.split()) >= 2:
            parts = original.split()
            short_name = parts[0]  # First part is usually the short name (e.g., "아이든")

            # Extract short name translation from full name translation
            if target_lang == 'japanese':
                # For Japanese: アイデン・シモン・オルフェウス -> アイデン
                if '・' in translation:
                    trans_parts = translation.split('・')
                    if len(trans_parts) >= 1:
                        short_translation = trans_parts[0]
                        foreign_name_map[short_name] = short_translation
            elif target_lang == 'taiwanese':
                # For Taiwanese: 艾登·西蒙·奧菲斯 -> 艾登
                if '·' in translation or '・' in translation:
                    sep = '·' if '·' in translation else '・'
                    trans_parts = translation.split(sep)
                    if len(trans_parts) >= 1:
                        short_translation = trans_parts[0]
                        foreign_name_map[short_name] = short_translation
                # Also handle space-separated: 艾登 西蒙 奧菲斯
                elif ' ' in translation:
                    trans_parts = translation.split()
                    if len(trans_parts) >= 1:
                        short_translation = trans_parts[0]
                        foreign_name_map[short_name] = short_translation

    # Build a mapping of all character name translations (including wrong ones)
    # This maps original names to their current translations before correction
    original_translations = {}
    for term in terms:
        if term.get('category') == 'character':
            original_translations[term.get('original', '')] = term.get('translation', '')

    # Build set of full names to exclude from correction
    full_names = set(full_name_map.keys())

    # Add foreign full names to exclusion set
    for term in terms:
        original = term.get('original', '')
        if ' ' in original and len(original.split()) >= 2:
            full_names.add(original)

    # Second pass: fix terms containing first names (Korean names)
    corrections_made = 0
    for term in terms:
        original = term.get('original', '')
        current_translation = term.get('translation', '')

        # Skip full names - they are the source of truth, not correction targets
        if original in full_names:
            continue

        # Check foreign name consistency first (e.g., "아이든" from "아이든 시몬 오르피어스")
        if original in foreign_name_map:
            correct_translation = foreign_name_map[original]
            if current_translation != correct_translation:
                term['translation'] = correct_translation
                term['_corrected_from'] = current_translation
                term['_matched_foreign_name'] = original
                corrections_made += 1
                print(f"        🔧 Fixed foreign name: {original}: {current_translation} → {correct_translation}")
                continue

        # Check each known first name
        for first_name, correct_translation in first_name_map.items():
            if first_name in original:
                # Case 1: Exact match (first name only)
                if original == first_name:
                    if current_translation != correct_translation:
                        term['translation'] = correct_translation
                        term['_corrected_from'] = current_translation
                        term['_matched_first_name'] = first_name
                        corrections_made += 1
                    break

                # Case 2: Compound term containing first name (e.g., "서연의 고모")
                else:
                    # Get the original (possibly wrong) translation of the first name
                    wrong_translation = original_translations.get(first_name, '')

                    # If the wrong translation exists in current translation and differs from correct
                    if wrong_translation and wrong_translation != correct_translation and wrong_translation in current_translation:
                        new_translation = current_translation.replace(wrong_translation, correct_translation)
                        if new_translation != current_translation:
                            term['translation'] = new_translation
                            term['_corrected_from'] = current_translation
                            term['_name_replaced'] = f"{wrong_translation} → {correct_translation}"
                            corrections_made += 1
                    # Also check if any Chinese character variant of the name is in the translation
                    # This handles cases where LLM translated compound terms with different characters
                    elif target_lang == 'taiwanese' and len(correct_translation) >= 2:
                        # For compound terms, check if ANY 2-3 character sequence might be the name
                        # by looking at position where the name should appear
                        name_pos = original.find(first_name)
                        if name_pos >= 0:
                            # Calculate approximate position ratio
                            pos_ratio = name_pos / len(original) if len(original) > 0 else 0
                            expected_pos = int(pos_ratio * len(current_translation))

                            # Search for potential name translation around expected position
                            search_start = max(0, expected_pos - 2)
                            search_end = min(len(current_translation), expected_pos + len(correct_translation) + 2)
                            search_region = current_translation[search_start:search_end]

                            # Try to find any 2-char Chinese name that's NOT the correct one
                            for i in range(len(search_region) - 1):
                                potential_name = search_region[i:i+len(correct_translation)]
                                # Check if it looks like a name (all CJK characters) and differs from correct
                                if (len(potential_name) == len(correct_translation) and
                                    potential_name != correct_translation and
                                    all('\u4e00' <= c <= '\u9fff' for c in potential_name)):
                                    # This might be the wrong name translation - replace it
                                    actual_start = search_start + i
                                    new_translation = (current_translation[:actual_start] +
                                                      correct_translation +
                                                      current_translation[actual_start + len(correct_translation):])
                                    if new_translation != current_translation:
                                        term['translation'] = new_translation
                                        term['_corrected_from'] = current_translation
                                        term['_name_replaced'] = f"{potential_name} → {correct_translation}"
                                        corrections_made += 1
                                    break
                    break

    if corrections_made > 0:
        print(f"     📝 Fixed {corrections_made} name consistency issues")

    return terms

# Target languages for output
TARGET_LANGUAGES = ['korean', 'japanese', 'taiwanese']

# Language display names
LANGUAGE_DISPLAY = {
    'korean': '🇰🇷 Korean',
    'japanese': '🇯🇵 Japanese',
    'taiwanese': '🇹🇼 Taiwanese'
}


def _copy_korean_episodes(series_folder: Path, episodes: List[Path]) -> int:
    """
    Korean source = target, just copy files.

    Returns:
        Number of episodes copied
    """
    target_folder = series_folder / '02_translated' / 'korean'
    target_folder.mkdir(parents=True, exist_ok=True)

    copied = 0
    for episode_file in episodes:
        output_file = target_folder / episode_file.name

        if output_file.exists():
            continue

        with open(episode_file, 'r', encoding='utf-8') as f:
            episode_data = json.load(f)

        episode_data['metadata']['translated_to'] = 'korean'
        episode_data['metadata']['translation_type'] = 'identity'

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(episode_data, f, ensure_ascii=False, indent=2)
        copied += 1

    return copied


def _generate_glossary_for_language(
    series_folder: Path,
    target_lang: str,
    source_language: str,
    episodes: List[Path],
    llm_processor: 'LLMProcessor'
) -> tuple[Path, 'GlossaryManager']:
    """
    Generate glossary JSON for one language.

    Returns:
        Tuple of (glossary_file_path, GlossaryManager)
    """
    from datetime import datetime

    glossary_file = series_folder / f'glossary_{target_lang}.json'

    if glossary_file.exists():
        glossary_manager = GlossaryManager(glossary_path=glossary_file)
        print(f"     📚 Loaded existing glossary: {len(glossary_manager.get_all_terms())} terms")
        return glossary_file, glossary_manager

    glossary_manager = GlossaryManager()

    print(f"     📚 Creating comprehensive glossary from full series...")
    print(f"        🔍 Scanning {len(episodes)} episodes...")

    # Load all episode contents
    all_contents = []
    for ep_file in episodes:
        with open(ep_file, 'r', encoding='utf-8') as f:
            ep_data = json.load(f)
            all_contents.append(ep_data['content'])

    total_chars = sum(len(c) for c in all_contents)
    print(f"        📊 Total content: {total_chars:,} characters")

    # Extract terms from full series
    print(f"        ⏳ Extracting terms...")
    terms = llm_processor.extract_terms_from_full_series(all_contents)
    print(f"        📝 Extracted {len(terms)} terms")

    # Translate each term
    print(f"        🌏 Translating {len(terms)} terms to {target_lang}...")
    with tqdm(total=len(terms), desc="           Terms", bar_format='{desc}: {n}/{total}|{bar}|') as term_pbar:
        for term in terms:
            try:
                term_translation = llm_processor.translate_term(
                    term=term['original'],
                    source_lang=source_language,
                    target_lang=target_lang,
                    category=term.get('category', 'term'),
                    context=term.get('context', '')
                )

                glossary_manager.add_term(
                    original=term['original'],
                    translation=term_translation,
                    category=term.get('category', 'term'),
                    context=term.get('context', '')
                )
            except Exception:
                pass  # Skip failed terms
            term_pbar.update(1)

    # Enforce name consistency (full name ↔ first name)
    all_terms = glossary_manager.get_all_terms()
    corrected_terms = enforce_name_consistency(all_terms, target_lang)

    # Update glossary with corrected terms
    for term in corrected_terms:
        if term.get('_corrected_from'):
            glossary_manager.update_term(
                original=term['original'],
                translation=term['translation']
            )

    # Save glossary
    glossary_manager.glossary_data['series_name'] = series_folder.name
    glossary_manager.glossary_data['source_language'] = source_language
    glossary_manager.glossary_data['target_language'] = target_lang
    glossary_manager.glossary_data['created_date'] = datetime.now().isoformat()

    glossary_manager.save(glossary_file)
    print(f"        💾 Saved glossary: {len(glossary_manager.get_all_terms())} terms")

    return glossary_file, glossary_manager


def _generate_glossary_csv_for_language(
    series_folder: Path,
    glossary_file: Path,
    target_lang: str
) -> Optional[Path]:
    """
    Generate glossary CSV for one language.

    Returns:
        CSV file path or None
    """
    from processors.review_generator import ReviewGenerator

    review_gen = ReviewGenerator(series_folder)
    csv_path = review_gen.generate_glossary_csv(glossary_file, target_language=target_lang)

    if csv_path:
        print(f"        📊 Exported glossary CSV: {csv_path}")

    return csv_path


def _translate_episodes_for_language(
    series_folder: Path,
    target_lang: str,
    source_language: str,
    episodes: List[Path],
    glossary_manager: 'GlossaryManager',
    llm_processor: 'LLMProcessor'
) -> bool:
    """
    Translate episodes for one language.

    Returns:
        True if successful
    """
    target_folder = series_folder / '02_translated' / target_lang
    target_folder.mkdir(parents=True, exist_ok=True)

    failed_episodes = []
    skipped_episodes = []
    processed_count = 0

    with tqdm(total=len(episodes), desc=f"     {target_lang}", bar_format='{desc}: {n}/{total}|{bar}| [{elapsed}<{remaining}]') as pbar:
        for episode_file in episodes:
            output_file = target_folder / episode_file.name

            # Skip if already processed
            if output_file.exists():
                try:
                    with open(output_file, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                        if existing_data.get('metadata', {}).get('translated_to') == target_lang:
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
                original_title = episode_data.get('title', '')

                # Translate with retry logic
                max_retries = 3
                retry_delay = 10
                translated_text = None

                for attempt in range(max_retries):
                    try:
                        translate_result = llm_processor.execute({
                            'text': content,
                            'operation': 'translate',
                            'params': {
                                'source_lang': source_language,
                                'target_lang': target_lang,
                                'glossary': glossary_manager.get_all_terms()
                            }
                        })
                        translated_text = translate_result['output']
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            pbar.write(f"        ⚠️  Retry {attempt + 1}/{max_retries}: {e}")
                            time.sleep(retry_delay)
                        else:
                            raise

                if translated_text is None:
                    raise Exception("Translation failed after retries")

                # Translate title if present
                translated_title = original_title
                if original_title and source_language != target_lang:
                    try:
                        title_result = llm_processor.execute({
                            'text': original_title,
                            'operation': 'translate_title',
                            'params': {
                                'source_lang': source_language,
                                'target_lang': target_lang,
                                'glossary': glossary_manager.get_all_terms()
                            }
                        })
                        translated_title = title_result['output']
                    except Exception as e:
                        pbar.write(f"        ⚠️  Title translation failed: {e}")

                # Save translated episode
                episode_data['content'] = translated_text
                episode_data['title'] = translated_title
                episode_data['metadata']['translated_to'] = target_lang
                episode_data['metadata']['source_language'] = source_language
                episode_data['metadata']['translation_type'] = 'llm'
                episode_data['metadata']['glossary_used'] = True
                if original_title != translated_title:
                    episode_data['metadata']['original_title'] = original_title

                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(episode_data, f, ensure_ascii=False, indent=2)

                processed_count += 1
                pbar.update(1)

            except Exception as e:
                pbar.write(f"        ❌ Failed {episode_file.name}: {e}")
                failed_episodes.append((episode_file.name, str(e)))
                pbar.update(1)

    # Print summary
    print(f"        ✅ Processed: {processed_count}, Skipped: {len(skipped_episodes)}, Failed: {len(failed_episodes)}")

    return len(failed_episodes) == 0


def _glossary_review_checkpoint(
    series_folder: Path,
    languages: List[str],
    glossary_managers: Dict[str, 'GlossaryManager'],
    csv_paths: Dict[str, Optional[Path]]
) -> bool:
    """
    Human review checkpoint for all glossaries at once.

    Returns:
        True if should proceed, False to abort
    """
    print("\n  " + "="*60)
    print("  📋 GLOSSARY REVIEW MODE")
    print("  " + "="*60)
    print("\n  모든 용어집이 생성되었습니다. 번역 전 검토해주세요:")
    print()

    for lang in languages:
        emoji = '🇯🇵' if lang == 'japanese' else '🇹🇼'
        glossary_file = series_folder / f'glossary_{lang}.json'
        term_count = len(glossary_managers[lang].get_all_terms())
        print(f"  {emoji} {lang.upper()}:")
        print(f"     JSON: {glossary_file} ({term_count} terms)")
        if csv_paths.get(lang):
            print(f"     CSV:  {csv_paths[lang]}")

    print()
    print("  CSV 파일을 수정하면 'y' 입력 시 자동으로 JSON에 반영됩니다.")
    print()

    while True:
        user_input = input("  계속 진행하시겠습니까? (y: 진행 / n: 중단 / r: 용어집 다시 로드): ").strip().lower()
        if user_input == 'y':
            # Auto-sync CSV to JSON before proceeding
            synced = _sync_csv_to_json_if_modified(
                series_folder, languages, csv_paths, glossary_managers
            )
            if synced > 0:
                print(f"  📥 자동 동기화됨: {synced}개 언어")
            return True
        elif user_input == 'n':
            print("  ❌ 번역이 중단되었습니다.")
            return False
        elif user_input == 'r':
            # Sync CSV first, then reload
            synced = _sync_csv_to_json_if_modified(
                series_folder, languages, csv_paths, glossary_managers
            )
            if synced > 0:
                print(f"  📥 자동 동기화됨: {synced}개 언어")
            for lang in languages:
                glossary_file = series_folder / f'glossary_{lang}.json'
                glossary_managers[lang] = GlossaryManager(glossary_path=glossary_file)
                print(f"  📚 Reloaded {lang} glossary: {len(glossary_managers[lang].get_all_terms())} terms")
            print("  용어집을 다시 로드했습니다. 계속 검토해주세요.")
        else:
            print("  ⚠️  y, n, r 중 하나를 입력해주세요.")


def _print_glossary_only_summary(
    series_folder: Path,
    glossary_managers: Dict[str, 'GlossaryManager'],
    csv_paths: Dict[str, Optional[Path]]
):
    """Print summary for glossary-only mode."""
    from processors.review_generator import ReviewGenerator

    print("\n" + "="*60)
    print("  Glossary Generation Complete")
    print("="*60)
    print()
    print("✅ All glossaries generated!")
    print()

    for lang, manager in glossary_managers.items():
        emoji = '🇯🇵' if lang == 'japanese' else '🇹🇼'
        print(f"  {emoji} {lang.upper()}: {len(manager.get_all_terms())} terms")
        if csv_paths.get(lang):
            print(f"     CSV: {csv_paths[lang]}")

    print()
    print("📋 Next Steps:")
    print("   1. Review glossary CSV files")
    print("   2. Edit CSV if needed, then convert back to JSON:")
    print('      python utils/csv_to_glossary.py "<csv_path>"')
    print("   3. Run translation with: --langs <lang>")


def _sync_csv_to_json_if_modified(
    series_folder: Path,
    languages: List[str],
    csv_paths: Dict[str, Optional[Path]],
    glossary_managers: Dict[str, 'GlossaryManager']
) -> int:
    """
    CSV 파일이 JSON보다 최신인 경우 자동으로 _PROCESSED의 JSON에 동기화.

    CSV는 _REVIEW 폴더에 있고, JSON은 _PROCESSED (series_folder)에 있으므로
    CSV를 읽어서 series_folder의 JSON을 직접 업데이트함.

    Returns:
        동기화된 언어 수
    """
    import csv
    import shutil
    from datetime import datetime

    synced_count = 0

    for lang in languages:
        csv_path = csv_paths.get(lang)
        if not csv_path or not csv_path.exists():
            continue

        # JSON은 _PROCESSED (series_folder)에 있음
        json_path = series_folder / f'glossary_{lang}.json'

        if not json_path.exists():
            continue

        # CSV가 JSON보다 최신인지 확인
        csv_mtime = csv_path.stat().st_mtime
        json_mtime = json_path.stat().st_mtime

        if csv_mtime > json_mtime:
            emoji = '🇯🇵' if lang == 'japanese' else '🇹🇼'
            print(f"\n  {emoji} {lang.upper()}: CSV가 수정됨, JSON에 동기화 중...")

            try:
                # Load existing JSON to preserve metadata
                with open(json_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)

                # Read CSV and convert to terms
                terms = []
                with open(csv_path, 'r', encoding='utf-8-sig') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
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

                # Update JSON with new terms (preserve other metadata)
                existing_data['terms'] = terms
                existing_data['last_updated'] = datetime.now().isoformat()

                # Backup existing JSON
                backup_path = json_path.with_suffix('.json.bak')
                shutil.copy2(json_path, backup_path)

                # Save updated JSON to _PROCESSED
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(existing_data, f, ensure_ascii=False, indent=2)

                # Reload glossary manager
                glossary_managers[lang] = GlossaryManager(glossary_path=json_path)
                print(f"     ✅ 동기화 완료: {len(terms)} terms → {json_path.name}")
                synced_count += 1

            except Exception as e:
                print(f"     ⚠️  동기화 실패: {e}")

    return synced_count


def run_stage_2(
    series_folder: Path,
    target_languages: Optional[List[str]] = None,
    glossary_only: bool = False,
    review_glossary: bool = False,
    max_episodes: int = None
):
    """
    Run Stage 2: Multi-Language Translation (Phase-based workflow)

    Restructured workflow:
    1. Phase 1: Generate ALL glossary JSONs (non-Korean languages)
    2. Phase 2: Generate ALL glossary CSVs
    3. Phase 3: Human review checkpoint (if review_glossary=True)
    4. Phase 4: Translate ALL languages

    Args:
        series_folder: Path to series folder
        target_languages: List of target languages (default: all 3)
        glossary_only: If True, only generate glossary and exit (no translation)
        review_glossary: If True, pause after glossary generation for human review
        max_episodes: Maximum number of episodes to process (None = all)
    """
    if target_languages is None:
        target_languages = TARGET_LANGUAGES

    print("=" * 80)
    print("STAGE 2: Multi-Language Translation (Phase-based)")
    print("=" * 80)
    print()

    stage_01_split = series_folder / '01_split'
    stage_02_translated = series_folder / '02_translated'

    if not stage_01_split.exists():
        print(f"❌ Stage 1 output not found: {stage_01_split}")
        print("   Please run stage_01_split.py first")
        return False

    # Load series metadata to get source language
    metadata_file = series_folder / 'series_metadata.json'
    if not metadata_file.exists():
        print(f"❌ Series metadata not found: {metadata_file}")
        return False

    with open(metadata_file, 'r', encoding='utf-8') as f:
        series_metadata = json.load(f)

    source_language = series_metadata.get('source_language', 'korean')
    print(f"📖 Source language: {source_language}")
    print(f"🌏 Target languages: {', '.join(target_languages)}")
    print()

    # Get all episode files
    episodes = sorted(stage_01_split.glob('episode_*.json'))

    if not episodes:
        print(f"❌ No episode files found in {stage_01_split}")
        return False

    # Apply max_episodes limit if specified
    total_episodes = len(episodes)
    if max_episodes and len(episodes) > max_episodes:
        print(f"📋 Limiting to first {max_episodes} episodes (total: {total_episodes})")
        episodes = episodes[:max_episodes]

    print(f"📁 Series: {series_folder.name}")
    print(f"📊 Episodes to translate: {len(episodes)}")
    print()

    llm_processor = LLMProcessor()

    # Filter out Korean (no glossary/translation needed - just copy)
    non_korean_langs = [lang for lang in target_languages if lang != source_language]

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 0: Handle Korean (source = target, just copy)
    # ═══════════════════════════════════════════════════════════════════════════
    if source_language in target_languages:
        print("=" * 60)
        print("  PHASE 0: Copying Korean Episodes (source = target)")
        print("=" * 60)
        print()
        copied = _copy_korean_episodes(series_folder, episodes)
        print(f"  ✅ Copied {copied} episodes (skipped existing)")
        print()

    # If no non-Korean languages, we're done
    if not non_korean_langs:
        print("✅ Only Korean was requested, stage complete!")
        return True

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 1: Generate ALL glossary JSONs
    # ═══════════════════════════════════════════════════════════════════════════
    print("=" * 60)
    print("  PHASE 1: Generating Glossary JSONs")
    print("=" * 60)
    print()

    glossary_managers: Dict[str, GlossaryManager] = {}
    glossary_files: Dict[str, Path] = {}

    for target_lang in non_korean_langs:
        emoji = '🇯🇵' if target_lang == 'japanese' else '🇹🇼'
        print(f"  {emoji} {target_lang.upper()}")

        glossary_file, manager = _generate_glossary_for_language(
            series_folder, target_lang, source_language, episodes, llm_processor
        )
        glossary_managers[target_lang] = manager
        glossary_files[target_lang] = glossary_file
        print()

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 2: Generate ALL glossary CSVs
    # ═══════════════════════════════════════════════════════════════════════════
    print("=" * 60)
    print("  PHASE 2: Generating Glossary CSVs")
    print("=" * 60)
    print()

    csv_paths: Dict[str, Optional[Path]] = {}

    for target_lang in non_korean_langs:
        emoji = '🇯🇵' if target_lang == 'japanese' else '🇹🇼'
        print(f"  {emoji} {target_lang.upper()}")

        # Check if CSV already exists
        from processors.review_generator import ReviewGenerator
        review_gen = ReviewGenerator(series_folder)
        expected_csv = review_gen.review_dir / f'glossary_{target_lang}.csv'

        if expected_csv.exists():
            csv_paths[target_lang] = expected_csv
            print(f"        📊 CSV already exists: {expected_csv}")
        else:
            csv_path = _generate_glossary_csv_for_language(
                series_folder, glossary_files[target_lang], target_lang
            )
            csv_paths[target_lang] = csv_path
        print()

    # ═══════════════════════════════════════════════════════════════════════════
    # Handle glossary_only mode - exit after generating all glossaries
    # ═══════════════════════════════════════════════════════════════════════════
    if glossary_only:
        _print_glossary_only_summary(series_folder, glossary_managers, csv_paths)
        return True

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 3: Human Review Checkpoint (all glossaries at once)
    # ═══════════════════════════════════════════════════════════════════════════
    if review_glossary:
        # Check for CSV modifications and sync back to JSON
        synced = _sync_csv_to_json_if_modified(
            series_folder, non_korean_langs, csv_paths, glossary_managers
        )
        if synced > 0:
            print(f"\n  📥 자동 동기화됨: {synced}개 언어")

        proceed = _glossary_review_checkpoint(
            series_folder, non_korean_langs, glossary_managers, csv_paths
        )
        if not proceed:
            return False

        # Reload glossaries after potential human edits
        for target_lang in non_korean_langs:
            glossary_file = series_folder / f'glossary_{target_lang}.json'
            glossary_managers[target_lang] = GlossaryManager(glossary_path=glossary_file)

    # ═══════════════════════════════════════════════════════════════════════════
    # PHASE 4: Translate ALL languages
    # ═══════════════════════════════════════════════════════════════════════════
    print()
    print("=" * 60)
    print("  PHASE 4: Translating Episodes")
    print("=" * 60)
    print()

    overall_success = True

    for target_lang in non_korean_langs:
        emoji = '🇯🇵' if target_lang == 'japanese' else '🇹🇼'
        print(f"  {emoji} {target_lang.upper()}")

        success = _translate_episodes_for_language(
            series_folder, target_lang, source_language,
            episodes, glossary_managers[target_lang], llm_processor
        )
        if not success:
            overall_success = False
        print()

    # ═══════════════════════════════════════════════════════════════════════════
    # Summary
    # ═══════════════════════════════════════════════════════════════════════════
    print()
    print("=" * 80)
    print("Stage 2 Complete")
    print("=" * 80)
    print()

    if overall_success:
        print("✅ All translations completed successfully!")
        print()
        print("📋 Next Steps:")
        print("   1. Review translations in: " + str(stage_02_translated))
        print("   2. Run: python stage_03_format.py")
    else:
        print("⚠️  Some translations failed. Review and retry.")

    return overall_success


if __name__ == '__main__':
    import argparse
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(
        description='Stage 2: Multi-Language Translation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 기본 실행 (용어집 생성 후 검토 → 번역)
  python stage_02_translate.py "processed/Publisher/Series" --langs taiwanese

  # 자동 실행 (검토 없이 바로 번역)
  python stage_02_translate.py "processed/Publisher/Series" --langs taiwanese --auto

  # 용어집만 생성 (번역 안 함)
  python stage_02_translate.py "processed/Publisher/Series" --langs taiwanese --glossary-only

Workflow:
  1. Reads split episodes from 01_split/
  2. Creates glossary for each target language
  3. (Default) Pauses for human review of glossary
  4. Translates episodes using glossary
  5. Outputs to 02_translated/{language}/
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
        '--auto',
        action='store_true',
        help='Auto mode: skip glossary review and translate immediately'
    )
    parser.add_argument(
        '--glossary-only',
        action='store_true',
        help='Only generate glossary (no translation)'
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

    # Default: review_glossary=True unless --auto is specified
    review_glossary = not args.auto and not args.glossary_only

    success = run_stage_2(
        series_folder,
        target_languages=args.langs,
        glossary_only=args.glossary_only,
        review_glossary=review_glossary,
        max_episodes=args.max_episodes
    )
    sys.exit(0 if success else 1)
