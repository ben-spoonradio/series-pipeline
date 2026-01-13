"""
Review Generator
Generate human-readable Markdown review files for pipeline outputs.
These files are stored in _review/ directory separate from JSON outputs.
"""

import csv
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import config for default paths
try:
    from config import get_review_dir
except ImportError:
    def get_review_dir():
        return None

# Import prompts for logging
try:
    from processors import prompts
except ImportError:
    import prompts


class ReviewGenerator:
    """
    Generate human-readable review files for human QA reviewers.

    Output structure (mirrors _PROCESSED structure):
        _REVIEW/{publisher}/{series_name}/
        ├── 01_split/
        │   ├── __PROMPT_USED.md
        │   ├── __MERGED_REVIEW.md
        │   └── episodes/
        │       ├── episode_001.md
        │       └── ...
        ├── 02_translated/{language}/
        │   ├── __PROMPT_USED.md
        │   ├── __MERGED_REVIEW.md
        │   └── episodes/
        ├── 03_formatted/{language}/
        ├── 03a_speaker_tagged/{language}/
        ├── 04_tagged/{language}/
        └── 05_audio/
            ├── __PROMPT_USED.md
            └── __SETTINGS_REVIEW.md
    """

    def __init__(self, series_folder: Path, output_dir: Path = None):
        self.series_folder = Path(series_folder)
        self.series_name = self.series_folder.name

        # Extract language_code and publisher from series_metadata.json
        # e.g., _PROCESSED/KR/Peex/사랑의빚 -> language_code = KR, publisher = Peex
        self.language_code, self.publisher = self._get_metadata()

        # Priority: 1) explicit output_dir, 2) config REVIEW_DIR, 3) series_folder/_review
        # Review structure mirrors processed: _REVIEW/{language_code}/{publisher}/{series_name}/
        if output_dir:
            self.review_dir = Path(output_dir) / self.language_code / self.publisher / self.series_name
        else:
            config_review_dir = get_review_dir()
            if config_review_dir:
                # Use Google Drive _REVIEW with same structure as _PROCESSED
                self.review_dir = config_review_dir / self.language_code / self.publisher / self.series_name
            else:
                # Default to _review/ in series folder (legacy behavior)
                self.review_dir = self.series_folder / '_review'

    def _get_metadata(self) -> tuple:
        """Extract language_code and publisher from series_metadata.json or directory path"""
        import json

        language_code = 'Unknown'
        publisher = 'Unknown'

        # Try to read from series_metadata.json
        metadata_path = self.series_folder / 'series_metadata.json'
        if metadata_path.exists():
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    metadata = json.load(f)
                    language_code = metadata.get('language_code', 'Unknown')
                    publisher = metadata.get('publisher', 'Unknown')
                    if language_code != 'Unknown' and publisher != 'Unknown':
                        return language_code, publisher
            except (json.JSONDecodeError, IOError):
                pass

        # Fallback: use directory structure
        # _PROCESSED/KR/Peex/사랑의빚 -> parent = Peex, grandparent = KR
        skip_names = {'_PROCESSED', '_SOURCE', '_REVIEW', 'processed', 'source', 'origin'}

        parent_name = self.series_folder.parent.name
        grandparent_name = self.series_folder.parent.parent.name

        if parent_name not in skip_names:
            publisher = parent_name if publisher == 'Unknown' else publisher
        if grandparent_name not in skip_names:
            language_code = grandparent_name if language_code == 'Unknown' else language_code

        return language_code, publisher

    def _ensure_dir(self, path: Path) -> Path:
        """Create directory if it doesn't exist"""
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _get_timestamp(self) -> str:
        """Get current timestamp for headers"""
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # =========================================================================
    # Prompt Logging
    # =========================================================================

    def _get_prompt_by_name(self, prompt_name: str) -> Optional[str]:
        """Get prompt content by name from prompts module"""
        return getattr(prompts, prompt_name, None)

    def generate_prompt_log(self, stage_dir: Path, prompts_used: List[str],
                           stage_name: str, extra_context: str = "") -> Path:
        """
        Generate __PROMPT_USED.md with the prompts used for this stage.

        Args:
            stage_dir: Directory to write to
            prompts_used: List of prompt variable names
            stage_name: Human-readable stage name
            extra_context: Additional context to include

        Returns:
            Path to generated file
        """
        self._ensure_dir(stage_dir)
        output_path = stage_dir / '__PROMPT_USED.md'

        lines = []
        lines.append(f"# {stage_name} - Prompts Used")
        lines.append("")
        lines.append(f"> Generated: {self._get_timestamp()}")
        lines.append(f"> Series: {self.series_name}")
        if extra_context:
            lines.append(f"> {extra_context}")
        lines.append("")
        lines.append("---")
        lines.append("")

        for i, prompt_name in enumerate(prompts_used, 1):
            prompt_content = self._get_prompt_by_name(prompt_name)
            lines.append(f"## {i}. {prompt_name}")
            lines.append("")
            if prompt_content:
                lines.append("```")
                lines.append(prompt_content.strip())
                lines.append("```")
            else:
                lines.append("*(Prompt not found in prompts.py)*")
            lines.append("")
            lines.append("---")
            lines.append("")

        lines.append("## [Improvement Suggestions]")
        lines.append("<!-- Reviewer: Add your feedback on the prompts here -->")
        lines.append("")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        return output_path

    # =========================================================================
    # Episode Markdown Generation
    # =========================================================================

    def _episode_to_markdown(self, episode_data: Dict[str, Any],
                             include_metadata: bool = True) -> str:
        """Convert episode JSON to markdown content"""
        lines = []

        episode_num = episode_data.get('episode_number', 0)
        title = episode_data.get('title', '')
        content = episode_data.get('content', '')

        # Header
        if title:
            lines.append(f"# [Episode {episode_num:03d}] {title}")
        else:
            lines.append(f"# [Episode {episode_num:03d}]")
        lines.append("")

        # Metadata
        if include_metadata:
            char_count = len(content)
            line_count = content.count('\n') + 1
            lines.append(f"**Characters**: {char_count:,} | **Lines**: {line_count:,}")
            lines.append("")

        lines.append("---")
        lines.append("")

        # Content
        lines.append(content)
        lines.append("")

        return '\n'.join(lines)

    def generate_episode_md(self, episode_json_path: Path, output_dir: Path) -> Path:
        """
        Generate individual episode markdown file.

        Args:
            episode_json_path: Path to episode JSON file
            output_dir: Directory to write episode markdown

        Returns:
            Path to generated markdown file
        """
        self._ensure_dir(output_dir)

        with open(episode_json_path, 'r', encoding='utf-8') as f:
            episode_data = json.load(f)

        episode_num = episode_data.get('episode_number', 0)
        output_path = output_dir / f"episode_{episode_num:03d}.md"

        md_content = self._episode_to_markdown(episode_data)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        return output_path

    def generate_merged_review(self, episode_files: List[Path], output_dir: Path,
                               stage_name: str, language: str = None) -> Path:
        """
        Generate __MERGED_REVIEW.md with all episodes merged.

        Args:
            episode_files: List of episode JSON file paths (sorted)
            output_dir: Directory to write merged review
            stage_name: Stage name for header
            language: Target language (optional)

        Returns:
            Path to generated file
        """
        self._ensure_dir(output_dir)
        output_path = output_dir / '__MERGED_REVIEW.md'

        lines = []

        # Header
        header_parts = [self.series_name, stage_name]
        if language:
            header_parts.append(language.upper())
        lines.append(f"# {' - '.join(header_parts)}")
        lines.append("")
        lines.append(f"> Generated: {self._get_timestamp()}")
        lines.append(f"> Total Episodes: {len(episode_files)}")

        # Calculate total character count
        total_chars = 0
        episodes_data = []
        for ep_file in episode_files:
            with open(ep_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                episodes_data.append(data)
                total_chars += len(data.get('content', ''))

        lines.append(f"> Total Characters: {total_chars:,}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Count failed episodes
        failed_count = sum(1 for ep in episodes_data if ep.get('metadata', {}).get('emotion_tagging_failed'))

        if failed_count > 0:
            lines.append(f"> ⚠️ **Failed Episodes**: {failed_count} (no emotion tags)")
            lines.append("")

        # Table of Contents
        lines.append("## Table of Contents")
        lines.append("")
        for ep_data in episodes_data:
            ep_num = ep_data.get('episode_number', 0)
            title = ep_data.get('title', '')
            anchor = f"episode-{ep_num:03d}"
            failed_marker = " ⚠️" if ep_data.get('metadata', {}).get('emotion_tagging_failed') else ""
            if title:
                lines.append(f"- [Episode {ep_num:03d}: {title}](#{anchor}){failed_marker}")
            else:
                lines.append(f"- [Episode {ep_num:03d}](#{anchor}){failed_marker}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Episode Contents
        for ep_data in episodes_data:
            ep_num = ep_data.get('episode_number', 0)
            title = ep_data.get('title', '')
            content = ep_data.get('content', '')
            metadata = ep_data.get('metadata', {})
            is_failed = metadata.get('emotion_tagging_failed', False)

            # Anchor
            lines.append(f"<a id=\"episode-{ep_num:03d}\"></a>")
            lines.append("")

            # Header with failure indicator
            header_prefix = "⚠️ " if is_failed else ""
            if title:
                lines.append(f"# {header_prefix}[Episode {ep_num:03d}] {title}")
            else:
                lines.append(f"# {header_prefix}[Episode {ep_num:03d}]")
            lines.append("")

            # Show failure warning if applicable
            if is_failed:
                error_msg = metadata.get('emotion_tagging_error', 'Unknown error')
                lines.append(f"> ⚠️ **EMOTION TAGGING FAILED** - Content below has NO emotion tags")
                lines.append(f"> ")
                lines.append(f"> Error: `{error_msg[:100]}...`" if len(error_msg) > 100 else f"> Error: `{error_msg}`")
                lines.append("")

            # Metadata
            char_count = len(content)
            lines.append(f"**Characters**: {char_count:,}")
            if is_failed:
                lines.append(f"**Status**: ❌ Emotion tagging failed")
            lines.append("")
            lines.append("---")
            lines.append("")

            # Content
            lines.append(content)
            lines.append("")
            lines.append("---")
            lines.append("")

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        return output_path

    # =========================================================================
    # Stage-Specific Review Generation
    # =========================================================================

    def generate_stage_1_review(self) -> bool:
        """
        Generate review files for Stage 1: Episode Splitting

        Source: 01_split/episode_*.json
        Output: _review/01_split/
        """
        source_dir = self.series_folder / '01_split'
        output_dir = self.review_dir / '01_split'

        if not source_dir.exists():
            return False

        episode_files = sorted(source_dir.glob('episode_*.json'))
        if not episode_files:
            return False

        # Generate prompt log (episode splitter uses inline prompts)
        prompts_used = []  # Inline prompts in llm_episode_splitter.py
        self.generate_prompt_log(
            output_dir,
            prompts_used,
            "Stage 1: Episode Splitting",
            "Note: This stage uses inline prompts in llm_episode_splitter.py"
        )

        # Generate individual episode markdowns
        episodes_dir = self._ensure_dir(output_dir / 'episodes')
        for ep_file in episode_files:
            self.generate_episode_md(ep_file, episodes_dir)

        # Generate merged review
        self.generate_merged_review(episode_files, output_dir, "Episode Split")

        return True

    def generate_glossary_csv(self, glossary_path: Path, target_language: str = None) -> Optional[Path]:
        """
        Generate CSV export of glossary for human review.
        CSV is saved to _REVIEW folder (not _PROCESSED) as it's for review purposes.

        Args:
            glossary_path: Path to glossary.json file
            target_language: Target language (e.g., 'japanese', 'taiwanese') for filename

        Returns:
            Path to generated CSV file, or None if failed
        """
        if not glossary_path.exists():
            return None

        try:
            with open(glossary_path, 'r', encoding='utf-8') as f:
                glossary_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

        terms = glossary_data.get('terms', [])
        if not terms:
            return None

        # Category priority order (character first, then location, then others)
        category_priority = {
            'character': 0,
            'location': 1,
            'term': 2,
            'skill': 3,
            'item': 4,
            'organization': 5,
        }

        # Sort terms by category priority, then by original text
        def sort_key(term):
            category = term.get('category', 'term').lower()
            priority = category_priority.get(category, 99)
            return (priority, term.get('original', ''))

        sorted_terms = sorted(terms, key=sort_key)

        # Save to _REVIEW directory (review_dir), not _PROCESSED
        output_dir = self.review_dir
        self._ensure_dir(output_dir)

        # Generate CSV with language-specific filename
        if target_language:
            csv_path = output_dir / f'glossary_{target_language}.csv'
        else:
            csv_path = output_dir / 'glossary.csv'

        with open(csv_path, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)

            # Header row
            writer.writerow(['Category', 'Original', 'Translation', 'Context'])

            # Data rows
            current_category = None
            for term in sorted_terms:
                category = term.get('category', 'term')
                original = term.get('original', '')
                translation = term.get('translation', '')
                context = term.get('context', '')

                # Add empty row between categories for readability
                if current_category is not None and category != current_category:
                    writer.writerow([])
                current_category = category

                writer.writerow([category, original, translation, context])

        return csv_path

    def generate_stage_2_review(self) -> bool:
        """
        Generate review files for Stage 2: Translation

        Source: 02_translated/{korean,japanese,taiwanese}/episode_*.json
        Output: _review/02_translated/{language}/
        """
        source_dir = self.series_folder / '02_translated'

        if not source_dir.exists():
            return False

        languages = ['korean', 'japanese', 'taiwanese']
        generated = False

        for lang in languages:
            lang_dir = source_dir / lang
            if not lang_dir.exists():
                continue

            episode_files = sorted(lang_dir.glob('episode_*.json'))
            if not episode_files:
                continue

            output_dir = self.review_dir / '02_translated' / lang

            # Language-specific prompts
            if lang == 'korean':
                # Korean is source, no translation prompt
                prompts_used = []
            elif lang == 'japanese':
                prompts_used = [
                    'TERM_EXTRACTION_PROMPT',
                    'JAPANESE_TERM_TRANSLATION_PROMPT',
                    'JAPANESE_GLOSSARY_TRANSLATION_PROMPT'
                ]
            elif lang == 'taiwanese':
                prompts_used = [
                    'TERM_EXTRACTION_PROMPT',
                    'TAIWAN_TERM_TRANSLATION_PROMPT',
                    'TAIWAN_GLOSSARY_TRANSLATION_PROMPT'
                ]

            self.generate_prompt_log(
                output_dir,
                prompts_used,
                "Stage 2: Translation",
                f"Target Language: {lang.upper()}"
            )

            # Generate episode markdowns
            episodes_dir = self._ensure_dir(output_dir / 'episodes')
            for ep_file in episode_files:
                self.generate_episode_md(ep_file, episodes_dir)

            # Generate merged review
            self.generate_merged_review(
                episode_files, output_dir,
                "Translation", language=lang
            )

            # Generate glossary CSV (for non-Korean languages)
            if lang != 'korean':
                # Glossary is stored in series root with language suffix
                glossary_path = self.series_folder / f'glossary_{lang}.json'
                csv_path = self.generate_glossary_csv(glossary_path, target_language=lang)
                if csv_path:
                    print(f"     📋 Generated glossary CSV: {csv_path.name}")

            generated = True

        return generated

    def generate_stage_3_review(self) -> bool:
        """
        Generate review files for Stage 3: TTS Formatting

        Source: 03_formatted/{korean,japanese,taiwanese}/episode_*.json
        Output: _review/03_formatted/{language}/
        """
        source_dir = self.series_folder / '03_formatted'

        if not source_dir.exists():
            return False

        languages = ['korean', 'japanese', 'taiwanese']
        prompt_map = {
            'korean': ['TTS_FORMAT_PROMPT_KR', 'EPISODE_TITLE_PROMPT_KR'],
            'japanese': ['TTS_FORMAT_PROMPT_JP', 'EPISODE_TITLE_PROMPT_JP'],
            'taiwanese': ['TTS_FORMAT_PROMPT_TW', 'EPISODE_TITLE_PROMPT_TW']
        }
        generated = False

        for lang in languages:
            lang_dir = source_dir / lang
            if not lang_dir.exists():
                continue

            episode_files = sorted(lang_dir.glob('episode_*.json'))
            if not episode_files:
                continue

            output_dir = self.review_dir / '03_formatted' / lang

            self.generate_prompt_log(
                output_dir,
                prompt_map.get(lang, []),
                "Stage 3: TTS Formatting",
                f"Target Language: {lang.upper()}"
            )

            # Generate episode markdowns
            episodes_dir = self._ensure_dir(output_dir / 'episodes')
            for ep_file in episode_files:
                self.generate_episode_md(ep_file, episodes_dir)

            # Generate merged review
            self.generate_merged_review(
                episode_files, output_dir,
                "TTS Formatted", language=lang
            )

            generated = True

        return generated

    def generate_stage_3a_review(self) -> bool:
        """
        Generate review files for Stage 3a: Speaker Tagging

        Source: 03a_speaker_tagged/{korean,japanese,taiwanese}/episode_*.json
        Output: _review/03a_speaker_tagged/{language}/
        """
        source_dir = self.series_folder / '03a_speaker_tagged'

        if not source_dir.exists():
            return False

        languages = ['korean', 'japanese', 'taiwanese']
        prompt_map = {
            'korean': ['CHARACTER_EXTRACTION_PROMPT', 'SPEAKER_TAGGING_PROMPT_KR'],
            'japanese': ['CHARACTER_EXTRACTION_PROMPT', 'SPEAKER_TAGGING_PROMPT_JP'],
            'taiwanese': ['CHARACTER_EXTRACTION_PROMPT', 'SPEAKER_TAGGING_PROMPT_TW']
        }
        generated = False

        for lang in languages:
            lang_dir = source_dir / lang
            if not lang_dir.exists():
                continue

            episode_files = sorted(lang_dir.glob('episode_*.json'))
            if not episode_files:
                continue

            output_dir = self.review_dir / '03a_speaker_tagged' / lang

            self.generate_prompt_log(
                output_dir,
                prompt_map.get(lang, []),
                "Stage 3a: Speaker Tagging",
                f"Target Language: {lang.upper()}"
            )

            # Generate episode markdowns
            episodes_dir = self._ensure_dir(output_dir / 'episodes')
            for ep_file in episode_files:
                self.generate_episode_md(ep_file, episodes_dir)

            # Generate merged review
            self.generate_merged_review(
                episode_files, output_dir,
                "Speaker Tagged", language=lang
            )

            generated = True

        return generated

    def generate_stage_4_review(self) -> bool:
        """
        Generate review files for Stage 4: Emotion Tagging

        Source: 04_tagged/{korean,japanese,taiwanese}/episode_*.json
        Output: _review/04_tagged/{language}/
        """
        source_dir = self.series_folder / '04_tagged'

        if not source_dir.exists():
            return False

        languages = ['korean', 'japanese', 'taiwanese']
        generated = False

        for lang in languages:
            lang_dir = source_dir / lang
            if not lang_dir.exists():
                continue

            episode_files = sorted(lang_dir.glob('episode_*.json'))
            if not episode_files:
                continue

            output_dir = self.review_dir / '04_tagged' / lang

            self.generate_prompt_log(
                output_dir,
                ['EMOTIONAL_TAGGING_PROMPT'],
                "Stage 4: Emotion Tagging",
                f"Target Language: {lang.upper()}"
            )

            # Generate episode markdowns
            episodes_dir = self._ensure_dir(output_dir / 'episodes')
            for ep_file in episode_files:
                self.generate_episode_md(ep_file, episodes_dir)

            # Generate merged review
            self.generate_merged_review(
                episode_files, output_dir,
                "Emotion Tagged", language=lang
            )

            generated = True

        return generated

    def generate_stage_5_review(self) -> bool:
        """
        Generate review files for Stage 5: Audio Setup

        Source: 05_audio_setup/audio_config.json
        Output: _review/05_audio/
        """
        source_dir = self.series_folder / '05_audio_setup'
        config_file = source_dir / 'audio_config.json'

        if not config_file.exists():
            return False

        output_dir = self._ensure_dir(self.review_dir / '05_audio')

        # Generate prompt log
        self.generate_prompt_log(
            output_dir,
            [
                'VOICE_VARIABLE_EXTRACTION_PROMPT',
                'MUSIC_GENERATION_PROMPT',
                'SERIES_SUMMARY_PROMPT',
                'VOICE_CHARACTER_PROMPT'
            ],
            "Stage 5: Audio Setup"
        )

        # Generate settings review
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)

        settings_path = output_dir / '__SETTINGS_REVIEW.md'

        lines = []
        lines.append(f"# {self.series_name} - Audio Settings Review")
        lines.append("")
        lines.append(f"> Generated: {self._get_timestamp()}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # Series Summary
        series_summary = config.get('series_summary', {})
        if series_summary:
            lines.append("## Series Summary")
            lines.append("")
            lines.append(f"**Title**: {series_summary.get('title', 'N/A')}")
            lines.append(f"**Genre**: {series_summary.get('genre', 'N/A')}")
            lines.append(f"**Setting**: {series_summary.get('setting', 'N/A')}")
            lines.append("")
            lines.append("**Synopsis**:")
            lines.append(series_summary.get('synopsis', 'N/A'))
            lines.append("")
            lines.append("---")
            lines.append("")

        # Voice Characters
        voice_chars = config.get('voice_characters', [])
        if voice_chars:
            lines.append("## Voice Characters")
            lines.append("")
            for vc in voice_chars:
                lines.append(f"### {vc.get('character_name', 'Unknown')}")
                lines.append("")
                lines.append(f"- **Role**: {vc.get('role', 'N/A')}")
                lines.append(f"- **Age**: {vc.get('age', 'N/A')}")
                lines.append(f"- **Gender**: {vc.get('gender', 'N/A')}")
                lines.append(f"- **Voice Type**: {vc.get('voice_type', 'N/A')}")
                lines.append(f"- **Description**: {vc.get('description', 'N/A')}")
                lines.append("")
            lines.append("---")
            lines.append("")

        # Music Settings
        music_config = config.get('music_config', {})
        if music_config:
            lines.append("## Music Configuration")
            lines.append("")
            lines.append(f"**Primary Genre**: {music_config.get('primary_genre', 'N/A')}")
            lines.append(f"**Mood**: {music_config.get('mood', 'N/A')}")
            lines.append(f"**Tempo**: {music_config.get('tempo', 'N/A')}")
            lines.append("")

            # Music prompts if available
            music_prompts = music_config.get('generation_prompts', [])
            if music_prompts:
                lines.append("### Generation Prompts")
                lines.append("")
                for mp in music_prompts:
                    lines.append(f"- {mp}")
            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("## [Review Notes]")
        lines.append("<!-- Reviewer: Add your feedback on audio settings here -->")
        lines.append("")

        with open(settings_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        return True

    # =========================================================================
    # Main Entry Points
    # =========================================================================

    def generate_stage_review(self, stage_num) -> bool:
        """
        Generate review files for a specific stage.

        Args:
            stage_num: Stage number (1, 2, '2a', 3, '3a', 4, 5, etc.)

        Returns:
            True if review was generated, False otherwise
        """
        stage_generators = {
            1: self.generate_stage_1_review,
            2: self.generate_stage_2_review,
            '2a': lambda: True,  # QA stage - no review needed
            3: self.generate_stage_3_review,
            '3a': self.generate_stage_3a_review,
            4: self.generate_stage_4_review,
            5: self.generate_stage_5_review,
            6: lambda: True,  # TTS generation - audio files
            '6a': lambda: True,  # TTS QA - no review needed
            7: lambda: True,  # Audio mixing - final audio files
        }

        generator = stage_generators.get(stage_num)
        if generator:
            return generator()
        return False

    def generate_all_reviews(self) -> Dict[str, bool]:
        """
        Generate review files for all available stages.

        Returns:
            Dict mapping stage names to success status
        """
        results = {}

        stages = [
            (1, 'Episode Split'),
            (2, 'Translation'),
            (3, 'TTS Format'),
            ('3a', 'Speaker Tagging'),
            (4, 'Emotion Tagging'),
            (5, 'Audio Setup')
        ]

        for stage_num, stage_name in stages:
            try:
                success = self.generate_stage_review(stage_num)
                results[f"Stage {stage_num}: {stage_name}"] = success
            except Exception as e:
                results[f"Stage {stage_num}: {stage_name}"] = False
                print(f"  Error generating review for stage {stage_num}: {e}")

        return results


# =========================================================================
# CLI Entry Point
# =========================================================================

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Generate human-readable review files for pipeline outputs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate all reviews for a series
  python review_generator.py "processed/Publisher/Series"

  # Generate review for specific stage
  python review_generator.py "processed/Publisher/Series" --stage 2

Output:
  _review/
  ├── 01_split/
  │   ├── __PROMPT_USED.md
  │   ├── __MERGED_REVIEW.md
  │   └── episodes/
  ├── 02_translated/{language}/
  ├── 03_formatted/{language}/
  ├── 03a_speaker_tagged/{language}/
  ├── 04_tagged/{language}/
  └── 05_audio/
"""
    )

    parser.add_argument('series_folder', type=str, help='Path to series folder')
    parser.add_argument('--stage', type=str, default=None,
                        help='Specific stage to generate review (e.g., 1, 2, 3a)')

    args = parser.parse_args()

    series_folder = Path(args.series_folder)

    if not series_folder.exists():
        print(f"Error: Series folder not found: {series_folder}")
        exit(1)

    generator = ReviewGenerator(series_folder)

    if args.stage:
        # Parse stage number
        try:
            stage_num = int(args.stage)
        except ValueError:
            stage_num = args.stage  # Keep as string (e.g., '2a', '3a')

        print(f"Generating review for Stage {stage_num}...")
        success = generator.generate_stage_review(stage_num)
        if success:
            print(f"  Review generated in: {generator.review_dir}")
        else:
            print(f"  No output found for Stage {stage_num}")
    else:
        print(f"Generating all reviews for: {series_folder.name}")
        print(f"Output: {generator.review_dir}")
        print()

        results = generator.generate_all_reviews()

        print()
        print("Results:")
        for stage_name, success in results.items():
            status = "OK" if success else "SKIP"
            print(f"  [{status}] {stage_name}")

        print()
        print(f"Review files saved to: {generator.review_dir}")
