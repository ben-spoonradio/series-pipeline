#!/usr/bin/env python3
"""
Stage 4: Emotion Tagging
Add emotion tags to formatted text for expressive TTS per target language.

Input: 03a_speaker_tagged/{language}/ (preferred) or 03_formatted/{language}/
Output: 04_tagged/{language}/
"""

import sys
import json
import time
from pathlib import Path
from typing import List, Optional
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


def run_stage_4(
    series_folder: Path,
    target_languages: Optional[List[str]] = None,
    max_episodes: int = None
):
    """
    Run Stage 4: Emotion Tagging for each target language

    Args:
        series_folder: Path to series folder
        target_languages: List of target languages (default: all 3)
    """
    if target_languages is None:
        target_languages = TARGET_LANGUAGES

    print("=" * 80)
    print("STAGE 4: Emotion Tagging")
    print("=" * 80)
    print()

    # Try 03a_speaker_tagged first, fallback to 03_formatted
    stage_03a_tagged = series_folder / '03a_speaker_tagged'
    stage_03_formatted = series_folder / '03_formatted'
    stage_04_tagged = series_folder / '04_tagged'

    # Determine input folder (prefer speaker-tagged if available)
    if stage_03a_tagged.exists():
        input_folder = stage_03a_tagged
        print(f"📂 Using speaker-tagged input: {stage_03a_tagged.name}")
    elif stage_03_formatted.exists():
        input_folder = stage_03_formatted
        print(f"📂 Using formatted input: {stage_03_formatted.name}")
        print("   💡 Tip: Run stage_03a_speaker_tagging.py first for speaker tags")
    else:
        print(f"❌ No input found. Expected:")
        print(f"   - {stage_03a_tagged}")
        print(f"   - {stage_03_formatted}")
        print("   Please run stage_03_format.py first")
        return False

    print(f"📁 Series: {series_folder.name}")
    print(f"🌏 Languages to tag: {', '.join(target_languages)}")
    print()
    print("-" * 80)
    print()

    llm_processor = LLMProcessor()
    overall_success = True

    for target_lang in target_languages:
        print(f"\n{'='*60}")
        print(f"  Tagging Emotions for {LANGUAGE_DISPLAY.get(target_lang, target_lang)}")
        print(f"{'='*60}\n")

        source_folder = input_folder / target_lang
        target_folder = stage_04_tagged / target_lang

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

        print(f"  📊 Episodes to tag: {len(episodes)}")

        # Track progress
        failed_episodes = []
        skipped_episodes = []
        processed_count = 0

        with tqdm(total=len(episodes), desc="  Tagging", bar_format='{desc}: {n}/{total}|{bar}| [{elapsed}<{remaining}]') as pbar:
            for episode_file in episodes:
                output_file = target_folder / episode_file.name

                # Skip if already processed
                if output_file.exists():
                    try:
                        with open(output_file, 'r', encoding='utf-8') as f:
                            existing_data = json.load(f)
                            if existing_data.get('metadata', {}).get('emotion_tags_applied'):
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

                    # Tag emotions with retry logic
                    max_retries = 3
                    retry_delay = 10
                    tagged_text = None

                    for attempt in range(max_retries):
                        try:
                            tag_result = llm_processor.execute({
                                'text': content,
                                'operation': 'tag',
                                'params': {'language': target_lang}
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
                        raise Exception("Emotion tagging failed after retries")

                    # Save tagged episode
                    episode_data['content'] = tagged_text
                    episode_data['metadata']['emotion_tags_applied'] = True
                    episode_data['metadata']['emotion_tagging_language'] = target_lang

                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(episode_data, f, ensure_ascii=False, indent=2)

                    processed_count += 1
                    pbar.set_postfix_str(f"{episode_file.name}")
                    pbar.update(1)

                except Exception as e:
                    pbar.write(f"     ❌ Failed {episode_file.name}: {e}")
                    failed_episodes.append((episode_file.name, str(e)))

                    # Save failed episode without emotion tags (preserve original content)
                    try:
                        with open(episode_file, 'r', encoding='utf-8') as f:
                            episode_data = json.load(f)

                        episode_data['metadata']['emotion_tags_applied'] = False
                        episode_data['metadata']['emotion_tagging_failed'] = True
                        episode_data['metadata']['emotion_tagging_error'] = str(e)[:200]  # Truncate long errors
                        episode_data['metadata']['emotion_tagging_language'] = target_lang

                        with open(output_file, 'w', encoding='utf-8') as f:
                            json.dump(episode_data, f, ensure_ascii=False, indent=2)

                        pbar.write(f"     💾 Saved {episode_file.name} without emotion tags")
                    except Exception as save_error:
                        pbar.write(f"     ⚠️  Could not save fallback: {save_error}")

                    pbar.update(1)

        # Summary for this language
        print()
        print(f"  {LANGUAGE_DISPLAY.get(target_lang, target_lang)} Summary:")
        print(f"    Processed: {processed_count}")
        print(f"    Skipped: {len(skipped_episodes)}")
        print(f"    Failed: {len(failed_episodes)}")

        if failed_episodes:
            overall_success = False
            print(f"    ⚠️  Failed episodes:")
            for ep_name, error in failed_episodes[:5]:
                print(f"       - {ep_name}: {error}")

    print()
    print("=" * 80)
    print("Stage 4 Complete")
    print("=" * 80)
    print()

    if overall_success:
        print("✅ All emotion tagging completed successfully!")
        print()
        print("📋 Next Steps:")
        print("   1. Review tagged files in: " + str(stage_04_tagged))
        print("   2. Check emotion tag placement and quality")
        print("   3. Run: python stage_05_setup_audio.py")
    else:
        print("⚠️  Some emotion tagging failed. Review and retry.")

    return overall_success


if __name__ == '__main__':
    import argparse
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(
        description='Stage 4: Emotion Tagging',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python stage_04_tag_emotions.py "processed/Publisher/Series"
  python stage_04_tag_emotions.py "processed/Publisher/Series" --langs korean japanese

This stage:
  1. Reads episodes from 03a_speaker_tagged/{language}/ (or 03_formatted/{language}/)
  2. Applies emotion tags for expressive TTS
  3. Outputs to 04_tagged/{language}/

Run stage_03a_speaker_tagging.py first for speaker-tagged input.
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

    success = run_stage_4(series_folder, target_languages=args.langs, max_episodes=args.max_episodes)
    sys.exit(0 if success else 1)
