#!/usr/bin/env python3
"""
Stage 7: Audio Mixing
Concatenate TTS chunks and optionally add background music
"""

import sys
import json
from pathlib import Path
from tqdm import tqdm
from processors.audio_mixer import AudioMixer

def run_stage_7(series_folder: Path, music_file: Path = None, add_music: bool = None, max_episodes: int = None,
                apply_mastering: bool = False, peak_db: float = -3.0, rms_db: float = -20.0,
                source_language: str = None):
    """Run Stage 7: Audio Mixing and optional Mastering"""

    print("=" * 80)
    print("STAGE 7: Audio Mixing")
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
            source_lang = audio_config.get('source_language', 'korean')
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

    # Check TTS audio (language-specific: 06_tts_audio/{language}/)
    stage_06_tts = series_folder / '06_tts_audio' / source_lang

    if not stage_06_tts.exists():
        print(f"❌ TTS audio not found: {stage_06_tts}")
        print("   Please run stage_06_generate_tts.py first")
        return False

    # Get all episode directories
    episode_dirs = sorted([d for d in stage_06_tts.iterdir() if d.is_dir() and d.name.startswith('episode_')])

    # Apply max_episodes limit if specified
    if max_episodes and len(episode_dirs) > max_episodes:
        episode_dirs = episode_dirs[:max_episodes]

    if not episode_dirs:
        print(f"❌ No episode audio found in {stage_06_tts}")
        return False

    print(f"📁 Series: {series_folder.name}")
    print(f"📊 Episodes to mix: {len(episode_dirs)}" + (f" (limited to {max_episodes})" if max_episodes else ""))
    if apply_mastering:
        print(f"🎚️  Mastering: Peak={peak_db}dB, RMS={rms_db}LUFS")
    print()

    # Music setup
    if add_music is None:
        print("🎵 Background Music:")
        print("   Add background music to episodes?")
        print()
        choice = input("Add music? (y/n): ").strip().lower()
        add_music = choice == 'y'
        print()

    if add_music:
        if music_file is None:
            print("   Enter path to background music file (MP3):")
            music_path = input("   Music file: ").strip()
            music_file = Path(music_path) if music_path else None
            print()

        if music_file and not music_file.exists():
            print(f"   ⚠️  Music file not found: {music_file}")
            print("   Proceeding without background music")
            add_music = False
            music_file = None
        elif music_file:
            print(f"   ✅ Using music: {music_file.name}")
            print()

    # Create output directory (language-specific: 07_final_audio/{language}/)
    stage_07_final = series_folder / '07_final_audio' / source_lang
    stage_07_final.mkdir(parents=True, exist_ok=True)

    print("-" * 80)
    print()

    # Initialize audio mixer
    audio_mixer = AudioMixer(
        temp_folder=series_folder / 'temp_audio',
        output_folder=stage_07_final
    )

    # Check ffmpeg availability
    if not audio_mixer.check_ffmpeg():
        print("⚠️  Warning: FFmpeg not available")
        print("   Will use pydub only (may have limited functionality)")
        print()

    # Get audio settings from config
    gap_duration_ms = audio_config.get('audio_settings', {}).get('gap_duration_ms', 1000)
    music_volume = audio_config.get('audio_settings', {}).get('music_volume', 0.3)
    fade_duration = audio_config.get('audio_settings', {}).get('fade_duration', 5.0)
    intro_music_duration = audio_config.get('audio_settings', {}).get('intro_music_duration', 30.0)
    outro_music_duration = audio_config.get('audio_settings', {}).get('outro_music_duration', 30.0)
    voice_start_delay = audio_config.get('audio_settings', {}).get('voice_start_delay', 5.0)

    # Process each episode
    with tqdm(total=len(episode_dirs), desc="  Mixing audio", bar_format='{desc}: {n}/{total}|{bar}| [{elapsed}<{remaining}]') as pbar:
        for episode_dir in episode_dirs:
            try:
                # Load episode metadata
                metadata_file = episode_dir / 'metadata.json'
                if not metadata_file.exists():
                    pbar.write(f"     ⚠️  Skipping {episode_dir.name}: No metadata")
                    pbar.update(1)
                    continue

                with open(metadata_file, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)

                episode_num = metadata['episode_number']
                episode_title = metadata.get('title', f'Episode {episode_num}')

                pbar.write(f"     🎧 Episode {episode_num:03d}: {episode_title}")

                # Get chunk files
                chunk_files = [episode_dir / f for f in metadata.get('chunk_files', [])]
                chunk_files = [f for f in chunk_files if f.exists()]

                if not chunk_files:
                    pbar.write(f"        ⚠️  No audio chunks found")
                    pbar.update(1)
                    continue

                pbar.write(f"        📦 Concatenating {len(chunk_files)} chunks...")

                # Concatenate chunks
                voice_only_file = stage_07_final / f"episode_{episode_num:03d}_voice.mp3"

                success = audio_mixer.concatenate_audio_files(
                    audio_files=chunk_files,
                    output_file=voice_only_file,
                    gap_duration_ms=gap_duration_ms
                )

                if not success:
                    pbar.write(f"        ❌ Concatenation failed")
                    pbar.update(1)
                    continue

                pbar.write(f"        ✅ Voice concatenated: {voice_only_file.name}")

                # Mix with music if requested (intro/outro style)
                if add_music and music_file:
                    pbar.write(f"        🎵 Mixing with intro/outro music...")

                    final_file = stage_07_final / f"episode_{episode_num:03d}_final.mp3"

                    success = audio_mixer.mix_voice_with_intro_outro_music(
                        voice_file=voice_only_file,
                        music_file=music_file,
                        output_file=final_file,
                        intro_music_duration=intro_music_duration,
                        outro_music_duration=outro_music_duration,
                        voice_start_delay=voice_start_delay,
                        fade_duration=fade_duration,
                        music_volume=music_volume
                    )

                    if success:
                        pbar.write(f"        ✅ Final mix saved: {final_file.name}")
                    else:
                        pbar.write(f"        ⚠️  Music mixing failed, using voice-only")
                else:
                    # Copy voice-only as final
                    final_file = stage_07_final / f"episode_{episode_num:03d}_final.mp3"
                    if voice_only_file != final_file:
                        import shutil
                        shutil.copy2(voice_only_file, final_file)
                        pbar.write(f"        ✅ Final saved: {final_file.name}")

                # Apply mastering if requested
                if apply_mastering:
                    pbar.write(f"        🎚️  Applying mastering...")
                    mastered_file = stage_07_final / f"episode_{episode_num:03d}_mastered.mp3"

                    mastering_success = audio_mixer.master_audio(
                        input_file=final_file,
                        output_file=mastered_file,
                        target_peak_db=peak_db,
                        target_rms_db=rms_db
                    )

                    if mastering_success:
                        pbar.write(f"        ✅ Mastered: {mastered_file.name}")
                    else:
                        pbar.write(f"        ⚠️  Mastering failed, keeping unmastered version")

                pbar.update(1)

            except Exception as e:
                pbar.write(f"     ❌ Failed to process {episode_dir.name}: {e}")
                pbar.update(1)
                continue

    print()
    print("=" * 80)
    print(f"✅ Stage 7 Complete: Audio mixed")
    print("=" * 80)
    print()
    print("📋 Results:")
    print("   - Final audio files: " + str(stage_07_final))
    print(f"   - Total episodes: {len(episode_dirs)}")
    if add_music and music_file:
        print(f"   - Background music: {music_file.name}")
    if apply_mastering:
        print(f"   - Mastering applied: Peak={peak_db}dB, RMS={rms_db}LUFS")
    print()
    print("🎉 Audio pipeline complete!")
    print()

    return True

if __name__ == '__main__':
    import argparse
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(
        description='Stage 7: Audio Mixing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python stage_07_mix_audio.py "processed/Peex/버추얼 러브"
  python stage_07_mix_audio.py "processed/Peex/버추얼 러브" --lang korean
  python stage_07_mix_audio.py "processed/Peex/버추얼 러브" --music "music/background.mp3"
  python stage_07_mix_audio.py "processed/Peex/버추얼 러브" --no-music
  python stage_07_mix_audio.py "processed/Peex/버추얼 러브" --max-episodes 30
  python stage_07_mix_audio.py "processed/Peex/버추얼 러브" --master
  python stage_07_mix_audio.py "processed/Peex/버추얼 러브" --master --peak-db -2.0 --rms-db -18.0
"""
    )

    parser.add_argument('series_folder', type=str, help='Path to series folder')
    parser.add_argument('--lang', type=str, default=None,
                        choices=['korean', 'japanese', 'taiwanese'],
                        help='Target language (default: interactive selection)')
    parser.add_argument('--music', type=str, default=None,
                        help='Path to background music file (MP3)')
    parser.add_argument('--no-music', action='store_true',
                        help='Skip background music')
    parser.add_argument('--max-episodes', type=int, default=None,
                        help='Maximum number of episodes to mix (e.g., 30)')
    parser.add_argument('--master', action='store_true',
                        help='Apply audio mastering (peak/RMS normalization)')
    parser.add_argument('--peak-db', type=float, default=-3.0,
                        help='Target peak level in dB (default: -3.0)')
    parser.add_argument('--rms-db', type=float, default=-20.0,
                        help='Target RMS level in LUFS (default: -20.0)')

    args = parser.parse_args()

    series_folder = Path(args.series_folder)

    if not series_folder.exists():
        print(f"❌ Series folder not found: {series_folder}")
        sys.exit(1)

    # Determine music settings
    music_file = Path(args.music) if args.music else None
    add_music = False if args.no_music else (True if args.music else None)

    success = run_stage_7(
        series_folder,
        music_file,
        add_music,
        args.max_episodes,
        apply_mastering=args.master,
        peak_db=args.peak_db,
        rms_db=args.rms_db,
        source_language=args.lang
    )
    sys.exit(0 if success else 1)
