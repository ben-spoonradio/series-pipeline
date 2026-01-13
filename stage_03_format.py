#!/usr/bin/env python3
"""
Stage 3: TTS Formatting
Format translated text for optimal TTS synthesis per target language
"""

import sys
import json
import time
import re
from pathlib import Path
from typing import List, Optional
from tqdm import tqdm
from processors.llm_processor import LLMProcessor
from processors.episode_utils import arabic_to_chinese

# Target languages
TARGET_LANGUAGES = ['korean', 'japanese', 'taiwanese']

# Language display names
LANGUAGE_DISPLAY = {
    'korean': '🇰🇷 Korean',
    'japanese': '🇯🇵 Japanese',
    'taiwanese': '🇹🇼 Taiwanese'
}

# Korean number words
KOREAN_NUMBER_WORDS = {
    1: '일', 2: '이', 3: '삼', 4: '사', 5: '오',
    6: '육', 7: '칠', 8: '팔', 9: '구', 10: '십'
}


def arabic_to_korean(num: int) -> str:
    """
    Convert Arabic number to Korean number word.

    Examples:
        1 → 일, 10 → 십, 11 → 십일, 21 → 이십일, 50 → 오십
    """
    if num <= 0:
        return str(num)

    if num <= 10:
        return KOREAN_NUMBER_WORDS[num]

    if num < 20:
        # 11-19: 십일, 십이, ...
        ones = num % 10
        return f"십{KOREAN_NUMBER_WORDS[ones]}" if ones > 0 else "십"

    if num < 100:
        # 20-99
        tens = num // 10
        ones = num % 10
        result = f"{KOREAN_NUMBER_WORDS[tens]}십"
        if ones > 0:
            result += KOREAN_NUMBER_WORDS[ones]
        return result

    # For numbers >= 100, just return Arabic
    return str(num)

# Episode title patterns by language
EPISODE_PATTERNS = {
    'korean': [
        (r'^(\d+)화\s*[-:]\s*(.+?)(?:\n|$)', 1, 2),
        (r'^제(\d+)화\s*[-:]\s*(.+?)(?:\n|$)', 1, 2),
    ],
    'japanese': [
        (r'^第(\d+)話\s*[-:：]\s*(.+?)(?:\n|$)', 1, 2),
        (r'^(\d+)話\s*[-:：]\s*(.+?)(?:\n|$)', 1, 2),
    ],
    'taiwanese': [
        (r'^第(\d+)話\s*[-:：]\s*(.+?)(?:\n|$)', 1, 2),
        (r'^第(\d+)集\s*[-:：]\s*(.+?)(?:\n|$)', 1, 2),
    ]
}


def extract_title_from_content(content: str, language: str) -> tuple:
    """
    Extract episode title from content based on language.

    Returns:
        Tuple of (title, episode_number) or (None, None)
    """
    patterns = EPISODE_PATTERNS.get(language, EPISODE_PATTERNS['korean'])
    search_text = content[:500]

    for pattern, num_group, title_group in patterns:
        match = re.search(pattern, search_text, re.MULTILINE | re.IGNORECASE)
        if match:
            episode_num = int(match.group(num_group))
            title = match.group(title_group).strip()
            title = title.rstrip('.,;:')
            if title:
                return title, episode_num

    return None, None


def format_episode_header(episode_number: int, title: str, language: str) -> str:
    """
    Create TTS-friendly episode header based on language.

    Format:
        korean:    "Episode 일. 제목."
        japanese:  "第1話。제목。"
        taiwanese: "第一集。제목。"
    """
    if language == 'korean':
        korean_num = arabic_to_korean(episode_number)
        return f"Episode {korean_num}. {title}.\n\n"
    elif language == 'japanese':
        return f"第{episode_number}話。{title}。\n\n"
    elif language == 'taiwanese':
        chinese_num = arabic_to_chinese(episode_number)
        return f"第{chinese_num}集。{title}。\n\n"
    else:
        return f"Episode {episode_number}. {title}.\n\n"


def clean_header_for_tts(content: str, episode_number: int, title: str, language: str) -> str:
    """
    Clean up episode header in content for TTS-friendly format.
    Removes ALL existing episode headers and adds a single standardized header.

    Example:
        Input:  "4화. 제목.\n\n에피소드 사화.\n\n본문..."
        Output: "Episode 사. 제목.\n\n본문..."
    """
    cleaned = content

    # Korean number words
    korean_numbers = r'(?:일|이|삼|사|오|육|칠|팔|구|십|백|천|' + \
                     r'하나|둘|셋|넷|다섯|여섯|일곱|여덟|아홉|열|' + \
                     r'[일이삼사오육칠팔구십백천]+)'

    # Japanese hiragana numbers (for LLM-converted headers like だいいっしゅう, だいよんしゅう)
    # Includes all readings: いち(1), に(2), さん(3), し/よん(4), ご(5), ろく(6), しち/なな(7), はち(8), きゅう/く(9), じゅう(10)
    hiragana_numbers = r'(?:いち|に|さん|し|よん|ご|ろく|しち|なな|はち|きゅう|く|じゅう|' + \
                       r'ひゃく|せん|いっ|にっ|さっ|よっ|ごっ|ろっ|しっ|はっ|きゅっ|' + \
                       r'[いちにさんしよんごろくしちななはちきゅうくじゅうひゃくせん]+)'

    # Japanese number words
    japanese_numbers = r'(?:一|二|三|四|五|六|七|八|九|十|百|千|[一二三四五六七八九十百千]+)'

    # Remove ALL episode header patterns (may appear multiple times due to LLM formatting)
    # Apply repeatedly until no more matches

    patterns_to_remove = [
        # "Episode 일." or "Episode 1." with optional title
        r'^Episode\s+(?:\d+|' + korean_numbers + r')\s*[.。]?\s*(?:[^\n]+[.。])?\s*\n+',
        # "에피소드 일." or "에피소드 1." with optional title
        r'^에피소드\s*(?:\d+|' + korean_numbers + r')(?:화)?\s*[.。]?\s*(?:[^\n]+[.。])?\s*\n+',
        # "1화." or "제1화." with optional title
        r'^(?:제)?(?:\d+)화\s*[.。:]\s*(?:[^\n]+[.。])?\s*\n+',
        # "第1話" or "第一話" with optional title (kanji)
        r'^第(?:\d+|' + japanese_numbers + r')話\s*[.。]?\s*(?:[^\n]+[.。。])?\s*\n+',
        # "第1集" with optional title (kanji)
        r'^第(?:\d+|' + japanese_numbers + r')集\s*[.。]?\s*(?:[^\n]+[.。。])?\s*\n+',
        # Hiragana episode headers (LLM-converted): "だいいっしゅう。" "だいにしゅう。" etc.
        r'^だい' + hiragana_numbers + r'(?:しゅう|わ|か)\s*[.。]?\s*\n+',
        # Generic hiragana chapter patterns
        r'^(?:だい)?(?:' + hiragana_numbers + r')(?:しゅう|わ|か|ばん)\s*[.。]?\s*\n+',
    ]

    # Apply each pattern removal repeatedly
    for pattern in patterns_to_remove:
        prev_cleaned = None
        while prev_cleaned != cleaned:
            prev_cleaned = cleaned
            cleaned = re.sub(pattern, '', cleaned, count=1, flags=re.IGNORECASE | re.MULTILINE)

    # Remove leading whitespace
    cleaned = cleaned.lstrip('\n\r\t ')

    # Add standardized header based on language
    tts_header = format_episode_header(episode_number, title, language)
    cleaned = tts_header + cleaned

    return cleaned


def run_stage_3(
    series_folder: Path,
    target_languages: Optional[List[str]] = None,
    max_episodes: int = None
):
    """
    Run Stage 3: TTS Formatting for each target language

    Args:
        series_folder: Path to series folder
        target_languages: List of target languages (default: all 3)
        max_episodes: Maximum number of episodes to process (None = all)
    """
    if target_languages is None:
        target_languages = TARGET_LANGUAGES

    print("=" * 80)
    print("STAGE 3: TTS Formatting")
    print("=" * 80)
    print()

    stage_02_translated = series_folder / '02_translated'
    stage_03_formatted = series_folder / '03_formatted'

    if not stage_02_translated.exists():
        print(f"❌ Stage 2 output not found: {stage_02_translated}")
        print("   Please run stage_02_translate.py first")
        return False

    print(f"📁 Series: {series_folder.name}")
    print(f"🌏 Languages to format: {', '.join(target_languages)}")
    print()
    print("-" * 80)
    print()

    llm_processor = LLMProcessor()
    overall_success = True

    for target_lang in target_languages:
        print(f"\n{'='*60}")
        print(f"  Formatting {LANGUAGE_DISPLAY.get(target_lang, target_lang)}")
        print(f"{'='*60}\n")

        source_folder = stage_02_translated / target_lang
        target_folder = stage_03_formatted / target_lang

        if not source_folder.exists():
            print(f"  ⚠️  Source folder not found: {source_folder}")
            print(f"     Skipping {target_lang}...")
            continue

        target_folder.mkdir(parents=True, exist_ok=True)

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

        print(f"  📊 Episodes to format: {len(episodes)}")

        # Track progress
        failed_episodes = []
        skipped_episodes = []
        processed_count = 0

        with tqdm(total=len(episodes), desc="  Formatting", bar_format='{desc}: {n}/{total}|{bar}| [{elapsed}<{remaining}]') as pbar:
            for episode_file in episodes:
                output_file = target_folder / episode_file.name

                # Skip if already processed
                if output_file.exists():
                    try:
                        with open(output_file, 'r', encoding='utf-8') as f:
                            existing_data = json.load(f)
                            if existing_data.get('metadata', {}).get('formatting_applied'):
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
                    series_name = episode_data.get('metadata', {}).get('series_name', series_folder.name)
                    episode_number = episode_data.get('episode_number', 1)
                    current_title = episode_data.get('title')

                    # Format for TTS with retry logic
                    max_retries = 3
                    retry_delay = 10
                    formatted_text = None

                    for attempt in range(max_retries):
                        try:
                            format_result = llm_processor.execute({
                                'text': content,
                                'operation': 'format',
                                'params': {'language': target_lang}
                            })
                            formatted_text = format_result['output']
                            break
                        except Exception as e:
                            if attempt < max_retries - 1:
                                pbar.write(f"     ⚠️  Retry {attempt + 1}/{max_retries}: {e}")
                                time.sleep(retry_delay)
                            else:
                                raise

                    if formatted_text is None:
                        raise Exception("Formatting failed after retries")

                    # Handle title
                    final_title = None
                    title_source = None

                    if current_title:
                        final_title = current_title
                        title_source = 'existing'
                    else:
                        # Try to extract title
                        extracted_title, _ = extract_title_from_content(content, target_lang)
                        if extracted_title:
                            final_title = extracted_title
                            title_source = 'extracted'
                        else:
                            # Generate title using LLM
                            for attempt in range(max_retries):
                                try:
                                    title_result = llm_processor.execute({
                                        'text': formatted_text,
                                        'operation': 'generate_title',
                                        'params': {
                                            'series_name': series_name,
                                            'episode_number': episode_number,
                                            'language': target_lang
                                        }
                                    })
                                    final_title = title_result['output']
                                    title_source = 'generated'
                                    break
                                except Exception:
                                    if attempt == max_retries - 1:
                                        # Default title by language
                                        if target_lang == 'korean':
                                            final_title = f"에피소드 {episode_number}"
                                        elif target_lang == 'japanese':
                                            final_title = f"エピソード {episode_number}"
                                        elif target_lang == 'taiwanese':
                                            final_title = f"第{episode_number}集"
                                        else:
                                            final_title = f"Episode {episode_number}"
                                        title_source = 'default'

                    # Clean header for TTS-friendly format
                    if final_title:
                        formatted_text = clean_header_for_tts(
                            formatted_text, episode_number, final_title, target_lang
                        )

                    # Save formatted episode
                    episode_data['content'] = formatted_text
                    episode_data['title'] = final_title
                    episode_data['metadata']['formatting_applied'] = True
                    episode_data['metadata']['formatting_language'] = target_lang
                    episode_data['metadata']['title'] = final_title
                    episode_data['metadata']['title_source'] = title_source

                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(episode_data, f, ensure_ascii=False, indent=2)

                    processed_count += 1
                    pbar.set_postfix_str(f"{episode_file.name}")
                    pbar.update(1)

                except Exception as e:
                    pbar.write(f"     ❌ Failed {episode_file.name}: {e}")
                    failed_episodes.append((episode_file.name, str(e)))
                    pbar.update(1)

        # Summary for this language
        print()
        print(f"  {LANGUAGE_DISPLAY.get(target_lang, target_lang)} Summary:")
        print(f"    Processed: {processed_count}")
        print(f"    Skipped: {len(skipped_episodes)}")
        print(f"    Failed: {len(failed_episodes)}")

        if failed_episodes:
            overall_success = False

    print()
    print("=" * 80)
    print("Stage 3 Complete")
    print("=" * 80)
    print()

    if overall_success:
        print("✅ All formatting completed successfully!")
        print()
        print("📋 Next Steps:")
        print("   1. Review formatted files in: " + str(stage_03_formatted))
        print("   2. Run: python stage_04_tag_emotions.py")
    else:
        print("⚠️  Some formatting failed. Review and retry.")

    return overall_success


if __name__ == '__main__':
    import argparse
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(
        description='Stage 3: TTS Formatting',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python stage_03_format.py "processed/Publisher/Series"
  python stage_03_format.py "processed/Publisher/Series" --langs korean japanese

This stage:
  1. Reads translated episodes from 02_translated/{language}/
  2. Applies language-specific TTS formatting
  3. Generates episode titles if missing
  4. Outputs to 03_formatted/{language}/
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

    success = run_stage_3(series_folder, target_languages=args.langs, max_episodes=args.max_episodes)
    sys.exit(0 if success else 1)
