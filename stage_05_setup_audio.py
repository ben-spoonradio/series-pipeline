#!/usr/bin/env python3
"""
Stage 5: Audio Setup
Create voice profiles and audio configuration for the series
Automatically generates voice using ElevenLabs Voice Design API
"""

import sys
import json
import os
from pathlib import Path
from processors.llm_processor import LLMProcessor
from processors.voice_generator import VoiceGenerator
from processors.prompts import VOICE_TEMPLATE_NARRATIVE, VOICE_TEMPLATE_EMOTIONAL

# Country code mapping for voice names
COUNTRY_CODES = {
    'korean': 'KR',
    'japanese': 'JP',
    'taiwanese': 'TW'
}

# Sample texts for voice preview (min 100 chars required by ElevenLabs API)
SAMPLE_TEXTS = {
    'korean': "안녕하세요, 여러분. 저는 오디오북 내레이터입니다. 오늘 여러분께 아름다운 이야기를 들려드리겠습니다. 따뜻하고 편안한 목소리로 여러분을 이야기 속 세계로 안내해 드릴게요. 함께 떠나볼까요?",
    'japanese': "こんにちは、皆さん。私はオーディオブックのナレーターです。今日は皆さんに美しい物語をお届けします。温かく落ち着いた声で、物語の世界へとご案内いたします。心に響く言葉を大切に紡ぎながら、一緒に旅に出かけましょう。どうぞ、ゆっくりとお聴きください。",
    'taiwanese': "大家好，我是有聲書的旁白。今天我要為大家講述一個美麗的故事。我會用溫暖舒適的聲音，帶領大家進入故事的世界。每一個字句都承載著情感與溫度，希望這段故事能夠觸動您的心靈。現在，請放鬆心情，讓我們一起開始這段美好的旅程吧。"
}


def select_voice_template(template_type: str) -> str:
    """
    Select English voice template based on template type.

    Args:
        template_type: 'narrative' or 'emotional'

    Returns:
        Voice template string
    """
    if template_type == 'emotional':
        return VOICE_TEMPLATE_EMOTIONAL
    return VOICE_TEMPLATE_NARRATIVE

def parse_voice_description_output(output: str) -> tuple[str, str]:
    """
    Parse voice description output to extract description and characteristic keyword.

    Expected format:
        [voice description text]
        ---
        [characteristic keyword]

    Returns:
        (description, characteristic) tuple
    """
    if '---' in output:
        parts = output.split('---')
        description = parts[0].strip()
        characteristic = parts[1].strip() if len(parts) > 1 else '내레이터'
        # Clean up characteristic (remove quotes, extra whitespace)
        characteristic = characteristic.strip('"\'').strip()
        # Limit characteristic length
        if len(characteristic) > 10:
            characteristic = characteristic[:10]
    else:
        # Fallback: use full output as description, default characteristic
        description = output.strip()
        characteristic = '내레이터'

    return description, characteristic

def select_source_stage(series_folder: Path):
    """Interactive source selection from 04_tagged/{language}/"""
    print("=" * 80)
    print("Select Source Language for Audio Setup")
    print("=" * 80)
    print()

    # Find available tagged languages in 04_tagged/
    stage_04_tagged = series_folder / '04_tagged'
    if not stage_04_tagged.exists():
        print(f"❌ Stage 4 output not found: {stage_04_tagged}")
        print("   Please run stage_04_tag_emotions.py first")
        return None, None

    langs = sorted([d.name for d in stage_04_tagged.iterdir() if d.is_dir()])
    if not langs:
        print(f"❌ No language folders found in {stage_04_tagged}")
        return None, None

    print("Available languages:")
    for i, lang in enumerate(langs, 1):
        emoji = {'korean': '🇰🇷', 'japanese': '🇯🇵', 'taiwanese': '🇹🇼'}.get(lang, '🌏')
        print(f"  {i}. {emoji} {lang.replace('_', ' ').title()}")
    print()

    while True:
        lang_choice = input(f"Select language (1-{len(langs)}): ").strip()
        try:
            lang_idx = int(lang_choice) - 1
            if 0 <= lang_idx < len(langs):
                source_lang = langs[lang_idx]
                source_stage = stage_04_tagged / source_lang
                break
            else:
                print("❌ Invalid choice")
        except ValueError:
            print("❌ Invalid input")

    print(f"\n✅ Using: {source_stage} ({source_lang})\n")
    return source_stage, source_lang

def run_stage_5_preset(series_folder: Path, source_language: str = None):
    """Run Stage 5 with preset voice_id and existing music files.

    This is a simplified audio setup that uses:
    - Preset voice_id from series_metadata.json (from IP LIST.csv's default_voice_id column)
    - Existing music files from {series_folder}/music/ folder

    Args:
        series_folder: Path to series folder
        source_language: Target language for voice (korean, japanese, taiwanese, or 'all')

    Returns:
        bool: True if successful, False otherwise
    """
    print("=" * 80)
    print("STAGE 5: Audio Setup (Preset Mode)")
    print("=" * 80)
    print()

    # Find available languages in 04_tagged/
    stage_04_tagged = series_folder / '04_tagged'
    if not stage_04_tagged.exists():
        print(f"❌ Stage 4 output not found: {stage_04_tagged}")
        print("   Please run stage_04_tag_emotions.py first")
        return False

    available_langs = sorted([d.name for d in stage_04_tagged.iterdir() if d.is_dir()])
    if not available_langs:
        print(f"❌ No language folders found in {stage_04_tagged}")
        return False

    # Determine which languages to process
    if source_language == 'all':
        languages_to_process = available_langs
        print(f"🌏 Processing ALL available languages: {', '.join(languages_to_process)}")
    elif source_language is None:
        # Interactive selection
        source_stage, source_lang = select_source_stage(series_folder)
        if source_stage is None:
            return False
        languages_to_process = [source_lang]
    else:
        if source_language not in available_langs:
            print(f"❌ Language '{source_language}' not found in {stage_04_tagged}")
            print(f"   Available: {', '.join(available_langs)}")
            return False
        languages_to_process = [source_language]

    print()

    # Step 1: Load series_metadata.json to get voice_ids
    print("📝 Loading series metadata...")
    metadata_file = series_folder / 'series_metadata.json'
    if not metadata_file.exists():
        print(f"❌ series_metadata.json not found: {metadata_file}")
        return False

    with open(metadata_file, 'r', encoding='utf-8') as f:
        series_metadata = json.load(f)

    # Language-specific voice_id mapping
    voice_id_map = {
        'korean': series_metadata.get('default_voice_id'),
        'japanese': series_metadata.get('default_voice_id_jp'),
        'taiwanese': series_metadata.get('default_voice_id'),  # TW uses same as KR
    }

    # Check if at least one voice_id exists for the languages to process
    missing_voices = [lang for lang in languages_to_process if not voice_id_map.get(lang)]
    if missing_voices:
        print(f"⚠️  Missing voice_id for languages: {', '.join(missing_voices)}")
        print("   Available voice_ids:")
        print(f"     - default_voice_id (KR/TW): {series_metadata.get('default_voice_id') or 'Not set'}")
        print(f"     - default_voice_id_jp (JP): {series_metadata.get('default_voice_id_jp') or 'Not set'}")

    # Show loaded voice_ids
    for lang in languages_to_process:
        voice_id = voice_id_map.get(lang)
        if voice_id:
            print(f"   ✅ {lang.upper()} Voice ID: {voice_id}")

    # Step 2: Find music file in {series_folder}/music/
    print()
    print("🎵 Looking for music files...")
    music_folder = series_folder / 'music'
    music_file = None
    music_relative_path = None

    if music_folder.exists():
        music_files = list(music_folder.glob('*.mp3')) + list(music_folder.glob('*.wav'))
        if music_files:
            music_file = music_files[0]  # Use first file
            music_relative_path = f'../../music/{music_file.name}'
            print(f"   ✅ Found: {music_file.name}")
            if len(music_files) > 1:
                print(f"   ℹ️  Multiple files found, using first: {music_file.name}")
        else:
            print(f"   ⚠️  No music files (.mp3/.wav) found in {music_folder}")
    else:
        print(f"   ⚠️  Music folder not found: {music_folder}")

    # Step 3: Create audio_config.json for each language
    print()
    print("=" * 80)

    stage_05_audio = series_folder / '05_audio_setup'
    stage_05_audio.mkdir(parents=True, exist_ok=True)

    for lang in languages_to_process:
        print()
        emoji = {'korean': '🇰🇷', 'japanese': '🇯🇵', 'taiwanese': '🇹🇼'}.get(lang, '🌏')
        print(f"{emoji} Creating config for: {lang.upper()}")

        # Get language-specific voice_id
        lang_voice_id = voice_id_map.get(lang)
        if not lang_voice_id:
            print(f"   ⚠️  Skipping {lang}: no voice_id configured")
            continue

        lang_output_dir = stage_05_audio / lang
        lang_output_dir.mkdir(parents=True, exist_ok=True)

        country_code = COUNTRY_CODES.get(lang, 'XX')
        lang_config = {
            'series_name': series_folder.name,
            'source_language': lang,
            'country_code': country_code,
            'voice_id': lang_voice_id,
            'voice_settings': {
                'stability': 0.5,
                'similarity_boost': 0.75,
                'style': 0.0,
                'use_speaker_boost': True
            },
            'audio_settings': {
                'gap_duration_ms': 1000,
                'music_volume': 0.3,
                'fade_duration': 5.0,
                'intro_music_duration': 30.0,
                'outro_music_duration': 30.0,
                'voice_start_delay': 5.0
            },
            'music_file': music_relative_path,
            'preset_mode': True
        }

        config_file = lang_output_dir / 'audio_config.json'
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(lang_config, f, ensure_ascii=False, indent=2)

        print(f"   ✅ Config saved: {lang}/audio_config.json")

    # Summary
    print()
    print("=" * 80)
    print("✅ Stage 5 Complete: Audio Setup (Preset Mode)")
    print("=" * 80)
    print()
    print("📂 Output Structure:")
    print(f"   {stage_05_audio}/")
    for lang in languages_to_process:
        print(f"   ├── {lang}/")
        print(f"   │   └── audio_config.json")
    print()
    print(f"🎤 Voice ID: {voice_id}")
    if music_file:
        print(f"🎵 Music: {music_file.name}")
    else:
        print(f"🎵 Music: Not configured")
    print()
    print("🎉 Stage 6 will use these settings automatically.")
    print()

    return True


def run_stage_5(series_folder: Path, source_language: str = None, skip_voice_api: bool = False, use_preset: bool = False):
    """Run Stage 5: Audio Setup

    Args:
        series_folder: Path to series folder
        source_language: Target language for voice (korean, japanese, taiwanese, or 'all')
        skip_voice_api: If True, skip ElevenLabs Voice Design API call (manual workflow)
        use_preset: If True, use preset voice_id from CSV and existing music files
    """
    # Branch: Use preset mode if requested
    if use_preset:
        return run_stage_5_preset(series_folder, source_language)

    print("=" * 80)
    print("STAGE 5: Audio Setup")
    print("=" * 80)
    print()

    # Find available languages in 04_tagged/
    stage_04_tagged = series_folder / '04_tagged'
    if not stage_04_tagged.exists():
        print(f"❌ Stage 4 output not found: {stage_04_tagged}")
        print("   Please run stage_04_tag_emotions.py first")
        return False

    available_langs = sorted([d.name for d in stage_04_tagged.iterdir() if d.is_dir()])
    if not available_langs:
        print(f"❌ No language folders found in {stage_04_tagged}")
        return False

    # Determine which languages to process
    if source_language == 'all':
        languages_to_process = available_langs
        print(f"🌏 Processing ALL available languages: {', '.join(languages_to_process)}")
    elif source_language is None:
        # Interactive selection
        source_stage, source_lang = select_source_stage(series_folder)
        if source_stage is None:
            return False
        languages_to_process = [source_lang]
    else:
        if source_language not in available_langs:
            print(f"❌ Language '{source_language}' not found in {stage_04_tagged}")
            print(f"   Available: {', '.join(available_langs)}")
            return False
        languages_to_process = [source_language]

    print()

    stage_05_audio = series_folder / '05_audio_setup'
    stage_05_audio.mkdir(parents=True, exist_ok=True)

    print(f"📁 Series: {series_folder.name}")
    print()

    # Step 1: Load series synopsis from series_metadata.json (shared across languages)
    print("  📝 Loading series synopsis from metadata...")
    series_metadata_file = series_folder / 'series_metadata.json'
    series_summary = None
    genre = 'web novel'

    if series_metadata_file.exists():
        try:
            with open(series_metadata_file, 'r', encoding='utf-8') as f:
                series_metadata = json.load(f)
            series_summary = series_metadata.get('synopsis', '')
            genre = series_metadata.get('genre', 'web novel')
            if series_summary:
                print(f"     ✅ Synopsis loaded ({len(series_summary)} chars)")
            else:
                print(f"     ⚠️  No synopsis found in series_metadata.json")
        except Exception as e:
            print(f"     ⚠️  Failed to load series_metadata.json: {e}")
    else:
        print(f"     ⚠️  series_metadata.json not found")

    # Fallback: Generate summary from first available episode
    if not series_summary:
        first_lang = languages_to_process[0]
        first_source = series_folder / '04_tagged' / first_lang
        episodes = sorted(first_source.glob('episode_*.json'))
        if episodes:
            with open(episodes[0], 'r', encoding='utf-8') as f:
                episode_data = json.load(f)
            content = episode_data['content']
            print("  📝 Generating series summary from Episode 1 (fallback)...")
            llm_processor = LLMProcessor()
            summary_result = llm_processor.execute({
                'text': content,
                'operation': 'summarize_series',
                'params': {
                    'series_name': series_folder.name,
                    'sample_text': content[:5000]
                }
            })
            series_summary = summary_result['output']
            print(f"     ✅ Summary generated ({len(series_summary)} chars)")

    print()
    print("-" * 80)
    print()
    print("📋 Series Summary:")
    print()
    print(series_summary)
    print()
    print("-" * 80)

    # Initialize processors
    llm_processor = LLMProcessor()
    elevenlabs_api_key = os.getenv('ELEVENLABS_API_KEY')
    voice_gen = None
    if not skip_voice_api and elevenlabs_api_key:
        voice_gen = VoiceGenerator(api_key=elevenlabs_api_key)

    # Step 2: Generate background music (shared across all languages)
    music_prompt = None
    music_file = None

    if voice_gen:
        print()
        print("  🎵 Generating background music (shared across all languages)...")
        try:
            music_result = llm_processor.execute({
                'text': '',
                'operation': 'generate_music_prompt',
                'params': {
                    'synopsis': series_summary,
                    'genre': genre
                }
            })
            music_prompt = music_result['output'].strip()
            print(f"     ✅ Music prompt generated ({len(music_prompt)} chars)")
            print()
            print("🎵 Music Prompt:", music_prompt[:100], "...")
            print()

            music_path = stage_05_audio / 'background_music.mp3'
            voice_gen.generate_music(
                prompt=music_prompt,
                duration_ms=120000,
                output_path=music_path
            )
            music_file = 'background_music.mp3'
            print(f"     ✅ Music generated: {music_file}")
        except Exception as e:
            print(f"     ⚠️  Music generation failed: {e}")

    print()
    print("=" * 80)

    # Step 3: Process each language
    voice_results = {}

    for lang in languages_to_process:
        print()
        print(f"{'=' * 80}")
        emoji = {'korean': '🇰🇷', 'japanese': '🇯🇵', 'taiwanese': '🇹🇼'}.get(lang, '🌏')
        print(f"{emoji} Processing: {lang.upper()}")
        print("=" * 80)
        print()

        source_stage = series_folder / '04_tagged' / lang
        lang_output_dir = stage_05_audio / lang
        lang_output_dir.mkdir(parents=True, exist_ok=True)

        # Get Episode 1 for this language
        episodes = sorted(source_stage.glob('episode_*.json'))
        if not episodes:
            print(f"  ❌ No episodes found for {lang}")
            continue

        episode_1_file = next((e for e in episodes if 'episode_001' in e.name), episodes[0])
        with open(episode_1_file, 'r', encoding='utf-8') as f:
            episode_data = json.load(f)
        episode_title = episode_data.get('title', 'Episode 1')

        print(f"  📖 Using Episode 1: {episode_title}")

        # Extract voice design variables for this language
        print(f"  🎤 Extracting voice design variables for {lang}...")
        variables_result = llm_processor.execute({
            'text': '',
            'operation': 'extract_voice_variables',
            'params': {
                'series_summary': series_summary,
                'genre': genre,
                'target_language': lang
            }
        })

        voice_vars = variables_result.get('metadata', {}).get('voice_variables')
        if not voice_vars:
            try:
                voice_vars = json.loads(variables_result['output'])
            except json.JSONDecodeError:
                voice_vars = llm_processor._get_default_voice_variables(lang)

        # Select template and assemble voice description
        template_type = voice_vars.get('template_type', 'narrative')
        template = select_voice_template(template_type)

        try:
            voice_description = template.format(**voice_vars)
        except KeyError as e:
            print(f"     ⚠️  Missing variable {e}, using defaults")
            default_vars = llm_processor._get_default_voice_variables(lang)
            default_vars.update(voice_vars)
            voice_description = template.format(**default_vars)

        voice_characteristic = voice_vars.get('characteristic_keyword', 'Warm, Steady')

        print(f"     ✅ Variables: gender={voice_vars.get('gender')}, age={voice_vars.get('age')}")
        print(f"     📌 Nationality: {voice_vars.get('nationality')}")
        print(f"     📌 Characteristic: {voice_characteristic}")
        print()
        print(f"  🎤 Voice Description:")
        print(f"     {voice_description[:150]}...")
        print()

        # Generate voice for this language
        voice_id = None
        if voice_gen:
            print(f"  🔊 Generating voice for {lang}...")
            try:
                sample_text = SAMPLE_TEXTS.get(lang, SAMPLE_TEXTS['korean'])
                country_code = COUNTRY_CODES.get(lang, 'XX')
                voice_name = f"{country_code}_{series_folder.name}_{voice_characteristic}"

                result = voice_gen.design_and_save_voice(
                    name=voice_name,
                    voice_description=voice_description,
                    sample_text=sample_text,
                    model="eleven_ttv_v3",
                    guidance_scale=3.0,
                    save_preview=True,
                    preview_path=lang_output_dir / 'voice_preview.mp3'
                )

                voice_id = result['voice_id']
                print(f"     ✅ Voice created: {voice_name}")
                print(f"     📌 Voice ID: {voice_id}")
                print(f"     🔊 Preview: {lang}/voice_preview.mp3")

            except Exception as e:
                print(f"     ⚠️  Voice generation failed: {e}")
        else:
            print(f"  ⚠️  Skipping voice generation (no API key or --skip-voice-api)")

        # Save language-specific config
        country_code = COUNTRY_CODES.get(lang, 'XX')
        lang_config = {
            'series_name': series_folder.name,
            'source_language': lang,
            'country_code': country_code,
            'series_summary': series_summary,
            'voice_description': voice_description,
            'voice_characteristic': voice_characteristic,
            'voice_variables': voice_vars,
            'voice_template_type': template_type,
            'voice_id': voice_id,
            'voice_settings': {
                'stability': 0.5,
                'similarity_boost': 0.75,
                'style': 0.0,
                'use_speaker_boost': True
            },
            'audio_settings': {
                'gap_duration_ms': 1000,
                'music_volume': 0.3,
                'fade_duration': 5.0,
                'intro_music_duration': 30.0,
                'outro_music_duration': 30.0,
                'voice_start_delay': 5.0
            },
            'music_prompt': music_prompt,
            'music_file': f'../background_music.mp3' if music_file else None,
            'music_duration_ms': 120000 if music_file else None,
            'created_from_episode': episode_title
        }

        config_file = lang_output_dir / 'audio_config.json'
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(lang_config, f, ensure_ascii=False, indent=2)

        print(f"     ✅ Config saved: {lang}/audio_config.json")

        voice_results[lang] = {
            'voice_id': voice_id,
            'voice_name': f"{country_code}_{series_folder.name}_{voice_characteristic}" if voice_id else None,
            'config_file': str(config_file)
        }

    # Summary
    print()
    print("=" * 80)
    print("✅ Stage 5 Complete: Audio Setup")
    print("=" * 80)
    print()
    print("📂 Output Structure:")
    print(f"   {stage_05_audio}/")
    if music_file:
        print(f"   ├── background_music.mp3 (shared)")
    for lang in languages_to_process:
        result = voice_results.get(lang, {})
        voice_status = f"✅ {result.get('voice_id', 'N/A')}" if result.get('voice_id') else "❌ Not generated"
        print(f"   ├── {lang}/")
        print(f"   │   ├── audio_config.json")
        print(f"   │   └── voice_preview.mp3  {voice_status}")
    print()

    if any(r.get('voice_id') for r in voice_results.values()):
        print("🎉 Voice IDs saved to each language's audio_config.json")
        print("   Stage 6 will use these voice IDs automatically.")
        print("   Stage 7 will use this music for background audio.")
    elif music_prompt:
        print("📋 Music prompt generated but API call failed.")
        print("   You can use the prompt above to generate music manually.")
    print()

    return True

if __name__ == '__main__':
    import argparse
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(
        description='Stage 5: Audio Setup',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python stage_05_setup_audio.py "processed/Publisher/Series"
  python stage_05_setup_audio.py "processed/Publisher/Series" --lang korean
  python stage_05_setup_audio.py "processed/Publisher/Series" --lang all
  python stage_05_setup_audio.py "processed/Publisher/Series" --skip-voice-api

This stage:
  1. Reads emotion-tagged episodes from 04_tagged/{language}/
  2. Loads series synopsis from series_metadata.json
  3. Generates background music (shared across all languages)
  4. For each language:
     - Designs voice description optimized for ElevenLabs Voice Design API
     - Generates voice using ElevenLabs API (if API key available)
     - Saves voice_id to {language}/audio_config.json

Output Structure:
  05_audio_setup/
  ├── background_music.mp3  (shared)
  ├── korean/
  │   ├── audio_config.json
  │   └── voice_preview.mp3
  ├── japanese/
  │   ├── audio_config.json
  │   └── voice_preview.mp3
  └── taiwanese/
      ├── audio_config.json
      └── voice_preview.mp3

Environment Variables:
  ELEVENLABS_API_KEY: Required for automatic voice generation
        """
    )
    parser.add_argument('series_folder', help='Path to series folder')
    parser.add_argument(
        '--lang',
        choices=['korean', 'japanese', 'taiwanese', 'all'],
        default=None,
        help='Source language or "all" for all available languages (default: interactive)'
    )
    parser.add_argument(
        '--skip-voice-api',
        action='store_true',
        help='Skip ElevenLabs Voice Design API call (manual workflow)'
    )
    parser.add_argument(
        '--use-preset',
        action='store_true',
        help='Use preset voice_id from CSV and existing music files from music/ folder'
    )

    args = parser.parse_args()
    series_folder = Path(args.series_folder)

    if not series_folder.exists():
        print(f"❌ Series folder not found: {series_folder}")
        sys.exit(1)

    success = run_stage_5(series_folder, args.lang, args.skip_voice_api, args.use_preset)
    sys.exit(0 if success else 1)
