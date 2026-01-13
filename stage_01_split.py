#!/usr/bin/env python3
"""
Stage 1: Episode Splitting
Split source file into episodes and match series metadata
"""

import sys
from pathlib import Path
from processors.file_converter import FileConverter
from processors.llm_episode_splitter import LLMEpisodeSplitter
from processors.series_metadata_matcher import SeriesMetadataMatcher
from config import get_output_dir, get_source_dir

def run_stage_1(file_path: Path, output_base: Path = None, language: str = 'korean'):
    """Run Stage 1: Episode Splitting with TTS heading"""
    # Use Config output directory if not specified
    if output_base is None:
        output_base = get_output_dir()

    print("=" * 80)
    print("STAGE 1: Episode Splitting")
    print("=" * 80)
    print()

    # Extract country/language and publisher from path
    # Structure: _SOURCE/KR/Peex/[시리즈폴더/]file.docx
    # Expected: parts = (KR, Peex, ...) where KR=language, Peex=publisher
    source_dir = get_source_dir()
    try:
        parts = file_path.relative_to(source_dir).parts
        # parts = (KR, Peex, [시리즈폴더,] file.docx)
        language_code = parts[0] if len(parts) > 0 else 'Unknown'
        publisher = parts[1] if len(parts) > 1 else 'Unknown'
    except ValueError:
        # File is not under source_dir, use fallback
        language_code = 'Unknown'
        publisher = 'Unknown'

    original_filename = file_path.stem

    print(f"📁 File: {file_path}")
    print(f"📊 Size: {file_path.stat().st_size:,} bytes")
    print(f"🌍 Country: {language_code}")
    print(f"📚 Publisher: {publisher}")
    print()

    print("-" * 80)
    print()

    # Step 1: Match series metadata to get cleaned series name
    print("  📝 Matching series metadata from CSV...")
    matcher = SeriesMetadataMatcher()
    match_result = matcher.match(original_filename)

    if match_result['matched'] and match_result['match_score'] > 0.8:
        metadata = match_result
        series_name = metadata['series_name']  # Use cleaned name from CSV
        print(f"     ✅ CSV Match: {series_name} (score: {metadata['match_score']:.2f})")
    else:
        print(f"     ⚠️  No strong match found, using cleaned filename")
        series_name = match_result['series_name']  # Use cleaned name even if no match
        metadata = {'series_name': series_name, 'match_score': 0.0}

    print(f"📖 Series: {series_name}")
    print()

    # Setup output directory with cleaned series name
    # Structure: _PROCESSED/KR/Peex/사랑의빚/
    series_folder = output_base / language_code / publisher / series_name
    stage_01_split = series_folder / '01_split'
    stage_01_split.mkdir(parents=True, exist_ok=True)

    # Step 2: Convert file to text
    print("  📖 Reading file content...")
    converter = FileConverter()
    try:
        convert_result = converter.execute({
            'file_path': str(file_path),
            'language': 'korean'
        })
        text = convert_result['output']
    except Exception as e:
        print(f"     ❌ File conversion failed: {e}")
        return False
    print(f"     ✅ Converted: {len(text):,} characters")
    print()

    # Step 3: Split into episodes
    print("  ✂️  Splitting episodes...")
    splitter = LLMEpisodeSplitter()
    try:
        split_result = splitter.execute({
            'text': text,
            'filename': file_path.name,
            'language': 'korean'
        })
        episodes = split_result['output']['episodes']
    except Exception as e:
        print(f"     ❌ Episode splitting failed: {e}")
        return False
    print(f"     ✅ Found {len(episodes)} episodes")
    print(f"     📊 Pattern: {split_result['output']['pattern_used']}")
    print(f"     🎯 Confidence: {split_result['metadata']['confidence']}%")
    print()

    # Step 4: Save episodes with TTS heading
    print("  💾 Saving episode files...")

    # Define number pronunciation helper
    def get_tts_heading(episode_number: int, language: str = 'korean', title: str = None) -> str:
        """Generate TTS heading like 'Episode 일. 제목.' based on language"""

        # Korean number pronunciation
        korean_numbers = {
            1: '일', 2: '이', 3: '삼', 4: '사', 5: '오',
            6: '육', 7: '칠', 8: '팔', 9: '구', 10: '십',
            11: '십일', 12: '십이', 13: '십삼', 14: '십사', 15: '십오',
            16: '십육', 17: '십칠', 18: '십팔', 19: '십구', 20: '이십',
            30: '삼십', 40: '사십', 50: '오십', 60: '육십', 70: '칠십',
            80: '팔십', 90: '구십', 100: '백'
        }

        # Japanese number pronunciation (using Chinese numerals)
        japanese_numbers = {
            1: '一', 2: '二', 3: '三', 4: '四', 5: '五',
            6: '六', 7: '七', 8: '八', 9: '九', 10: '十'
        }

        # Chinese number pronunciation (Traditional Chinese)
        chinese_numbers = {
            1: '一', 2: '二', 3: '三', 4: '四', 5: '五',
            6: '六', 7: '七', 8: '八', 9: '九', 10: '十'
        }

        if language == 'korean':
            if episode_number <= 20:
                num_text = korean_numbers.get(episode_number, str(episode_number))
            elif episode_number < 100:
                tens = (episode_number // 10) * 10
                ones = episode_number % 10
                if ones == 0:
                    num_text = korean_numbers.get(tens, str(episode_number))
                else:
                    num_text = korean_numbers.get(tens, '') + korean_numbers.get(ones, '')
            elif episode_number == 100:
                num_text = '백'
            else:
                # For numbers > 100, use decimal representation
                hundreds = episode_number // 100
                remainder = episode_number % 100
                if hundreds == 1:
                    num_text = '백'
                else:
                    num_text = korean_numbers.get(hundreds, str(hundreds)) + '백'
                if remainder > 0:
                    if remainder <= 20:
                        num_text += korean_numbers.get(remainder, str(remainder))
                    else:
                        tens = (remainder // 10) * 10
                        ones = remainder % 10
                        if ones == 0:
                            num_text += korean_numbers.get(tens, '')
                        else:
                            num_text += korean_numbers.get(tens, '') + korean_numbers.get(ones, '')
            if title:
                return f"Episode {num_text}. {title}.\n\n"
            return f"Episode {num_text}.\n\n"

        elif language == 'japanese':
            # For Japanese, construct number using Chinese numerals
            if episode_number <= 10:
                num_text = japanese_numbers.get(episode_number, str(episode_number))
            elif episode_number < 100:
                tens = episode_number // 10
                ones = episode_number % 10
                if tens == 1:
                    num_text = '十'
                else:
                    num_text = japanese_numbers.get(tens, str(tens)) + '十'
                if ones > 0:
                    num_text += japanese_numbers.get(ones, str(ones))
            else:
                # For 100+
                hundreds = episode_number // 100
                remainder = episode_number % 100
                if hundreds == 1:
                    num_text = '百'
                else:
                    num_text = japanese_numbers.get(hundreds, str(hundreds)) + '百'
                if remainder > 0:
                    if remainder <= 10:
                        num_text += japanese_numbers.get(remainder, str(remainder))
                    else:
                        tens = remainder // 10
                        ones = remainder % 10
                        if tens == 1:
                            num_text += '十'
                        else:
                            num_text += japanese_numbers.get(tens, str(tens)) + '十'
                        if ones > 0:
                            num_text += japanese_numbers.get(ones, str(ones))
            if title:
                return f"Episode {num_text}. {title}.\n\n"
            return f"Episode {num_text}.\n\n"

        elif language == 'traditional_chinese':
            # Similar to Japanese
            if episode_number <= 10:
                num_text = chinese_numbers.get(episode_number, str(episode_number))
            elif episode_number < 100:
                tens = episode_number // 10
                ones = episode_number % 10
                if tens == 1:
                    num_text = '十'
                else:
                    num_text = chinese_numbers.get(tens, str(tens)) + '十'
                if ones > 0:
                    num_text += chinese_numbers.get(ones, str(ones))
            else:
                hundreds = episode_number // 100
                remainder = episode_number % 100
                if hundreds == 1:
                    num_text = '百'
                else:
                    num_text = chinese_numbers.get(hundreds, str(hundreds)) + '百'
                if remainder > 0:
                    if remainder <= 10:
                        num_text += chinese_numbers.get(remainder, str(remainder))
                    else:
                        tens = remainder // 10
                        ones = remainder % 10
                        if tens == 1:
                            num_text += '十'
                        else:
                            num_text += chinese_numbers.get(tens, str(tens)) + '十'
                        if ones > 0:
                            num_text += chinese_numbers.get(ones, str(ones))
            if title:
                return f"Episode {num_text}. {title}.\n\n"
            return f"Episode {num_text}.\n\n"

        elif language == 'english':
            # English uses written numbers (one, two, three, etc.)
            english_numbers = {
                1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five',
                6: 'six', 7: 'seven', 8: 'eight', 9: 'nine', 10: 'ten',
                11: 'eleven', 12: 'twelve', 13: 'thirteen', 14: 'fourteen', 15: 'fifteen',
                16: 'sixteen', 17: 'seventeen', 18: 'eighteen', 19: 'nineteen', 20: 'twenty'
            }

            if episode_number <= 20:
                num_text = english_numbers.get(episode_number, str(episode_number))
            elif episode_number < 100:
                tens_map = {2: 'twenty', 3: 'thirty', 4: 'forty', 5: 'fifty',
                           6: 'sixty', 7: 'seventy', 8: 'eighty', 9: 'ninety'}
                tens = episode_number // 10
                ones = episode_number % 10
                num_text = tens_map.get(tens, str(tens * 10))
                if ones > 0:
                    num_text += '-' + english_numbers.get(ones, str(ones))
            else:
                num_text = str(episode_number)
            if title:
                return f"Episode {num_text}. {title}.\n\n"
            return f"Episode {num_text}.\n\n"

        else:
            # Default: use numeric
            if title:
                return f"Episode {episode_number}. {title}.\n\n"
            return f"Episode {episode_number}.\n\n"

    import json
    for episode in episodes:
        episode_file = stage_01_split / f"episode_{episode['number']:03d}.json"

        # Get extracted title (if available)
        episode_title = episode.get('title', '') or ''

        # Add TTS heading to content (with title if extracted)
        tts_heading = get_tts_heading(episode['number'], language=language, title=episode_title if episode_title else None)
        content_with_heading = tts_heading + episode['content']

        episode_data = {
            'episode_number': episode['number'],
            'title': episode.get('title', ''),
            'content': content_with_heading,
            'metadata': {
                'series_name': metadata['series_name'],
                'series_match_score': metadata['match_score'],
                'source_file': file_path.name,
                'character_count': len(content_with_heading),
                'tts_heading_added': True
            }
        }

        with open(episode_file, 'w', encoding='utf-8') as f:
            json.dump(episode_data, f, ensure_ascii=False, indent=2)

        print(f"     ✅ {episode_file.name} ({len(content_with_heading):,} chars)")

    print()
    print("=" * 80)
    print(f"✅ Stage 1 Complete: {len(episodes)} episodes saved to {stage_01_split}")
    print("=" * 80)
    print()
    print("📋 Next Steps:")
    print("   1. Review episode files in: " + str(stage_01_split))
    print("   2. Check episode boundaries and content quality")
    print("   3. Run: python stage_02_format.py")
    print()

    return True

if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv()

    if len(sys.argv) < 2:
        print("Usage: python stage_01_split.py <file_path>")
        print()
        print("Example:")
        print('  python stage_01_split.py "source/KR/Peex/버추얼 러브 수정본_로맨스판타지3.docx"')
        sys.exit(1)

    file_path = Path(sys.argv[1])

    if not file_path.exists():
        print(f"❌ File not found: {file_path}")
        sys.exit(1)

    success = run_stage_1(file_path)
    sys.exit(0 if success else 1)
