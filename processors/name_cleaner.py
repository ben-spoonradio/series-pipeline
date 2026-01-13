"""
Name Cleaner Processor
Cleans folder and file names by removing publisher/author suffixes and special characters
"""

from typing import Dict, Any, List
import re
import logging

from processors.base_processor import BaseProcessor, ProcessorType

logger = logging.getLogger(__name__)


class NameCleaner(BaseProcessor):
    """
    File and folder name cleaner processor

    Removes unwanted suffixes and patterns:
    - Publisher suffixes (_KADOKAWA, _ステキコンテンツ, _SUTEKI CONTENTS, etc.)
    - Author suffixes (Title_Author → Title)
    - Special characters and whitespace normalization
    - Multi-language support (Korean, Japanese, English)
    """

    def __init__(self):
        super().__init__(ProcessorType.RULE_BASED)

        # Publisher suffix patterns (case-insensitive)
        self.publisher_patterns = [
            # Japanese publishers
            r'_KADOKAWA',
            r'_kadokawa',
            r'_ステキコンテンツ',
            r'_SUTEKI CONTENTS',
            r'_suteki contents',
            r'_小学館',
            r'_講談社',
            r'_集英社',

            # Korean publishers
            r'_문피아',
            r'_조아라',
            r'_카카오페이지',
            r'_네이버',
            r'_리디북스',
            r'_munpia',
            r'_joara',
            r'_kakaopage',
            r'_naver',
            r'_ridibooks',

            # English publishers
            r'_penguin',
            r'_harpercollins',
            r'_simon_schuster',
            r'_macmillan',
        ]

    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Clean file or folder name

        Args:
            input_data: {
                'name': str (filename or folder name to clean),
                'params': {
                    'remove_publisher': bool (default: True),
                    'remove_author': bool (default: True),
                    'sanitize_special_chars': bool (default: True),
                    'language': str (korean, japanese, english, default: auto-detect)
                }
            }

        Returns:
            {
                'output': str (cleaned name),
                'metadata': {
                    'original_name': str,
                    'changes_made': list[str],
                    'publisher_removed': str or None,
                    'author_removed': str or None
                }
            }
        """
        name = input_data.get('name', '')
        params = input_data.get('params', {})

        if not name:
            raise ValueError("Name is required")

        original_name = name
        changes_made = []
        publisher_removed = None
        author_removed = None

        # Extract extension if present
        has_extension = '.' in name and not name.startswith('.')
        if has_extension:
            name_part, extension = name.rsplit('.', 1)
        else:
            name_part = name
            extension = None

        # Step 1: Remove publisher suffixes
        if params.get('remove_publisher', True):
            cleaned, publisher = self._remove_publisher_suffix(name_part)
            if cleaned != name_part:
                changes_made.append(f"Removed publisher: {publisher}")
                publisher_removed = publisher
                name_part = cleaned

        # Step 2: Remove author suffix (Title_Author pattern)
        if params.get('remove_author', True):
            cleaned, author = self._remove_author_suffix(name_part)
            if cleaned != name_part:
                changes_made.append(f"Removed author: {author}")
                author_removed = author
                name_part = cleaned

        # Step 3: Sanitize special characters
        if params.get('sanitize_special_chars', True):
            cleaned = self._sanitize_special_chars(name_part)
            if cleaned != name_part:
                changes_made.append("Sanitized special characters")
                name_part = cleaned

        # Reconstruct with extension
        if has_extension and extension:
            final_name = f"{name_part}.{extension}"
        else:
            final_name = name_part

        return {
            'output': final_name,
            'metadata': {
                'original_name': original_name,
                'changes_made': changes_made,
                'publisher_removed': publisher_removed,
                'author_removed': author_removed,
                'extension': extension
            }
        }

    def validate(self, output_data: Dict[str, Any]) -> bool:
        """Validate cleaning output"""
        cleaned_name = output_data.get('output', '')

        # Check if name is not empty
        if not cleaned_name or not cleaned_name.strip():
            self.logger.warning("Cleaned name is empty")
            return False

        # Check if name has minimum length (at least 1 character)
        if len(cleaned_name.strip()) < 1:
            self.logger.warning("Cleaned name too short")
            return False

        return True

    def _remove_publisher_suffix(self, name: str) -> tuple[str, str | None]:
        """
        Remove publisher suffixes

        Args:
            name: Folder or file name

        Returns:
            (cleaned_name, removed_publisher)
        """
        original_name = name

        for pattern in self.publisher_patterns:
            if re.search(pattern, name, re.IGNORECASE):
                # Extract the matched publisher
                match = re.search(pattern, name, re.IGNORECASE)
                if match:
                    publisher = match.group(0)
                    # Remove the pattern
                    name = re.sub(pattern, '', name, flags=re.IGNORECASE)
                    return name.strip(), publisher.strip('_')

        return name, None

    def _remove_author_suffix(self, name: str) -> tuple[str, str | None]:
        """
        Remove author suffix from Title_Author pattern

        Japanese pattern: Title_Author_Publisher → Title_Author (publisher removed) → Title
        Korean pattern: Title_Author → Title
        English pattern: Title_Author → Title

        Args:
            name: Folder or file name (after publisher removal)

        Returns:
            (cleaned_name, removed_author)
        """
        if '_' not in name:
            return name, None

        parts = name.split('_')

        # If there are 2+ parts, assume last part is author
        if len(parts) >= 2:
            # Remove last part (author)
            author = parts[-1]
            cleaned_name = '_'.join(parts[:-1])
            return cleaned_name.strip(), author.strip()

        return name, None

    def _sanitize_special_chars(self, name: str) -> str:
        """
        Sanitize special characters and whitespace

        - Remove leading/trailing whitespace
        - Replace multiple spaces with single space
        - Remove control characters
        - Keep alphanumeric, spaces, hyphens, underscores, and Unicode characters
        """
        # Remove control characters
        name = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', name)

        # Replace multiple spaces with single space
        name = re.sub(r'\s+', ' ', name)

        # Remove leading/trailing whitespace
        name = name.strip()

        # Remove leading/trailing underscores or hyphens
        name = name.strip('_-')

        return name

    def clean_batch(self, names: List[str], params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Clean multiple names in batch

        Args:
            names: List of names to clean
            params: Cleaning parameters

        Returns:
            List of {original, cleaned, metadata} dicts
        """
        if params is None:
            params = {}

        results = []
        for name in names:
            try:
                result = self.execute({
                    'name': name,
                    'params': params
                })
                results.append({
                    'original': name,
                    'cleaned': result['output'],
                    'metadata': result['metadata']
                })
            except Exception as e:
                self.logger.error(f"Error cleaning name '{name}': {e}")
                results.append({
                    'original': name,
                    'cleaned': name,  # Keep original on error
                    'metadata': {'error': str(e)}
                })

        return results
