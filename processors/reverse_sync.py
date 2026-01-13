"""
Reverse Sync: _REVIEW MD → _PROCESSED JSON
Parse modified __MERGED_REVIEW.md and sync back to individual files.

Usage:
    from processors.reverse_sync import ReverseSync

    syncer = ReverseSync(review_dir, processed_dir)
    syncer.sync_stage(stage_num=2, language='japanese')
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Optional


class ReverseSync:
    """Sync changes from _REVIEW markdown back to _PROCESSED JSON"""

    def __init__(self, review_dir: Path, processed_dir: Path):
        """
        Initialize ReverseSync.

        Args:
            review_dir: Base _REVIEW directory (e.g., _REVIEW/KR/Peex/시리즈명)
            processed_dir: Base _PROCESSED directory (series folder)
        """
        self.review_dir = Path(review_dir)
        self.processed_dir = Path(processed_dir)

    def parse_individual_episodes(self, episodes_dir: Path) -> List[Dict]:
        """
        Parse individual episode_*.md files directly.
        Use this when __MERGED_REVIEW.md is converted to .gdoc by Google Drive.

        Args:
            episodes_dir: Directory containing episode_*.md files

        Returns:
            List of {episode_number, title, content} dicts
        """
        episodes = []

        # Find all episode files
        episode_files = sorted(episodes_dir.glob('episode_*.md'))

        if not episode_files:
            print(f"  ⚠️  No episode files found in {episodes_dir}")
            return episodes

        for md_path in episode_files:
            # Extract episode number from filename
            match = re.match(r'episode_(\d+)\.md', md_path.name)
            if not match:
                continue

            ep_num = int(match.group(1))

            with open(md_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Parse the individual file
            # Format: # [Episode 001] Title
            #         **Characters**: X | **Lines**: Y
            #         ---
            #         actual content

            title = ''
            ep_content = ''

            # Extract title from header
            title_match = re.search(r'^#\s*\[Episode\s+\d+\]\s*(.*?)$', content, re.MULTILINE)
            if title_match:
                title = title_match.group(1).strip()

            # Find content after the horizontal rule
            hr_match = re.search(r'^---\s*$', content, re.MULTILINE)
            if hr_match:
                ep_content = content[hr_match.end():].strip()
            else:
                # Fallback: skip first few lines (header, stats)
                lines = content.split('\n')
                # Skip header and metadata lines
                content_start = 0
                for i, line in enumerate(lines):
                    if line.startswith('#') or line.startswith('**') or line.strip() == '---' or line.strip() == '':
                        content_start = i + 1
                    else:
                        break
                ep_content = '\n'.join(lines[content_start:]).strip()

            episodes.append({
                'episode_number': ep_num,
                'title': title,
                'content': ep_content
            })

        return episodes

    def parse_merged_review(self, merged_md_path: Path) -> List[Dict]:
        """
        Parse __MERGED_REVIEW.md and extract episode data.

        Returns:
            List of {episode_number, title, content} dicts
        """
        with open(merged_md_path, 'r', encoding='utf-8') as f:
            content = f.read()

        episodes = []

        # Split by episode anchors: <a id="episode-001"></a>
        # Pattern matches: <a id="episode-001"></a>\n\n# [Episode 001] Title
        # The title may or may not exist after the bracket
        # Title is on the same line, NOT starting with ** (which is metadata)
        episode_pattern = r'<a id="episode-(\d+)"></a>\s*\n+#\s*\[Episode\s+\d+\]\s*([^\n*]*)'

        # Find all episode boundaries
        matches = list(re.finditer(episode_pattern, content))

        if not matches:
            print(f"  ⚠️  No episodes found in {merged_md_path.name}")
            return episodes

        for i, match in enumerate(matches):
            ep_num = int(match.group(1))
            title = match.group(2).strip()

            # Get content between this episode header and next (or end)
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(content)

            ep_content = content[start_pos:end_pos]

            # Remove metadata lines and horizontal rules
            # **Characters**: X | **Lines**: Y
            # **Characters**: X,XXX
            # **Status**: ...
            ep_content = re.sub(r'\*\*Characters\*\*:.*?\n', '', ep_content)
            ep_content = re.sub(r'\*\*Status\*\*:.*?\n', '', ep_content)

            # Remove horizontal rules (---)
            ep_content = re.sub(r'^---\s*$', '', ep_content, flags=re.MULTILINE)

            # Remove warning blocks (⚠️ ... lines)
            ep_content = re.sub(r'^>.*⚠️.*$', '', ep_content, flags=re.MULTILINE)
            ep_content = re.sub(r'^>\s*$', '', ep_content, flags=re.MULTILINE)
            ep_content = re.sub(r'^>\s*Error:.*$', '', ep_content, flags=re.MULTILINE)

            # Clean up extra newlines (more than 2 consecutive)
            ep_content = re.sub(r'\n{3,}', '\n\n', ep_content)
            ep_content = ep_content.strip()

            episodes.append({
                'episode_number': ep_num,
                'title': title,
                'content': ep_content
            })

        return episodes

    def sync_to_individual_md(self, episodes: List[Dict], episodes_dir: Path) -> int:
        """
        Update individual episode_*.md files.

        Args:
            episodes: List of episode dicts from parse_merged_review
            episodes_dir: Directory containing episode_*.md files

        Returns:
            Number of files updated
        """
        updated = 0

        for ep in episodes:
            ep_num = ep['episode_number']
            md_path = episodes_dir / f'episode_{ep_num:03d}.md'

            # Generate markdown content
            title = ep.get('title', '')
            content = ep.get('content', '')

            lines = []
            if title:
                lines.append(f"# [Episode {ep_num:03d}] {title}")
            else:
                lines.append(f"# [Episode {ep_num:03d}]")
            lines.append("")

            # Calculate stats
            char_count = len(content)
            line_count = content.count('\n') + 1 if content else 0
            lines.append(f"**Characters**: {char_count:,} | **Lines**: {line_count:,}")
            lines.append("")
            lines.append("---")
            lines.append("")
            lines.append(content)
            lines.append("")

            with open(md_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))

            print(f"     ✅ {md_path.name}")
            updated += 1

        return updated

    def sync_to_json(self, episodes: List[Dict], json_dir: Path) -> int:
        """
        Update episode_*.json files in _PROCESSED.
        Preserves existing metadata fields.

        Args:
            episodes: List of episode dicts from parse_merged_review
            json_dir: Directory containing episode_*.json files

        Returns:
            Number of files updated
        """
        updated = 0

        for ep in episodes:
            ep_num = ep['episode_number']
            json_path = json_dir / f'episode_{ep_num:03d}.json'

            if not json_path.exists():
                print(f"     ⚠️  Skipped (not found): {json_path.name}")
                continue

            # Read existing JSON to preserve metadata
            with open(json_path, 'r', encoding='utf-8') as f:
                existing = json.load(f)

            # Update content and title (preserve everything else)
            existing['content'] = ep['content']
            if ep.get('title'):
                existing['title'] = ep['title']

            # Write back with same formatting
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)

            print(f"     ✅ {json_path.name}")
            updated += 1

        return updated

    def sync_stage(self, stage_num, language: str = None) -> bool:
        """
        Sync a specific stage from review to processed.

        Args:
            stage_num: Stage number (1, 2, 3, '3a', 4, etc.)
            language: Target language for stages 2+ (korean, japanese, taiwanese)

        Returns:
            True if sync successful
        """
        # Map stage numbers to directory names
        stage_dirs = {
            1: '01_split',
            2: '02_translated',
            3: '03_formatted',
            '3a': '03a_speaker_tagged',
            4: '04_tagged',
        }

        stage_key = stage_num if isinstance(stage_num, str) else stage_num
        stage_dir_name = stage_dirs.get(stage_key)

        if not stage_dir_name:
            print(f"  ❌ Unsupported stage: {stage_num}")
            return False

        # Build paths based on stage type
        if language and stage_num != 1:
            review_stage_dir = self.review_dir / stage_dir_name / language
            processed_stage_dir = self.processed_dir / stage_dir_name / language
        else:
            review_stage_dir = self.review_dir / stage_dir_name
            processed_stage_dir = self.processed_dir / stage_dir_name

        merged_md = review_stage_dir / '__MERGED_REVIEW.md'
        merged_gdoc = review_stage_dir / '__MERGED_REVIEW.md.gdoc'
        episodes_dir = review_stage_dir / 'episodes'

        episodes = []
        source_type = None

        # Priority 1: Use __MERGED_REVIEW.md if it exists (and not converted to gdoc)
        if merged_md.exists() and not merged_gdoc.exists():
            print(f"\n  📄 Parsing: {merged_md.relative_to(self.review_dir)}")
            episodes = self.parse_merged_review(merged_md)
            source_type = 'merged'

        # Priority 2: Use individual episode files if merged is missing or converted to gdoc
        if not episodes and episodes_dir.exists():
            if merged_gdoc.exists():
                print(f"\n  ⚠️  __MERGED_REVIEW.md was converted to Google Docs")
                print(f"      Using individual episode files instead...")
            else:
                print(f"\n  📄 No merged file found, using individual episodes")

            episodes = self.parse_individual_episodes(episodes_dir)
            source_type = 'individual'

        if not episodes:
            # No review files exist for this stage/language
            return False

        print(f"     Found {len(episodes)} episodes (from {source_type} files)")

        # Sync to individual MD files (only if source was merged file)
        # Skip if source was individual files (would just overwrite with same content)
        if source_type == 'merged' and episodes_dir.exists():
            print(f"\n  📁 Syncing to individual MD files...")
            md_count = self.sync_to_individual_md(episodes, episodes_dir)
            print(f"     Updated {md_count} MD files")

        # Sync to JSON files in _PROCESSED
        if processed_stage_dir.exists():
            print(f"\n  📁 Syncing to JSON files in _PROCESSED...")
            json_count = self.sync_to_json(episodes, processed_stage_dir)
            print(f"     Updated {json_count} JSON files")
        else:
            print(f"\n  ⚠️  _PROCESSED directory not found: {processed_stage_dir}")
            return False

        # Clean up .gdoc file if sync was successful
        if merged_gdoc.exists():
            try:
                merged_gdoc.unlink()
                print(f"\n  🗑️  Removed: {merged_gdoc.name}")
            except Exception as e:
                print(f"\n  ⚠️  Could not remove {merged_gdoc.name}: {e}")

        return True

    def sync_all_languages(self, stage_num) -> Dict[str, bool]:
        """
        Sync all languages for a given stage.

        Args:
            stage_num: Stage number (2, 3, '3a', 4)

        Returns:
            Dict mapping language to success status
        """
        results = {}
        languages = ['korean', 'japanese', 'taiwanese']

        for lang in languages:
            results[lang] = self.sync_stage(stage_num, lang)

        return results


# CLI entry point for standalone testing
if __name__ == '__main__':
    import argparse
    import sys

    # Add parent for imports
    sys.path.insert(0, str(Path(__file__).parent.parent))

    parser = argparse.ArgumentParser(
        description='Reverse sync: _REVIEW MD → _PROCESSED JSON',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sync Stage 1 (no language)
  python reverse_sync.py /path/to/review /path/to/processed --stage 1

  # Sync Stage 2 Japanese
  python reverse_sync.py /path/to/review /path/to/processed --stage 2 --lang japanese

  # Sync Stage 2 all languages
  python reverse_sync.py /path/to/review /path/to/processed --stage 2 --all-langs
"""
    )

    parser.add_argument('review_dir', type=str, help='_REVIEW base directory')
    parser.add_argument('processed_dir', type=str, help='_PROCESSED series directory')
    parser.add_argument('--stage', type=str, required=True,
                        help='Stage number (1, 2, 3, 3a, 4)')
    parser.add_argument('--lang', type=str, default=None,
                        help='Language (korean, japanese, taiwanese)')
    parser.add_argument('--all-langs', action='store_true',
                        help='Sync all languages for the stage')

    args = parser.parse_args()

    # Parse stage number
    try:
        stage_num = int(args.stage)
    except ValueError:
        stage_num = args.stage  # Keep as string (e.g., '3a')

    syncer = ReverseSync(args.review_dir, args.processed_dir)

    print(f"\n🔄 Reverse Sync: Stage {stage_num}")
    print(f"   Review:    {args.review_dir}")
    print(f"   Processed: {args.processed_dir}")
    print()

    if args.all_langs:
        results = syncer.sync_all_languages(stage_num)
        print("\n📊 Results:")
        for lang, success in results.items():
            status = "✅" if success else "⏭️"
            print(f"   {status} {lang}")
    else:
        success = syncer.sync_stage(stage_num, args.lang)
        if success:
            print("\n✅ Sync completed successfully")
        else:
            print("\n⚠️  No files synced (review file may not exist)")
