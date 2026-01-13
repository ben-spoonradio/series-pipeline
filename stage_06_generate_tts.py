#!/usr/bin/env python3
"""
Stage 6: TTS Generation
Generate audio files from text using ElevenLabs TTS
"""

import sys
import json
import os
from pathlib import Path
from tqdm import tqdm
from processors.voice_generator import VoiceGenerator

def run_stage_6(series_folder: Path, voice_id: str = None, max_episodes: int = None, source_language: str = None):
    """Run Stage 6: TTS Generation

    Args:
        series_folder: Path to series folder
        voice_id: Override voice ID (optional)
        max_episodes: Limit number of episodes to generate
        source_language: Target language (korean, japanese, taiwanese)
    """

    print("=" * 80)
    print("STAGE 6: TTS Generation")
    print("=" * 80)
    print()

    # Load audio configuration (new structure: 05_audio_setup/{language}/audio_config.json)
    stage_05_audio = series_folder / '05_audio_setup'

    if not stage_05_audio.exists():
        print(f"❌ Audio setup not found: {stage_05_audio}")
        print("   Please run stage_05_setup_audio.py first")
        return False

    # Find available language configs
    lang_configs = sorted([d for d in stage_05_audio.iterdir() if d.is_dir() and (d / 'audio_config.json').exists()])

    if not lang_configs:
        # Fallback: check for old single-file structure
        old_config = stage_05_audio / 'audio_config.json'
        if old_config.exists():
            with open(old_config, 'r', encoding='utf-8') as f:
                audio_config = json.load(f)
            source_lang = audio_config['source_language']
            config_file = old_config
        else:
            print(f"❌ No language configurations found in {stage_05_audio}")
            print("   Please run stage_05_setup_audio.py first")
            return False
    else:
        # Check if language was specified via --lang
        if source_language:
            config_dir = stage_05_audio / source_language
            if not (config_dir / 'audio_config.json').exists():
                print(f"❌ Language '{source_language}' not found in {stage_05_audio}")
                print(f"   Available: {', '.join([d.name for d in lang_configs])}")
                return False
        elif len(lang_configs) == 1:
            config_dir = lang_configs[0]
        else:
            # Interactive selection
            print("Available languages:")
            for i, d in enumerate(lang_configs, 1):
                emoji = {'korean': '🇰🇷', 'japanese': '🇯🇵', 'taiwanese': '🇹🇼'}.get(d.name, '🌏')
                print(f"  {i}. {emoji} {d.name}")
            print()
            while True:
                choice = input(f"Select language (1-{len(lang_configs)}): ").strip()
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(lang_configs):
                        config_dir = lang_configs[idx]
                        break
                except ValueError:
                    pass
                print("❌ Invalid choice")

        config_file = config_dir / 'audio_config.json'
        with open(config_file, 'r', encoding='utf-8') as f:
            audio_config = json.load(f)
        source_lang = audio_config['source_language']
        print(f"📂 Using config: {config_file}")
        print()

    # Determine source stage (always from 04_tagged/{language}/)
    source_stage = series_folder / '04_tagged' / source_lang

    if not source_stage.exists():
        print(f"❌ Source not found: {source_stage}")
        print("   Please run stage_04_tag_emotions.py first")
        return False

    # Get all episode files
    episodes = sorted(source_stage.glob('episode_*.json'))

    # Apply max_episodes limit if specified
    if max_episodes and len(episodes) > max_episodes:
        episodes = episodes[:max_episodes]

    if not episodes:
        print(f"❌ No episode files found in {source_stage}")
        return False

    print(f"📁 Series: {series_folder.name}")
    print(f"📊 Episodes to generate: {len(episodes)}" + (f" (limited to {max_episodes})" if max_episodes else ""))
    print(f"🌏 Source: {source_stage.name}")
    print()

    # Get voice ID (priority: CLI arg > config file > interactive prompt)
    config_voice_id = audio_config.get('voice_id')

    if voice_id is None:
        if config_voice_id:
            # Auto-read from config
            voice_id = config_voice_id
            print(f"🎤 Using Voice ID from config: {voice_id}")
            print()
        else:
            # Fallback to interactive prompt
            print("🎤 Voice ID Setup:")
            print("   Enter the ElevenLabs Voice ID to use for narration")
            print("   (You can create a custom voice using the voice description from Stage 5)")
            print()
            voice_id = input("Voice ID: ").strip()
            print()

    if not voice_id:
        print("❌ Voice ID is required")
        print("   Options:")
        print("   1. Run Stage 5 with ELEVENLABS_API_KEY to auto-generate voice")
        print("   2. Pass --voice-id argument")
        print("   3. Update audio_config.json with voice_id field")
        return False

    # Create output directory (language-specific: 06_tts_audio/{language}/)
    stage_06_tts = series_folder / '06_tts_audio' / source_lang
    stage_06_tts.mkdir(parents=True, exist_ok=True)

    print("-" * 80)
    print()

    # Initialize voice generator
    try:
        voice_generator = VoiceGenerator()
    except Exception as e:
        print(f"❌ Failed to initialize VoiceGenerator: {e}")
        print("   Make sure ELEVENLABS_API_KEY is set in your .env file")
        return False

    # Get voice settings from config
    voice_settings = audio_config.get('voice_settings', {})

    # Process each episode
    with tqdm(total=len(episodes), desc="  Generating TTS", bar_format='{desc}: {n}/{total}|{bar}| [{elapsed}<{remaining}]') as pbar:
        for episode_file in episodes:
            try:
                # Load episode
                with open(episode_file, 'r', encoding='utf-8') as f:
                    episode_data = json.load(f)

                episode_num = episode_data['episode_number']
                episode_title = episode_data.get('title', f'Episode {episode_num}')
                content = episode_data['content']

                pbar.write(f"     🎙️ Episode {episode_num:03d}: {episode_title}")
                pbar.write(f"        📝 Content: {len(content):,} chars")

                # Create episode output directory
                episode_dir = stage_06_tts / f"episode_{episode_num:03d}"
                episode_dir.mkdir(parents=True, exist_ok=True)

                # Generate TTS chunks
                pbar.write(f"        🎤 Generating audio chunks...")

                try:
                    # Use content directly from Stage 4 (already formatted in Stage 3)
                    chunk_files = voice_generator.generate_speech_chunks(
                        text=content,
                        voice_id=voice_id,
                        output_dir=episode_dir,
                        max_chars=2500,
                        **voice_settings
                    )

                    pbar.write(f"        ✅ Generated {len(chunk_files)} audio chunks")

                    # Save episode metadata
                    episode_metadata = {
                        'episode_number': episode_num,
                        'title': episode_title,
                        'source_language': source_lang,
                        'voice_id': voice_id,
                        'content_length': len(content),
                        'chunk_count': len(chunk_files),
                        'chunk_files': [str(f.name) for f in chunk_files],
                        'voice_settings': voice_settings
                    }

                    metadata_file = episode_dir / 'metadata.json'
                    with open(metadata_file, 'w', encoding='utf-8') as f:
                        json.dump(episode_metadata, f, ensure_ascii=False, indent=2)

                except Exception as e:
                    pbar.write(f"        ❌ TTS generation failed: {e}")
                    continue

                pbar.update(1)

            except Exception as e:
                pbar.write(f"     ❌ Failed to process {episode_file.name}: {e}")
                continue

    print()
    print("=" * 80)
    print(f"✅ Stage 6 Complete: TTS audio generated")
    print("=" * 80)
    print()
    print("📋 Next Steps:")
    print("   1. Review generated audio chunks: " + str(stage_06_tts))
    print("   2. Run Stage 7 to concatenate chunks and add background music")
    print()

    return True

if __name__ == '__main__':
    import argparse
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(
        description='Stage 6: TTS Generation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python stage_06_generate_tts.py "processed/Peex/버추얼 러브"
  python stage_06_generate_tts.py "processed/Peex/버추얼 러브" --lang korean
  python stage_06_generate_tts.py "processed/Peex/버추얼 러브" --lang japanese --max-episodes 5
  python stage_06_generate_tts.py "processed/Peex/버추얼 러브" --voice-id "21m00Tcm4TlvDq8ikWAM"

Voice ID Priority:
  1. --voice-id argument (highest priority)
  2. voice_id from 05_audio_setup/{lang}/audio_config.json
  3. Interactive prompt (if not found in config)

Note:
  - Voice ID will be automatically read from language-specific config
  - Set ELEVENLABS_API_KEY in your .env file
"""
    )

    parser.add_argument('series_folder', type=str, help='Path to series folder')
    parser.add_argument('--lang', type=str, default=None,
                        choices=['korean', 'japanese', 'taiwanese'],
                        help='Target language (default: interactive selection)')
    parser.add_argument('--voice-id', type=str, default=None,
                        help='ElevenLabs Voice ID (overrides config)')
    parser.add_argument('--max-episodes', type=int, default=None,
                        help='Maximum number of episodes to generate (e.g., 30)')

    args = parser.parse_args()

    series_folder = Path(args.series_folder)

    if not series_folder.exists():
        print(f"❌ Series folder not found: {series_folder}")
        sys.exit(1)

    success = run_stage_6(series_folder, args.voice_id, args.max_episodes, args.lang)
    sys.exit(0 if success else 1)
