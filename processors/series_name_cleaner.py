"""
Series Name Cleaner
Clean series names by removing unnecessary parts (author, publisher, format info)
"""

import re
from typing import Dict, Any


class SeriesNameCleaner:
    """Clean series names for folder creation"""

    def __init__(self):
        # Patterns to remove from series names
        self.removal_patterns = [
            r'^txt\s*',  # "txt피지컬 천재배우" → "피지컬 천재배우"
            r'^txt\d+\s*',  # "txt001스캔들" → "스캔들"
            r'_\d+-\d+화.*$',  # "_1-330화(외전 포함)" → ""
            r'_\d+-\d+.*$',  # "_1-235" → ""
            r'_연재형$',  # "_연재형" → ""
            r'_완결형$',  # "_완결형" → ""
            r'\(.*?외전.*?\)',  # "(외전 포함)" → ""
            r'\[.*?\]',  # "[테라핀]" → ""
        ]

        # Author name patterns (prefix before _)
        self.author_pattern = r'^[가-힣a-zA-Z]+_'  # "류향_골든 글로리" → "골든 글로리"

    def clean(self, filename: str) -> Dict[str, str]:
        """
        Clean series name from filename

        Args:
            filename: Original filename (e.g., "류향_골든 글로리_연재형.txt")

        Returns:
            {
                'original_filename': str,
                'author': str or None,
                'series_name': str,
                'clean_filename': str
            }
        """
        # Remove extension
        name = filename.replace('.txt', '').replace('.TXT', '')

        # Extract author (if exists)
        author = None
        author_match = re.match(self.author_pattern, name)
        if author_match:
            author = author_match.group(0).rstrip('_')
            name = name[len(author_match.group(0)):]

        # Apply removal patterns
        for pattern in self.removal_patterns:
            name = re.sub(pattern, '', name)

        # Clean up spaces and special characters
        name = name.strip()
        name = re.sub(r'\s+', ' ', name)  # Multiple spaces → single space

        # Remove invalid folder name characters
        name = re.sub(r'[<>:"/\\|?*]', '', name)

        return {
            'original_filename': filename,
            'author': author,
            'series_name': name,
            'clean_filename': f"{name}.txt"
        }

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processor interface

        Args:
            inputs: {
                'filename': str
            }

        Returns:
            {
                'output': {
                    'original_filename': str,
                    'author': str or None,
                    'series_name': str,
                    'clean_filename': str
                }
            }
        """
        filename = inputs['filename']
        result = self.clean(filename)

        return {
            'output': result,
            'metadata': {
                'processor': 'SeriesNameCleaner',
                'version': '1.0.0'
            }
        }
