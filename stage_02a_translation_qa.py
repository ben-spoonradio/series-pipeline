#!/usr/bin/env python3
"""
Stage 2A: Translation QA
Validate translation quality by checking language mixing, glossary consistency, and character name accuracy
"""

import sys
import json
from pathlib import Path
from typing import Optional, List
from tqdm import tqdm
from processors.translation_qa import TranslationQAValidator, batch_validate, QAResult
from processors.glossary_manager import GlossaryManager
from processors.llm_processor import LLMProcessor

# Language configurations
LANGUAGE_CONFIG = {
    'korean': {
        'emoji': '🇰🇷',
        'source_lang': 'korean',
        'target_lang': 'korean',
        'skip_language_mixing': True,  # Korean in Korean is expected
    },
    'japanese': {
        'emoji': '🇯🇵',
        'source_lang': 'korean',
        'target_lang': 'japanese',
        'skip_language_mixing': False,
    },
    'taiwanese': {
        'emoji': '🇹🇼',
        'source_lang': 'korean',
        'target_lang': 'traditional_chinese',
        'skip_language_mixing': False,
    }
}


def run_stage_2a(
    series_folder: Path,
    target_language: Optional[str] = None,
    auto_fix: bool = False,
    max_episodes: Optional[int] = None,
    fail_on_error: bool = False,
    max_retries: int = 5
) -> bool:
    """
    Run Stage 2A: Translation QA

    Args:
        series_folder: Path to series folder
        target_language: Specific language to validate (default: all available)
        auto_fix: Automatically fix glossary mismatches
        max_retries: Maximum retry attempts for auto-fix (default: 5)
        max_episodes: Limit number of episodes to validate
        fail_on_error: Return False if any errors found

    Returns:
        True if QA passed (or no critical errors), False otherwise
    """
    print("=" * 80)
    print("STAGE 2A: Translation QA")
    print("=" * 80)
    print()

    # Check for translated content
    stage_02_translated = series_folder / '02_translated'

    if not stage_02_translated.exists():
        print(f"❌ Translated content not found: {stage_02_translated}")
        print("   Please run stage_02_translate.py first")
        return False

    # Find available languages
    available_langs = sorted([
        d.name for d in stage_02_translated.iterdir()
        if d.is_dir() and d.name in LANGUAGE_CONFIG
    ])

    if not available_langs:
        print(f"❌ No language folders found in {stage_02_translated}")
        return False

    # Determine which languages to validate
    if target_language:
        if target_language not in available_langs:
            print(f"❌ Language '{target_language}' not found")
            print(f"   Available: {', '.join(available_langs)}")
            return False
        languages_to_validate = [target_language]
    else:
        languages_to_validate = available_langs

    print(f"📁 Series: {series_folder.name}")
    print(f"🌏 Languages to validate: {', '.join(languages_to_validate)}")
    if auto_fix:
        print(f"🔧 Auto-fix: Enabled")
    print()

    # Load glossary if available (check for language-specific glossaries)
    glossary = {'terms': []}

    # Try to load glossary files (glossary_japanese.json, glossary_taiwanese.json)
    for lang in languages_to_validate:
        glossary_file = series_folder / f'glossary_{lang}.json'
        if glossary_file.exists():
            try:
                glossary_manager = GlossaryManager(glossary_file)
                loaded = glossary_manager.glossary_data
                if loaded.get('terms'):
                    glossary['terms'].extend(loaded['terms'])
            except Exception as e:
                print(f"⚠️  Failed to load glossary for {lang}: {e}")

    if glossary and glossary.get('terms'):
        print(f"📚 Glossary loaded: {len(glossary['terms'])} terms")
    else:
        print(f"⚠️  No glossary found (glossary checks will be skipped)")
        glossary = {'terms': []}

    print()
    print("-" * 80)

    # Create QA output directory
    qa_output_dir = series_folder / '02a_qa_report'
    qa_output_dir.mkdir(parents=True, exist_ok=True)

    # Initialize LLM processor for auto-fix (only if auto_fix is enabled)
    llm_processor = None
    if auto_fix:
        try:
            llm_processor = LLMProcessor()
            print(f"🤖 LLM Processor initialized for auto-fix")
        except Exception as e:
            print(f"⚠️  Failed to initialize LLM Processor: {e}")
            print("   Language mixing errors will not be auto-fixed")

    # Process each language
    all_results = {}
    total_errors = 0
    total_warnings = 0
    total_fixed = 0

    for lang in languages_to_validate:
        config = LANGUAGE_CONFIG[lang]
        emoji = config['emoji']

        lang_dir = stage_02_translated / lang
        episodes = sorted(lang_dir.glob('episode_*.json'))

        if max_episodes:
            episodes = episodes[:max_episodes]

        if not episodes:
            print(f"   ⚠️  No episodes found for {lang}")
            continue

        # Retry loop for auto-fix
        retry_count = 0
        lang_passed = False
        cumulative_fixed = 0

        while retry_count < max_retries:
            retry_count += 1

            if retry_count > 1:
                print()
                print(f"   🔄 Retry attempt {retry_count}/{max_retries} for {lang.upper()}")
                print("-" * 40)
            else:
                print()
                print(f"{emoji} Validating: {lang.upper()}")
                print("=" * 40)

            # Initialize validator
            # Skip language mixing check if source == target (e.g., Korean)
            skip_lang_mixing = config.get('skip_language_mixing', False)
            validator = TranslationQAValidator(
                source_lang=config['source_lang'],
                target_lang=config['target_lang'],
                glossary=glossary,
                skip_language_mixing=skip_lang_mixing
            )

            lang_results = []
            lang_errors = 0
            lang_warnings = 0
            lang_fixed = 0

            with tqdm(total=len(episodes), desc=f"   Checking",
                      bar_format='{desc}: {n}/{total}|{bar}| [{elapsed}<{remaining}]') as pbar:
                for episode_file in episodes:
                    try:
                        with open(episode_file, 'r', encoding='utf-8') as f:
                            episode_data = json.load(f)

                        episode_num = episode_data.get('episode_number', 0)
                        content = episode_data.get('content', '')

                        # Validate
                        result = validator.validate(content, episode_num)
                        lang_results.append(result)

                        # Count issues
                        lang_errors += result.error_count
                        lang_warnings += result.warning_count

                        # Auto-fix if enabled
                        if auto_fix and result.issues:
                            fixed_content, fixed_count, remaining = validator.auto_fix(
                                content, result.issues, llm_processor=llm_processor
                            )
                            if fixed_count > 0:
                                episode_data['content'] = fixed_content
                                with open(episode_file, 'w', encoding='utf-8') as f:
                                    json.dump(episode_data, f, ensure_ascii=False, indent=2)
                                lang_fixed += fixed_count
                                pbar.write(f"      ✅ Episode {episode_num:03d}: Fixed {fixed_count} issues")

                        # Report critical issues
                        if result.error_count > 0:
                            pbar.write(f"      ❌ Episode {episode_num:03d}: {result.error_count} errors, {result.warning_count} warnings")

                    except Exception as e:
                        pbar.write(f"      ❌ Failed to process {episode_file.name}: {e}")

                    pbar.update(1)

            cumulative_fixed += lang_fixed

            # Check if passed
            print()
            lang_passed = lang_errors == 0
            status = "✅ PASS" if lang_passed else "❌ FAIL"
            print(f"   {status} - Errors: {lang_errors}, Warnings: {lang_warnings}")
            if lang_fixed > 0:
                print(f"   🔧 Auto-fixed: {lang_fixed} issues")

            # Exit retry loop if passed or no fixes were made (nothing more to fix)
            if lang_passed:
                print(f"   ✅ {lang.upper()} validation passed!")
                break
            elif not auto_fix:
                # Not in auto-fix mode, no need to retry
                break
            elif lang_fixed == 0 and lang_errors > 0:
                # No fixes were made but errors remain - likely unfixable issues
                print(f"   ⚠️  No fixes applied but {lang_errors} errors remain")
                if retry_count < max_retries:
                    print(f"   🔄 Will retry ({retry_count}/{max_retries})...")
                break
            elif retry_count < max_retries:
                print(f"   🔄 {lang_errors} errors remain, retrying...")

        all_results[lang] = {
            'results': lang_results,
            'error_count': lang_errors,
            'warning_count': lang_warnings,
            'fixed_count': cumulative_fixed,
            'passed': lang_passed,
            'retries': retry_count
        }

        total_errors += lang_errors
        total_warnings += lang_warnings
        total_fixed += cumulative_fixed

    # Generate detailed report
    print()
    print("-" * 80)
    print()
    print("📋 Generating QA Report...")

    report = generate_qa_report(series_folder.name, all_results, glossary)
    report_file = qa_output_dir / 'qa_report.json'
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Generate human-readable summary
    summary_file = qa_output_dir / 'qa_summary.txt'
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(generate_text_summary(report))

    print(f"   ✅ Report saved: {report_file.name}")
    print(f"   ✅ Summary saved: {summary_file.name}")

    # Final summary
    print()
    print("=" * 80)
    overall_pass = total_errors == 0
    status = "✅ QA PASSED" if overall_pass else "❌ QA FAILED"
    print(f"{status}")
    print("=" * 80)
    print()
    print(f"📊 Summary:")
    print(f"   Total Errors: {total_errors}")
    print(f"   Total Warnings: {total_warnings}")
    if total_fixed > 0:
        print(f"   Auto-fixed: {total_fixed}")
    print()
    print(f"📂 Output: {qa_output_dir}")
    print()

    if not overall_pass:
        print("💡 Next Steps:")
        print("   1. Review qa_summary.txt for details")
        print("   2. Fix translation issues manually or re-run with --auto-fix")
        print("   3. Re-run this stage to verify fixes")
        print()

    if fail_on_error:
        return overall_pass
    return True


def generate_qa_report(series_name: str, all_results: dict, glossary: dict) -> dict:
    """Generate detailed QA report as JSON"""
    report = {
        'series_name': series_name,
        'glossary_term_count': len(glossary.get('terms', [])),
        'languages': {},
        'summary': {
            'total_errors': 0,
            'total_warnings': 0,
            'total_episodes': 0,
            'passed': True
        }
    }

    for lang, data in all_results.items():
        lang_report = {
            'error_count': data['error_count'],
            'warning_count': data['warning_count'],
            'fixed_count': data['fixed_count'],
            'passed': data['passed'],
            'episodes': []
        }

        for result in data['results']:
            if result.issues:
                ep_report = {
                    'episode_number': result.episode_number,
                    'passed': result.passed,
                    'error_count': result.error_count,
                    'warning_count': result.warning_count,
                    'issues': [
                        {
                            'type': issue.type,
                            'severity': issue.severity,
                            'text': issue.text,
                            'message': issue.message,
                            'expected': issue.expected,
                            'context': issue.context
                        }
                        for issue in result.issues
                    ]
                }
                lang_report['episodes'].append(ep_report)

        report['languages'][lang] = lang_report
        report['summary']['total_errors'] += data['error_count']
        report['summary']['total_warnings'] += data['warning_count']
        report['summary']['total_episodes'] += len(data['results'])
        if not data['passed']:
            report['summary']['passed'] = False

    return report


def generate_text_summary(report: dict) -> str:
    """Generate human-readable text summary"""
    lines = []
    lines.append("=" * 60)
    lines.append(f"Translation QA Report: {report['series_name']}")
    lines.append("=" * 60)
    lines.append("")

    # Overall summary
    summary = report['summary']
    status = "PASSED" if summary['passed'] else "FAILED"
    lines.append(f"Status: {status}")
    lines.append(f"Total Episodes: {summary['total_episodes']}")
    lines.append(f"Total Errors: {summary['total_errors']}")
    lines.append(f"Total Warnings: {summary['total_warnings']}")
    lines.append(f"Glossary Terms: {report['glossary_term_count']}")
    lines.append("")

    # Per-language details
    for lang, data in report['languages'].items():
        lines.append("-" * 40)
        status = "PASS" if data['passed'] else "FAIL"
        lines.append(f"{lang.upper()} [{status}]")
        lines.append(f"  Errors: {data['error_count']}, Warnings: {data['warning_count']}")

        if data['episodes']:
            lines.append(f"  Episodes with issues:")
            for ep in data['episodes']:
                lines.append(f"    Episode {ep['episode_number']:03d}: {ep['error_count']} errors, {ep['warning_count']} warnings")
                for issue in ep['issues'][:3]:  # Show first 3 issues
                    lines.append(f"      [{issue['severity'].upper()}] {issue['message']}")
                if len(ep['issues']) > 3:
                    lines.append(f"      ... and {len(ep['issues']) - 3} more issues")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


if __name__ == '__main__':
    import argparse
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(
        description='Stage 2A: Translation QA',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python stage_02a_translation_qa.py "processed_origin/Publisher/Series"
  python stage_02a_translation_qa.py "processed_origin/Publisher/Series" --lang taiwanese
  python stage_02a_translation_qa.py "processed_origin/Publisher/Series" --auto-fix
  python stage_02a_translation_qa.py "processed_origin/Publisher/Series" --max-episodes 10

This stage validates:
  1. Language mixing (source language appearing in target text)
  2. Untranslated glossary terms
  3. Character name consistency (similar character substitutions)

Output:
  02a_qa_report/
  ├── qa_report.json   (detailed machine-readable report)
  └── qa_summary.txt   (human-readable summary)

Auto-fix:
  The --auto-fix flag will automatically correct:
  1. Glossary mismatches (wrong character variants)
  2. Language mixing errors (Korean text in translated content)
  3. Untranslated terms (using glossary translations)

  Language mixing auto-fix uses LLM to re-translate Korean segments.
"""
    )

    parser.add_argument('series_folder', type=str, help='Path to series folder')
    parser.add_argument('--lang', type=str, default=None,
                        choices=['korean', 'japanese', 'taiwanese'],
                        help='Specific language to validate (default: all)')
    parser.add_argument('--auto-fix', action='store_true',
                        help='Automatically fix translation issues')
    parser.add_argument('--max-episodes', type=int, default=None,
                        help='Maximum number of episodes to validate')
    parser.add_argument('--max-retries', type=int, default=5,
                        help='Maximum retry attempts for auto-fix (default: 5)')
    parser.add_argument('--strict', action='store_true',
                        help='Return non-zero exit code if errors found')

    args = parser.parse_args()

    series_folder = Path(args.series_folder)

    if not series_folder.exists():
        print(f"❌ Series folder not found: {series_folder}")
        sys.exit(1)

    success = run_stage_2a(
        series_folder,
        target_language=args.lang,
        auto_fix=args.auto_fix,
        max_episodes=args.max_episodes,
        fail_on_error=args.strict,
        max_retries=args.max_retries
    )
    sys.exit(0 if success else 1)
