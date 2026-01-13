#!/usr/bin/env python3
"""
Production Pipeline with Human-in-the-Loop Review
Interactive stage-by-stage processing with review checkpoints

Supports two modes:
- Interactive mode (default): Human review after each stage
- Auto mode (--auto): Automatic processing without human intervention
"""

import sys
import time
import json
import argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import subprocess
from config import get_output_dir, get_source_dir


class PipelineStats:
    """Track pipeline execution statistics"""

    def __init__(self):
        self.start_time = time.time()
        self.stages_completed = []
        self.stages_failed = []
        self.stages_skipped = []
        self.api_calls = 0
        self.api_wait_time = 0.0
        self.last_api_call = None
        self.by_stage = defaultdict(lambda: {
            'status': 'pending',
            'start_time': None,
            'end_time': None,
            'duration': 0,
            'output_files': 0,
            'error': None
        })
        self.series_info = {}

    def start_stage(self, stage_num):
        """Mark stage as started"""
        self.by_stage[stage_num]['status'] = 'running'
        self.by_stage[stage_num]['start_time'] = time.time()

    def complete_stage(self, stage_num, output_files=0):
        """Mark stage as completed"""
        self.by_stage[stage_num]['status'] = 'completed'
        self.by_stage[stage_num]['end_time'] = time.time()
        self.by_stage[stage_num]['duration'] = (
            self.by_stage[stage_num]['end_time'] -
            self.by_stage[stage_num]['start_time']
        )
        self.by_stage[stage_num]['output_files'] = output_files
        self.stages_completed.append(stage_num)

    def fail_stage(self, stage_num, error=None):
        """Mark stage as failed"""
        self.by_stage[stage_num]['status'] = 'failed'
        self.by_stage[stage_num]['end_time'] = time.time()
        if self.by_stage[stage_num]['start_time']:
            self.by_stage[stage_num]['duration'] = (
                self.by_stage[stage_num]['end_time'] -
                self.by_stage[stage_num]['start_time']
            )
        self.by_stage[stage_num]['error'] = error
        self.stages_failed.append(stage_num)

    def skip_stage(self, stage_num):
        """Mark stage as skipped"""
        self.by_stage[stage_num]['status'] = 'skipped'
        self.stages_skipped.append(stage_num)

    def get_total_duration(self):
        """Get total pipeline duration"""
        return time.time() - self.start_time

    def to_dict(self):
        """Convert stats to dictionary for JSON serialization"""
        return {
            'start_time': datetime.fromtimestamp(self.start_time).isoformat(),
            'total_duration_seconds': self.get_total_duration(),
            'total_duration_minutes': self.get_total_duration() / 60,
            'stages_completed': self.stages_completed,
            'stages_failed': self.stages_failed,
            'stages_skipped': self.stages_skipped,
            'api_calls': self.api_calls,
            'api_wait_time_seconds': self.api_wait_time,
            'by_stage': dict(self.by_stage),
            'series_info': self.series_info
        }


def wait_for_rate_limit(stats: PipelineStats, interval: float = 6.0):
    """Wait if needed to respect API rate limits"""
    if stats.last_api_call is not None:
        elapsed = time.time() - stats.last_api_call
        if elapsed < interval:
            wait_time = interval - elapsed
            print(f"  ⏳ Rate limiting: waiting {wait_time:.1f}s...")
            time.sleep(wait_time)
            stats.api_wait_time += wait_time
    stats.last_api_call = time.time()
    stats.api_calls += 1

def print_banner(text):
    """Print formatted banner"""
    print()
    print("=" * 80)
    print(f"  {text}")
    print("=" * 80)
    print()

def print_stage_info(stage_num, stage_name, description):
    """Print stage information"""
    print(f"📍 Stage {stage_num}: {stage_name}")
    print(f"   {description}")
    print()

def run_command(command, log_file=None):
    """Run shell command and return success status"""
    if log_file:
        # Use bash pipefail to capture real exit code from stage script, not tee
        command_str = f"bash -c 'set -o pipefail; {command} 2>&1 | tee {log_file}'"
    else:
        command_str = command

    result = subprocess.run(
        command_str,
        shell=True,
        env={'PYTHONUNBUFFERED': '1', **dict(subprocess.os.environ)}
    )

    return result.returncode == 0

def get_user_choice(prompt, options):
    """Get user choice from options"""
    print()
    print(prompt)
    for key, desc in options.items():
        print(f"  [{key}] {desc}")
    print()

    while True:
        choice = input("Your choice: ").strip().lower()
        if choice in options:
            return choice
        print(f"Invalid choice. Please choose from: {', '.join(options.keys())}")

def generate_qa_report(stats: PipelineStats, series_folder: Path, output_path: Path = None):
    """Generate QA report in Markdown and JSON formats"""
    if output_path is None:
        output_path = series_folder / 'pipeline_qa_report.md'

    report = []

    # Header
    report.append("# Pipeline QA Report")
    report.append(f"\n**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"**Series:** {stats.series_info.get('series_name', 'Unknown')}")
    report.append(f"**Publisher:** {stats.series_info.get('publisher', 'Unknown')}")
    report.append("\n---\n")

    # Executive Summary
    report.append("## Executive Summary\n")
    report.append(f"- **Total Duration:** {stats.get_total_duration():.1f}s ({stats.get_total_duration()/60:.1f}min)")
    report.append(f"- **Stages Completed:** {len(stats.stages_completed)}/8")
    report.append(f"- **Stages Failed:** {len(stats.stages_failed)}")
    report.append(f"- **Stages Skipped:** {len(stats.stages_skipped)}")
    report.append(f"- **API Calls:** {stats.api_calls}")
    report.append(f"- **API Wait Time:** {stats.api_wait_time:.1f}s")
    report.append("\n---\n")

    # Stage Details
    report.append("## Stage Details\n")
    report.append("| Stage | Name | Status | Duration | Output Files |")
    report.append("|-------|------|--------|----------|--------------|")

    stage_names = {
        0: 'File Preparation',
        1: 'Episode Splitting',
        2: 'Translation',
        '2a': 'Translation QA',
        3: 'TTS Formatting',
        '3a': 'Speaker Tagging',
        4: 'Emotion Tagging',
        5: 'Audio Setup',
        6: 'TTS Generation',
        '6a': 'TTS QA',
        7: 'Audio Mixing'
    }

    for stage_num in [0, 1, 2, '2a', 3, '3a', 4, 5, 6, '6a', 7]:
        stage_data = stats.by_stage.get(stage_num, {})
        status = stage_data.get('status', 'pending')
        duration = stage_data.get('duration', 0)
        output_files = stage_data.get('output_files', 0)

        status_emoji = {
            'completed': '✅',
            'failed': '❌',
            'skipped': '⏭️',
            'pending': '⏳',
            'running': '🔄'
        }.get(status, '❓')

        report.append(
            f"| {stage_num} | {stage_names.get(stage_num, 'Unknown')} | "
            f"{status_emoji} {status} | {duration:.1f}s | {output_files} |"
        )

    report.append("\n---\n")

    # Errors (if any)
    errors = [(num, stats.by_stage[num].get('error'))
              for num in stats.stages_failed
              if stats.by_stage[num].get('error')]
    if errors:
        report.append("## Errors\n")
        for stage_num, error in errors:
            report.append(f"### Stage {stage_num}: {stage_names.get(stage_num, 'Unknown')}")
            report.append(f"```\n{error}\n```\n")
        report.append("---\n")

    # Series Info
    if stats.series_info:
        report.append("## Series Information\n")
        for key, value in stats.series_info.items():
            report.append(f"- **{key}:** {value}")
        report.append("\n")

    # Write Markdown report
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))

    # Write JSON report
    json_path = output_path.with_suffix('.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(stats.to_dict(), f, ensure_ascii=False, indent=2)

    print(f"📝 QA Report: {output_path}")
    print(f"📊 JSON Data: {json_path}")

    return output_path, json_path


def run_pipeline(source_file: Path, auto_mode: bool = False, skip_stages: set = None,
                 rate_limit: float = 6.0, qa_report: bool = False, stop_on_error: bool = False,
                 max_episodes: int = None, apply_mastering: bool = False,
                 peak_db: float = -3.0, rms_db: float = -20.0, review_output: bool = False,
                 review_output_dir: Path = None, use_preset_audio: bool = False,
                 langs: str = None):
    """
    Run complete pipeline with optional human review checkpoints

    Args:
        source_file: Path to source file
        auto_mode: If True, skip all human review checkpoints
        skip_stages: Set of stage numbers to skip
        rate_limit: Seconds between API calls (default: 6.0)
        qa_report: If True, generate QA report at end
        stop_on_error: If True, stop pipeline on first error (auto mode only)
        max_episodes: Maximum number of episodes to process for TTS (stages 5-7)
        review_output: If True, generate human-readable review files in _review/
        review_output_dir: Custom directory for review output (e.g., Google Drive path)
        use_preset_audio: If True, use preset voice_id from CSV and existing music files
        langs: Comma-separated list of languages to process (e.g., "korean,japanese")
    """
    skip_stages = skip_stages or set()
    stats = PipelineStats()

    # Initialize review generator if enabled
    review_generator = None

    mode_label = "Auto Mode" if auto_mode else "Human-in-the-Loop"
    print_banner(f"🚀 Production Pipeline - {mode_label}")

    # Derive language_code and publisher from source path
    # Structure: _SOURCE/{language_code}/{publisher}/{series_folder}/file.docx
    # e.g., _SOURCE/KR/PEEX/사랑의 빚/사랑의 빚.docx
    source_dir = get_source_dir()

    # Resolve both paths to handle symlinks and normalize
    # Use NFC normalization to handle macOS NFD vs NFC unicode differences
    import unicodedata
    source_file_resolved = Path(unicodedata.normalize('NFC', str(source_file.resolve())))
    source_dir_resolved = Path(unicodedata.normalize('NFC', str(source_dir.resolve())))

    try:
        relative_parts = source_file_resolved.relative_to(source_dir_resolved).parts
        # relative_parts = (KR, PEEX, 사랑의 빚, 사랑의 빚.docx)
        language_code = relative_parts[0] if len(relative_parts) > 0 else 'Unknown'
        publisher = relative_parts[1] if len(relative_parts) > 1 else 'Unknown'
    except ValueError:
        # File is not under source_dir, use fallback
        language_code = 'Unknown'
        publisher = 'Unknown'
    initial_series_name = source_file.stem

    print(f"📁 Source: {source_file}")
    print(f"🌍 Language: {language_code}")
    print(f"📚 Publisher: {publisher}")
    print(f"📖 Initial Series Name: {initial_series_name}")
    if auto_mode:
        print(f"⚙️  Rate Limit: {rate_limit}s between API calls")
        if skip_stages:
            print(f"⏭️  Skipping stages: {sorted(skip_stages)}")
    if max_episodes:
        print(f"🎯 Max Episodes for TTS: {max_episodes}")
    if apply_mastering:
        print(f"🎚️  Mastering: Peak={peak_db}dB, RMS={rms_db}LUFS")
    print()

    # Store series info in stats
    stats.series_info['language_code'] = language_code
    stats.series_info['publisher'] = publisher
    stats.series_info['initial_series_name'] = initial_series_name
    stats.series_info['source_file'] = str(source_file)

    # Note: series_folder will be determined after Stage 0 runs
    # Stage 0 matches metadata and creates the folder with the matched series name
    series_folder = None  # Will be set after Stage 0

    def get_series_folder():
        """Get series folder after Stage 0 completes by reading series_metadata.json"""
        # Output structure: _PROCESSED/{language_code}/{publisher}/{series_name}/
        # e.g., _PROCESSED/KR/PEEX/사랑의 빚/
        base_dir = get_output_dir() / language_code / publisher
        if base_dir.exists():
            # Find the folder containing series_metadata.json that matches our source file
            for folder in base_dir.iterdir():
                if not folder.is_dir():
                    continue
                metadata_file = folder / 'series_metadata.json'
                if metadata_file.exists():
                    try:
                        with open(metadata_file, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                        # Check if this metadata matches our source file
                        metadata_source = metadata.get('source_file', '')
                        if source_file.name in metadata_source or initial_series_name in metadata.get('series_name', ''):
                            return folder
                    except Exception:
                        continue

            # Fallback: find folder with series_metadata.json modified most recently
            # (but only if it was modified within last 60 seconds to avoid picking wrong folder)
            import time
            current_time = time.time()
            recent_folders = []
            for folder in base_dir.iterdir():
                if not folder.is_dir():
                    continue
                metadata_file = folder / 'series_metadata.json'
                if metadata_file.exists():
                    mtime = metadata_file.stat().st_mtime
                    if current_time - mtime < 60:  # Modified within last 60 seconds
                        recent_folders.append((folder, mtime))

            if recent_folders:
                # Return the most recently modified
                return max(recent_folders, key=lambda x: x[1])[0]

        return None

    # Build --langs flag string for stage scripts
    # Convert comma-separated to space-separated for argparse nargs='+'
    langs_flag = f' --langs {langs.replace(",", " ")}' if langs else ''

    def make_stages(series_folder):
        """Generate stage configurations with actual series_folder"""
        return [
            {
                'number': 0,
                'name': 'File Preparation',
                'description': 'Convert source file, match metadata, and detect source language',
                'script': f'python stage_00_prepare.py "{source_file}"',
                'log': 'stage_00_prepare.log',
                'output_dir': series_folder if series_folder else get_output_dir() / publisher / initial_series_name,
                'review_prompt': 'Review metadata match, converted text, and detected source language.',
                'output_check': lambda d: (d / 'series_metadata.json').exists(),
            },
            {
                'number': 1,
                'name': 'Episode Splitting',
                'description': 'Split source file into episodes',
                'script': f'python stage_01_split.py "{source_file}"',
                'log': 'stage_01_split.log',
                'output_dir': series_folder / '01_split' if series_folder else None,
                'review_prompt': 'Review episode splits. Check episode boundaries and content.',
            },
            {
                'number': 2,
                'name': 'Translation',
                'description': 'Translate to target languages' + (f' ({langs})' if langs else ' (Korean, Japanese, Taiwanese)'),
                'script': (f'python stage_02_translate.py "{series_folder}"' +
                          (' --auto' if auto_mode else '') +
                          (f' --max-episodes {max_episodes}' if max_episodes else '') +
                          langs_flag) if series_folder else None,
                'log': 'stage_02_translate.log',
                'output_dir': series_folder / '02_translated' if series_folder else None,
                'review_prompt': 'Review translations. Check quality and term consistency for each language.',
                'output_check': lambda d: any(d.iterdir()) if d.exists() else False,
            },
            {
                'number': '2a',
                'name': 'Translation QA',
                'description': 'Validate translation quality and fix issues',
                'script': (f'python stage_02a_translation_qa.py "{series_folder}" --auto-fix' +
                          langs_flag) if series_folder else None,
                'log': 'stage_02a_translation_qa.log',
                'output_dir': series_folder / '02a_qa_report' if series_folder else None,
                'review_prompt': 'Review translation QA results. Check for language mixing and glossary consistency.',
                'output_check': lambda d: (d / 'qa_report.json').exists() if d and d.exists() else False,
            },
            {
                'number': 3,
                'name': 'TTS Formatting',
                'description': 'Format text for optimal TTS synthesis per language',
                'script': (f'python stage_03_format.py "{series_folder}"' +
                          (f' --max-episodes {max_episodes}' if max_episodes else '') +
                          langs_flag) if series_folder else None,
                'log': 'stage_03_format.log',
                'output_dir': series_folder / '03_formatted' if series_folder else None,
                'review_prompt': 'Review TTS formatting for each language. Check text optimization quality.',
                'output_check': lambda d: any(d.iterdir()) if d.exists() else False,
            },
            {
                'number': '3a',
                'name': 'Speaker Tagging',
                'description': 'Extract characters and tag speakers in dialogue',
                'script': (f'python stage_03a_speaker_tagging.py "{series_folder}"' +
                          (f' --max-episodes {max_episodes}' if max_episodes else '') +
                          langs_flag) if series_folder else None,
                'log': 'stage_03a_speaker_tagging.log',
                'output_dir': series_folder / '03a_speaker_tagged' if series_folder else None,
                'review_prompt': 'Review speaker tagging results. Check character dictionary and tagged dialogues.',
                'output_check': lambda d: any(d.iterdir()) if d and d.exists() else False,
            },
            {
                'number': 4,
                'name': 'Emotion Tagging',
                'description': 'Add emotion tags for expressive TTS per language',
                'script': (f'python stage_04_tag_emotions.py "{series_folder}"' +
                          (f' --max-episodes {max_episodes}' if max_episodes else '') +
                          langs_flag) if series_folder else None,
                'log': 'stage_04_tag_emotions.log',
                'output_dir': series_folder / '04_tagged' if series_folder else None,
                'review_prompt': 'Review emotion tags for each language. Check tag placement and quality.',
                'output_check': lambda d: any(d.iterdir()) if d.exists() else False,
            },
            {
                'number': 5,
                'name': 'Audio Setup',
                'description': 'Create voice profiles and audio configuration' + (' (preset mode)' if use_preset_audio else ''),
                'script': (f'python stage_05_setup_audio.py "{series_folder}"' +
                          (' --use-preset' if use_preset_audio else '') +
                          langs_flag) if series_folder else None,
                'log': 'stage_05_setup_audio.log',
                'output_dir': series_folder / '05_audio_setup' if series_folder else None,
                'review_prompt': 'Review voice character description and audio config.',
                'output_check': lambda d: (d / 'audio_config.json').exists() if d.exists() else False,
            },
            {
                'number': 6,
                'name': 'TTS Generation',
                'description': f'Generate TTS audio from text{f" (max {max_episodes} episodes)" if max_episodes else ""}',
                'script': (f'python stage_06_generate_tts.py "{series_folder}"' +
                          (f' --max-episodes {max_episodes}' if max_episodes else '') +
                          langs_flag) if series_folder else None,
                'log': 'stage_06_generate_tts.log',
                'output_dir': series_folder / '06_tts_audio' if series_folder else None,
                'review_prompt': 'Review generated TTS audio chunks.',
                'output_check': lambda d: any(d.iterdir()) if d.exists() else False,
            },
            {
                'number': '6a',
                'name': 'TTS QA',
                'description': 'Validate TTS audio completeness',
                'script': (f'python stage_06a_tts_qa.py "{series_folder}"' +
                          langs_flag) if series_folder else None,
                'log': 'stage_06a_tts_qa.log',
                'output_dir': series_folder / '06a_tts_qa_report' if series_folder else None,
                'review_prompt': 'Review TTS QA results. Check for missing or incomplete audio.',
                'output_check': lambda d: (d / 'qa_report.json').exists() if d and d.exists() else False,
            },
            {
                'number': 7,
                'name': 'Audio Mixing',
                'description': f'Mix voice with background music{f" (max {max_episodes} episodes)" if max_episodes else ""}{" + mastering" if apply_mastering else ""}',
                'script': (f'python stage_07_mix_audio.py "{series_folder}"' +
                          (f' --max-episodes {max_episodes}' if max_episodes else '') +
                          (f' --master --peak-db {peak_db} --rms-db {rms_db}' if apply_mastering else '') +
                          langs_flag) if series_folder else None,
                'log': 'stage_07_mix_audio.log',
                'output_dir': series_folder / '07_final_audio' if series_folder else None,
                'review_prompt': 'Review final mixed audio files.',
                'output_check': lambda d: len(list(d.glob('*.mp3'))) > 0 if d.exists() else False,
            },
        ]

    # Initialize stages with None series_folder
    stages = make_stages(series_folder)

    current_stage = 0

    while current_stage < len(stages):
        stage = stages[current_stage]
        stage_num = stage['number']

        # Check if stage should be skipped (user-requested)
        if stage_num in skip_stages:
            print(f"⏭️  Skipping Stage {stage_num}: {stage['name']} (user-requested)")
            stats.skip_stage(stage_num)
            current_stage += 1
            continue

        print_banner(f"Stage {stage_num}: {stage['name']}")
        print_stage_info(stage_num, stage['name'], stage['description'])

        # Check if stage already completed
        if stage['output_dir'] and stage['output_dir'].exists():
            # Use custom check if provided, otherwise check for JSON files
            if 'output_check' in stage:
                stage_complete = stage['output_check'](stage['output_dir'])
            else:
                files_count = len(list(stage['output_dir'].glob('*.json')))
                stage_complete = files_count > 0

            if stage_complete:
                if 'output_check' in stage:
                    print(f"⚠️  Stage {stage_num} output already exists")
                else:
                    files_count = len(list(stage['output_dir'].glob('*.json')))
                    print(f"⚠️  Stage {stage_num} output already exists ({files_count} files)")
                print(f"📂 {stage['output_dir']}")
                print()

                if auto_mode:
                    # Auto mode: skip existing stages
                    print("  → Auto mode: skipping to next stage")
                    stats.skip_stage(stage_num)
                    current_stage += 1
                    continue
                else:
                    choice = get_user_choice(
                        "What would you like to do?",
                        {
                            'r': 'Rerun this stage (will overwrite)',
                            's': 'Skip to next stage',
                            'a': 'Abort pipeline',
                        }
                    )

                    if choice == 'a':
                        print("Pipeline aborted by user")
                        return False, stats
                    elif choice == 's':
                        stats.skip_stage(stage_num)
                        current_stage += 1
                        continue

        # Apply rate limiting before LLM-heavy stages (1-6, including QA stages)
        if auto_mode and stage_num in [1, 2, '2a', 3, '3a', 4, 5, 6, '6a']:
            wait_for_rate_limit(stats, rate_limit)

        # Run stage
        print(f"▶️  Running Stage {stage_num}...")
        print()

        stats.start_stage(stage_num)
        success = run_command(stage['script'], stage['log'])

        if not success:
            print()
            print(f"❌ Stage {stage_num} failed!")
            print(f"📄 Check log: {stage['log']}")
            print()

            # Read error from log file
            log_path = Path(stage['log'])
            error_msg = None
            if log_path.exists():
                try:
                    with open(log_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        # Get last 10 lines as error context
                        error_msg = ''.join(lines[-10:])
                except Exception:
                    pass

            stats.fail_stage(stage_num, error_msg)

            # Generate review output even for failed stages (if partial output exists)
            if review_output and review_generator and stage_num in [1, 2, 3, '3a', 4, 5]:
                try:
                    if review_generator.generate_stage_review(stage_num):
                        print(f"   📝 Review files generated for Stage {stage_num} (with failures marked)")
                except Exception as e:
                    print(f"   ⚠️  Failed to generate review for Stage {stage_num}: {e}")

            if auto_mode:
                if stop_on_error:
                    print("  → Auto mode: stopping due to error (--stop-on-error)")
                    return False, stats
                else:
                    print("  → Auto mode: continuing to next stage despite error")
                    current_stage += 1
                    continue
            else:
                choice = get_user_choice(
                    "What would you like to do?",
                    {
                        'r': 'Retry this stage',
                        'a': 'Abort pipeline',
                    }
                )

                if choice == 'a':
                    print("Pipeline aborted due to failure")
                    return False, stats
                # 'r' will loop back and retry
                continue

        # Stage completed successfully - count output files
        output_files = 0
        if stage['output_dir'] and stage['output_dir'].exists():
            if stage_num == 7:
                output_files = len(list(stage['output_dir'].glob('*.mp3')))
            elif stage_num == 6:
                output_files = len([d for d in stage['output_dir'].iterdir() if d.is_dir()])
            else:
                output_files = len(list(stage['output_dir'].glob('*.json')))

        stats.complete_stage(stage_num, output_files)

        print()
        print(f"✅ Stage {stage_num} completed successfully!")
        print(f"📂 Output: {stage['output_dir']}")
        print()

        # Special handling after Stage 0: update series_folder
        if stage_num == 0 and series_folder is None:
            series_folder = get_series_folder()
            if series_folder:
                print(f"📂 Series folder determined: {series_folder}")
                print(f"📖 Series name: {series_folder.name}")
                # Regenerate stages with actual series_folder
                stages = make_stages(series_folder)
                # Update stats with series info
                stats.series_info['series_name'] = series_folder.name
                stats.series_info['series_folder'] = str(series_folder)
                # Initialize review generator if enabled
                if review_output:
                    from processors.review_generator import ReviewGenerator
                    review_generator = ReviewGenerator(series_folder, output_dir=review_output_dir)
                    print(f"📝 Review output enabled: {review_generator.review_dir}")
                print()
            else:
                print("⚠️  Warning: Could not determine series folder after Stage 0")
                print()

        # Generate review output if enabled (for stages 1-5)
        if review_output and review_generator and stage_num in [1, 2, 3, '3a', 4, 5]:
            try:
                if review_generator.generate_stage_review(stage_num):
                    print(f"   📝 Review files generated for Stage {stage_num}")
            except Exception as e:
                print(f"   ⚠️  Failed to generate review for Stage {stage_num}: {e}")

        # Human review checkpoint (skip in auto mode)
        if auto_mode:
            print("  → Auto mode: proceeding to next stage")
            current_stage += 1
        else:
            print("-" * 80)
            print(f"🔍 REVIEW CHECKPOINT")
            print(f"   {stage['review_prompt']}")
            print("-" * 80)

            # Build options - add 's' (sync) if review output is enabled
            options = {
                'c': 'Continue to next stage',
                'r': 'Redo this stage',
                'e': 'Edit files and redo',
                'a': 'Abort pipeline',
            }
            if review_output and review_generator and stage_num in [1, 2, 3, '3a', 4]:
                options['s'] = 'Sync review changes to processed and continue'

            choice = get_user_choice(
                "Review the output and choose next action:",
                options
            )

            if choice == 'a':
                print("Pipeline aborted by user")
                return False, stats
            elif choice == 's':
                # Sync review changes back to processed
                print()
                print("🔄 Syncing review changes to processed files...")
                try:
                    from processors.reverse_sync import ReverseSync
                    syncer = ReverseSync(review_generator.review_dir, series_folder)

                    if stage_num in [2, 3, '3a', 4]:
                        # Stages with language subdirectories
                        for lang in ['korean', 'japanese', 'taiwanese']:
                            syncer.sync_stage(stage_num, lang)
                    else:
                        # Stage 1 (no language)
                        syncer.sync_stage(stage_num)

                    print()
                    print("✅ Sync completed")
                except Exception as e:
                    print(f"❌ Sync failed: {e}")

                current_stage += 1
            elif choice == 'c':
                current_stage += 1
            elif choice == 'e':
                print()
                print(f"📂 Edit files in: {stage['output_dir']}")
                input("Press Enter when editing is complete...")
                # Loop back to rerun stage
            # 'r' or 'e' will loop back and rerun the stage

    # All stages complete
    print_banner("🎉 Pipeline Complete!")

    print("All stages completed successfully!")
    print()
    print("📊 Output Summary:")
    for stage in stages:
        if stage['output_dir'] and stage['output_dir'].exists():
            if stage['number'] == 7:
                # Audio files
                files_count = len(list(stage['output_dir'].glob('*.mp3')))
                print(f"   Stage {stage['number']}: {files_count} audio files in {stage['output_dir']}")
            elif stage['number'] == 6:
                # Episode directories
                dirs_count = len([d for d in stage['output_dir'].iterdir() if d.is_dir()])
                print(f"   Stage {stage['number']}: {dirs_count} episodes in {stage['output_dir']}")
            elif stage['number'] == 5:
                # Config file
                print(f"   Stage {stage['number']}: audio_config.json in {stage['output_dir']}")
            else:
                # JSON files
                files_count = len(list(stage['output_dir'].glob('*.json')))
                print(f"   Stage {stage['number']}: {files_count} files in {stage['output_dir']}")
    print()

    # Check for glossaries
    if series_folder:
        glossaries = list(series_folder.glob('glossary_*.json'))
        if glossaries:
            print(f"📚 Glossaries: {len(glossaries)} files")
            for g in glossaries:
                print(f"   - {g.name}")
            print()

    # Check for final audio
    if series_folder:
        final_audio_dir = series_folder / '07_final_audio'
        if final_audio_dir.exists():
            audio_files = list(final_audio_dir.glob('*.mp3'))
            if audio_files:
                print(f"🎧 Final Audio: {len(audio_files)} files in {final_audio_dir}")
                print()

    # Print statistics summary
    print("📈 Pipeline Statistics:")
    print(f"   Total Duration: {stats.get_total_duration():.1f}s ({stats.get_total_duration()/60:.1f}min)")
    print(f"   Stages Completed: {len(stats.stages_completed)}")
    print(f"   Stages Skipped: {len(stats.stages_skipped)}")
    print(f"   Stages Failed: {len(stats.stages_failed)}")
    if auto_mode:
        print(f"   API Calls: {stats.api_calls}")
        print(f"   API Wait Time: {stats.api_wait_time:.1f}s")
    print()

    # Generate QA report if requested
    if qa_report and series_folder:
        generate_qa_report(stats, series_folder)

    return True, stats

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Production Pipeline with Human-in-the-Loop Review',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Pipeline Stages:
  0.  File Preparation - Convert file, match metadata, detect source language
  1.  Episode Splitting - Split into episodes
  2.  Translation - Translate to 3 languages (Korean, Japanese, Taiwanese)
  2a. Translation QA - Validate translation quality and fix issues
  3.  TTS Formatting - Optimize text for TTS per language
  3a. Speaker Tagging - Extract characters and tag speakers in dialogue
  4.  Emotion Tagging - Add emotional context per language
  5.  Audio Setup - Create voice profiles and audio config
  6.  TTS Generation - Generate audio from text
  6a. TTS QA - Validate TTS audio completeness
  7.  Audio Mixing - Mix voice with background music

Data Flow:
  Source (KR/JP) → Split → Translate → QA → Format → Tag Speakers → Emotion → Audio

  02_translated/{korean,japanese,taiwanese}/
  02a_qa_report/
  03_formatted/{korean,japanese,taiwanese}/
  03a_speaker_tagged/{korean,japanese,taiwanese}/
  04_tagged/{korean,japanese,taiwanese}/

Examples:
  # Interactive mode (default)
  python pipeline.py "source/KR/Peex/버추얼러브.docx"

  # Auto mode with QA report
  python pipeline.py "source/KR/Peex/버추얼러브.docx" --auto --qa-report

  # Auto mode, skip audio stages (text processing only)
  python pipeline.py "source/KR/Peex/버추얼러브.docx" --auto --skip-stages 5,6,6a,7

  # Auto mode, skip QA stages
  python pipeline.py "source/KR/Peex/버추얼러브.docx" --auto --skip-stages 2a,3a,6a

  # Auto mode with custom rate limit
  python pipeline.py "source/KR/Peex/버추얼러브.docx" --auto --rate-limit 3.0

  # Auto mode with human-readable review output
  python pipeline.py "source/KR/Peex/버추얼러브.docx" --auto --review-output

  # Auto mode with review output to Google Drive
  python pipeline.py "source/KR/Peex/버추얼러브.docx" --auto --review-output-dir "/Users/user/Library/CloudStorage/GoogleDrive-user@example.com/공유 드라이브/Spoon Series"

  # Process Japanese source file
  python pipeline.py "source/JP/Publisher/novel.txt" --auto
"""
    )

    parser.add_argument('source_file', type=str, help='Path to source file (DOCX/PDF/TXT/HWP)')
    parser.add_argument('--auto', action='store_true',
                        help='Auto mode: skip all human review checkpoints')
    parser.add_argument('--skip-stages', type=str, default='',
                        help='Comma-separated list of stages to skip (e.g., "2a,3a,6a" or "5,6,6a,7")')
    parser.add_argument('--rate-limit', type=float, default=6.0,
                        help='Seconds between API calls in auto mode (default: 6.0)')
    parser.add_argument('--qa-report', action='store_true',
                        help='Generate QA report (Markdown + JSON) at end')
    parser.add_argument('--stop-on-error', action='store_true',
                        help='Stop pipeline on first error (auto mode only, default: continue)')
    parser.add_argument('--max-episodes', type=int, default=None,
                        help='Maximum number of episodes to generate TTS/audio (e.g., 30)')
    parser.add_argument('--master', action='store_true',
                        help='Apply audio mastering (peak/RMS normalization for audiobook standards)')
    parser.add_argument('--peak-db', type=float, default=-3.0,
                        help='Target peak level in dB (default: -3.0)')
    parser.add_argument('--rms-db', type=float, default=-20.0,
                        help='Target RMS level in LUFS (default: -20.0)')
    parser.add_argument('--review-output', action='store_true',
                        help='Generate human-readable review files in _review/ directory')
    parser.add_argument('--review-output-dir', type=str, default=None,
                        help='Custom directory for review output (e.g., Google Drive path)')
    parser.add_argument('--use-preset-audio', action='store_true',
                        help='Use preset voice_id from CSV and existing music files (skip Voice Design API)')
    parser.add_argument('--langs', type=str, default=None,
                        help='Comma-separated list of languages to process (e.g., "korean,japanese")')

    args = parser.parse_args()

    source_file = Path(args.source_file)

    if not source_file.exists():
        print(f"❌ Source file not found: {source_file}")
        sys.exit(1)

    # Parse skip stages (supports both integers and strings like '2a', '3a', '6a')
    skip_stages = set()
    if args.skip_stages:
        for s in args.skip_stages.split(','):
            s = s.strip()
            if not s:
                continue
            # Try to parse as integer, otherwise keep as string
            try:
                skip_stages.add(int(s))
            except ValueError:
                skip_stages.add(s)  # Keep as string (e.g., '2a', '3a', '6a')

    # Parse review output directory
    review_output_dir = Path(args.review_output_dir) if args.review_output_dir else None

    # Auto-enable review_output if review_output_dir is provided
    review_output = args.review_output or (review_output_dir is not None)

    # Run pipeline
    result = run_pipeline(
        source_file,
        auto_mode=args.auto,
        skip_stages=skip_stages,
        rate_limit=args.rate_limit,
        qa_report=args.qa_report,
        stop_on_error=args.stop_on_error,
        max_episodes=args.max_episodes,
        apply_mastering=args.master,
        peak_db=args.peak_db,
        rms_db=args.rms_db,
        review_output=review_output,
        review_output_dir=review_output_dir,
        use_preset_audio=args.use_preset_audio,
        langs=args.langs
    )

    # Handle return value (tuple in new version)
    if isinstance(result, tuple):
        success, stats = result
    else:
        success = result

    sys.exit(0 if success else 1)
