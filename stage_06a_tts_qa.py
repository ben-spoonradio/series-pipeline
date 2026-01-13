#!/usr/bin/env python3
"""
Stage 6A: TTS Quality Assurance
Verify TTS audio completeness using STT validation

This stage validates that TTS-generated audio files contain the complete text
by checking if the original text's last N characters appear in the transcribed
audio tail using ElevenLabs Speech-to-Text API.
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from tqdm import tqdm

from processors.tts_qa_service import TTSQAService, EpisodeQAResult


# Language configurations
LANGUAGE_CONFIG = {
    'korean': {'emoji': '🇰🇷', 'stt_code': 'ko'},
    'japanese': {'emoji': '🇯🇵', 'stt_code': 'ja'},
    'taiwanese': {'emoji': '🇹🇼', 'stt_code': 'zh'}
}


def chunk_text_for_qa(text: str, max_chars: int = 2500) -> List[str]:
    """
    Re-chunk text to match TTS chunking logic from VoiceGenerator.

    This function MUST produce the same chunks as VoiceGenerator.chunk_text()
    to ensure proper alignment between text and audio chunks.

    Note: Does NOT include SSML prefix that VoiceGenerator adds, as we're
    comparing against original text content.

    Args:
        text: Full episode text content
        max_chars: Maximum characters per chunk (must match TTS setting)

    Returns:
        List of text chunks matching TTS audio chunks
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    current_chunk = ""

    # Split by sentences (same logic as VoiceGenerator)
    sentences = text.split('.')

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        sentence = sentence + '.'

        # If adding this sentence exceeds max_chars, save current chunk
        if len(current_chunk) + len(sentence) > max_chars:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = sentence
        else:
            current_chunk += ' ' + sentence if current_chunk else sentence

    # Add final chunk
    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


def run_stage_6a(
    series_folder: Path,
    target_language: Optional[str] = None,
    max_episodes: Optional[int] = None,
    start_episode: Optional[int] = None,
    end_episode: Optional[int] = None,
    char_count: int = 10,
    segment_duration_ms: int = 3000
) -> bool:
    """
    Run Stage 6A: TTS Quality Assurance

    Args:
        series_folder: Path to series folder
        target_language: Specific language to validate (default: all available)
        max_episodes: Maximum episodes to process
        start_episode: Start from this episode number
        end_episode: End at this episode number
        char_count: Characters to compare (default: 10)
        segment_duration_ms: Audio tail length to transcribe in ms (default: 3000)

    Returns:
        True if QA completed successfully
    """
    print("=" * 80)
    print("STAGE 6A: TTS Quality Assurance")
    print("=" * 80)
    print()

    # Check for TTS output
    stage_06_tts = series_folder / '06_tts_audio'
    if not stage_06_tts.exists():
        print(f"❌ TTS output not found: {stage_06_tts}")
        print("   Please run stage_06_generate_tts.py first")
        return False

    # Find available languages
    available_langs = sorted([
        d.name for d in stage_06_tts.iterdir()
        if d.is_dir() and d.name in LANGUAGE_CONFIG
    ])

    if not available_langs:
        print(f"❌ No language folders found in {stage_06_tts}")
        return False

    # Determine languages to validate
    if target_language:
        if target_language not in available_langs:
            print(f"❌ Language '{target_language}' not found")
            print(f"   Available: {', '.join(available_langs)}")
            return False
        languages_to_validate = [target_language]
    else:
        languages_to_validate = available_langs

    print(f"📁 Series: {series_folder.name}")
    print(f"🌏 Languages: {', '.join(languages_to_validate)}")
    print(f"🔍 Comparison: last {char_count} chars, {segment_duration_ms}ms audio tail")
    print()
    print("-" * 80)

    # Create QA output directory
    qa_output_dir = series_folder / '06a_tts_qa_report'
    qa_output_dir.mkdir(parents=True, exist_ok=True)

    all_results = {}
    total_passed = 0
    total_failed = 0

    for lang in languages_to_validate:
        config = LANGUAGE_CONFIG[lang]
        emoji = config['emoji']

        print()
        print(f"{emoji} Validating: {lang.upper()}")
        print("=" * 40)

        tts_lang_dir = stage_06_tts / lang
        tagged_lang_dir = series_folder / '04_tagged' / lang

        if not tagged_lang_dir.exists():
            print(f"   ⚠️ Source text not found: {tagged_lang_dir}")
            continue

        # Find episode directories
        episode_dirs = sorted([
            d for d in tts_lang_dir.iterdir()
            if d.is_dir() and d.name.startswith('episode_')
        ])

        # Apply episode filters
        if start_episode or end_episode:
            filtered_dirs = []
            for d in episode_dirs:
                try:
                    ep_num = int(d.name.split('_')[1])
                    if start_episode and ep_num < start_episode:
                        continue
                    if end_episode and ep_num > end_episode:
                        continue
                    filtered_dirs.append(d)
                except (ValueError, IndexError):
                    continue
            episode_dirs = filtered_dirs

        if max_episodes and len(episode_dirs) > max_episodes:
            episode_dirs = episode_dirs[:max_episodes]

        if not episode_dirs:
            print(f"   ⚠️ No episodes found for {lang}")
            continue

        # Initialize QA service
        try:
            qa_service = TTSQAService(
                language=lang,
                char_count=char_count,
                segment_duration_ms=segment_duration_ms
            )
        except Exception as e:
            print(f"   ❌ Failed to initialize QA service: {e}")
            continue

        lang_results = []
        lang_passed = 0
        lang_failed = 0

        with tqdm(
            total=len(episode_dirs),
            desc=f"   Checking",
            bar_format='{desc}: {n}/{total}|{bar}| [{elapsed}<{remaining}]'
        ) as pbar:
            for episode_dir in episode_dirs:
                try:
                    ep_num = int(episode_dir.name.split('_')[1])
                except (ValueError, IndexError):
                    pbar.write(f"      ⚠️ Invalid episode directory: {episode_dir.name}")
                    pbar.update(1)
                    continue

                # Load source text
                source_file = tagged_lang_dir / f'episode_{ep_num:03d}.json'
                if not source_file.exists():
                    pbar.write(f"      ⚠️ Episode {ep_num:03d}: source not found")
                    pbar.update(1)
                    continue

                try:
                    with open(source_file, 'r', encoding='utf-8') as f:
                        episode_data = json.load(f)
                    content = episode_data.get('content', '')
                except Exception as e:
                    pbar.write(f"      ⚠️ Episode {ep_num:03d}: failed to load source - {e}")
                    pbar.update(1)
                    continue

                # Get chunk files
                chunk_files = sorted(episode_dir.glob('chunk_*.mp3'))
                if not chunk_files:
                    pbar.write(f"      ⚠️ Episode {ep_num:03d}: no chunks found")
                    pbar.update(1)
                    continue

                # Re-chunk text to match audio chunks
                chunk_texts = chunk_text_for_qa(content, max_chars=2500)

                # Verify episode
                episode_result = qa_service.verify_episode(ep_num, chunk_texts, chunk_files)
                lang_results.append(episode_result)
                lang_passed += episode_result.passed_count
                lang_failed += episode_result.failed_count

                # Report status
                status = "✅" if episode_result.passed else "❌"
                pbar.write(
                    f"      {status} Episode {ep_num:03d}: "
                    f"{episode_result.passed_count}/{episode_result.total_chunks} passed "
                    f"({episode_result.pass_rate:.1f}%)"
                )

                # Show failed chunk details if any
                if not episode_result.passed:
                    for chunk_result in episode_result.chunk_results:
                        if not chunk_result.passed:
                            chunk_name = Path(chunk_result.chunk_file).name
                            pbar.write(f"         ├─ {chunk_name}")
                            pbar.write(f"         │  Expected: '{chunk_result.original_last_chars}'")
                            if chunk_result.error:
                                pbar.write(f"         │  Error: {chunk_result.error}")
                            else:
                                pbar.write(f"         │  Got: '{chunk_result.transcribed_last_chars}'")

                pbar.update(1)

        # Language summary
        print()
        lang_total = lang_passed + lang_failed
        lang_pass_rate = (lang_passed / lang_total * 100) if lang_total > 0 else 0
        status = "✅ PASS" if lang_failed == 0 else "❌ FAIL"
        print(f"   {status} - Passed: {lang_passed}, Failed: {lang_failed} ({lang_pass_rate:.1f}%)")

        all_results[lang] = {
            'results': lang_results,
            'passed_count': lang_passed,
            'failed_count': lang_failed,
            'pass_rate': lang_pass_rate
        }

        total_passed += lang_passed
        total_failed += lang_failed

    # Generate reports
    print()
    print("-" * 80)
    print()
    print("📋 Generating QA Report...")

    report = generate_qa_report(series_folder.name, all_results)

    # Save JSON report
    report_file = qa_output_dir / 'qa_report.json'
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Save text summary
    summary_file = qa_output_dir / 'qa_summary.txt'
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(generate_text_summary(report))

    print(f"   ✅ Report saved: {report_file.name}")
    print(f"   ✅ Summary saved: {summary_file.name}")

    # Final summary
    print()
    print("=" * 80)
    total = total_passed + total_failed
    overall_rate = (total_passed / total * 100) if total > 0 else 0
    overall_pass = total_failed == 0
    status = "✅ QA PASSED" if overall_pass else "❌ QA FAILED"
    print(f"{status}")
    print("=" * 80)
    print()
    print(f"📊 Summary:")
    print(f"   Total Chunks Tested: {total}")
    print(f"   Passed: {total_passed}")
    print(f"   Failed: {total_failed}")
    print(f"   Pass Rate: {overall_rate:.1f}%")
    print()
    print(f"📂 Output: {qa_output_dir}")
    print()

    if not overall_pass:
        print("💡 Next Steps:")
        print("   1. Review qa_summary.txt for failed chunks")
        print("   2. Re-generate failed episodes with Stage 6")
        print("   3. Re-run this QA stage to verify fixes")
        print()

    return True


def generate_qa_report(series_name: str, all_results: dict) -> dict:
    """Generate detailed QA report as JSON"""
    report = {
        'series_name': series_name,
        'generated_at': datetime.now().isoformat(),
        'languages': {},
        'summary': {
            'total_chunks_tested': 0,
            'total_passed': 0,
            'total_failed': 0,
            'overall_pass_rate': 0.0
        }
    }

    total_passed = 0
    total_failed = 0

    for lang, data in all_results.items():
        lang_report = {
            'passed_count': data['passed_count'],
            'failed_count': data['failed_count'],
            'pass_rate': data['pass_rate'],
            'episodes': []
        }

        for episode_result in data['results']:
            ep_report = {
                'episode_number': episode_result.episode_number,
                'total_chunks': episode_result.total_chunks,
                'passed': episode_result.passed_count,
                'failed': episode_result.failed_count,
                'skipped': episode_result.skipped_count,
                'pass_rate': episode_result.pass_rate,
                'chunks': []
            }

            # Only include failed chunks in report to save space
            for chunk_result in episode_result.chunk_results:
                if not chunk_result.passed:
                    ep_report['chunks'].append(chunk_result.to_dict())

            lang_report['episodes'].append(ep_report)

        report['languages'][lang] = lang_report
        total_passed += data['passed_count']
        total_failed += data['failed_count']

    total = total_passed + total_failed
    report['summary'] = {
        'total_chunks_tested': total,
        'total_passed': total_passed,
        'total_failed': total_failed,
        'overall_pass_rate': (total_passed / total * 100) if total > 0 else 0.0
    }

    return report


def generate_text_summary(report: dict) -> str:
    """Generate human-readable text summary"""
    lines = []
    lines.append("=" * 60)
    lines.append(f"TTS QA Report: {report['series_name']}")
    lines.append(f"Generated: {report['generated_at']}")
    lines.append("=" * 60)
    lines.append("")

    # Overall summary
    summary = report['summary']
    status = "PASSED" if summary['total_failed'] == 0 else "FAILED"
    lines.append(f"Status: {status}")
    lines.append(f"Total Chunks Tested: {summary['total_chunks_tested']}")
    lines.append(f"Passed: {summary['total_passed']}")
    lines.append(f"Failed: {summary['total_failed']}")
    lines.append(f"Pass Rate: {summary['overall_pass_rate']:.1f}%")
    lines.append("")

    # Per-language details
    for lang, data in report['languages'].items():
        lines.append("-" * 40)
        status = "PASS" if data['failed_count'] == 0 else "FAIL"
        lines.append(f"{lang.upper()} [{status}]")
        lines.append(f"  Passed: {data['passed_count']}, Failed: {data['failed_count']} ({data['pass_rate']:.1f}%)")

        # Show failed episodes
        failed_episodes = [ep for ep in data['episodes'] if ep['failed'] > 0]
        if failed_episodes:
            lines.append("  Failed episodes:")
            for ep in failed_episodes[:10]:  # Limit to first 10
                lines.append(f"    Episode {ep['episode_number']:03d}: {ep['failed']} failed chunks")
                for chunk in ep['chunks'][:3]:  # Show first 3 failed chunks
                    chunk_name = Path(chunk['chunk_file']).name
                    lines.append(f"      - {chunk_name}")
                    lines.append(f"        Expected: '{chunk['original_last_chars']}'")
                    if chunk['error']:
                        lines.append(f"        Error: {chunk['error']}")
                    else:
                        lines.append(f"        Got: '{chunk['transcribed_last_chars']}'")
                if len(ep['chunks']) > 3:
                    lines.append(f"      ... and {len(ep['chunks']) - 3} more failed chunks")
            if len(failed_episodes) > 10:
                lines.append(f"  ... and {len(failed_episodes) - 10} more failed episodes")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


if __name__ == '__main__':
    import argparse
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(
        description='Stage 6A: TTS Quality Assurance',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python stage_06a_tts_qa.py "processed/Publisher/Series"
  python stage_06a_tts_qa.py "processed/Publisher/Series" --lang korean
  python stage_06a_tts_qa.py "processed/Publisher/Series" --max-episodes 10
  python stage_06a_tts_qa.py "processed/Publisher/Series" --start-episode 5 --end-episode 15
  python stage_06a_tts_qa.py "processed/Publisher/Series" --char-count 15 --segment-duration 5000

This stage validates:
  1. TTS audio completeness (last N chars of text appear in audio tail)
  2. STT verification using ElevenLabs Scribe API

Verification Method:
  - Extract last N characters from original text (removing markers)
  - Extract last M milliseconds from audio file
  - Transcribe audio using ElevenLabs STT
  - Check if original text ending is contained in transcription

Output:
  06a_tts_qa_report/
  ├── qa_report.json        (detailed machine-readable report)
  └── qa_summary.txt        (human-readable summary)

Requirements:
  - ELEVENLABS_API_KEY environment variable
  - TTS output from Stage 6 (06_tts_audio/{language}/)
  - Source text from Stage 4 (04_tagged/{language}/)
"""
    )

    parser.add_argument('series_folder', type=str, help='Path to series folder')
    parser.add_argument('--lang', type=str, default=None,
                        choices=['korean', 'japanese', 'taiwanese'],
                        help='Specific language to validate (default: all)')
    parser.add_argument('--max-episodes', type=int, default=None,
                        help='Maximum number of episodes to validate')
    parser.add_argument('--start-episode', type=int, default=None,
                        help='Start from this episode number')
    parser.add_argument('--end-episode', type=int, default=None,
                        help='End at this episode number')
    parser.add_argument('--char-count', type=int, default=10,
                        help='Number of characters to compare (default: 10)')
    parser.add_argument('--segment-duration', type=int, default=3000,
                        help='Audio tail duration in milliseconds (default: 3000)')

    args = parser.parse_args()

    series_folder = Path(args.series_folder)

    if not series_folder.exists():
        print(f"❌ Series folder not found: {series_folder}")
        sys.exit(1)

    success = run_stage_6a(
        series_folder,
        target_language=args.lang,
        max_episodes=args.max_episodes,
        start_episode=args.start_episode,
        end_episode=args.end_episode,
        char_count=args.char_count,
        segment_duration_ms=args.segment_duration
    )
    sys.exit(0 if success else 1)
