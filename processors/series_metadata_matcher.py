"""
Series Metadata Matcher
Match origin filenames to authoritative series metadata from CSV
"""

import csv
import re
import sys
from pathlib import Path
from difflib import SequenceMatcher
from typing import Dict, Any, Optional, List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import Config


class SeriesMetadataMatcher:
    """Match series names to authoritative CSV metadata"""

    def __init__(self, csv_path: str = None):
        # Use Google Drive IP LIST.csv by default
        if csv_path is None:
            if Config._GOOGLE_DRIVE:
                self.csv_path = Config._GOOGLE_DRIVE / "IP_LIST.csv"
            else:
                # Fallback to local data folder
                self.csv_path = Config.DATA_DIR / "IP_LIST.csv"
        else:
            self.csv_path = Path(csv_path)
        self.series_data = []
        self._load_csv()

    def _load_csv(self):
        """Load CSV file into memory"""
        if not self.csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self.csv_path}")

        with open(self.csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            self.series_data = list(reader)

        print(f"📊 Loaded {len(self.series_data)} series from CSV")

    def _clean_filename(self, filename: str) -> str:
        """Clean filename for better matching"""
        # Remove extension
        name = filename.replace('.txt', '').replace('.TXT', '')

        # Remove common patterns
        patterns = [
            r'^txt\s*',  # txt prefix
            r'_\d+-\d+화.*$',  # episode ranges
            r'_\d+-\d+.*$',  # episode ranges
            r'_연재형$',  # serialization type
            r'_완결형$',  # completion type
            r'\(.*?외전.*?\)',  # extras
            r'\[.*?\]',  # publisher tags
        ]

        for pattern in patterns:
            name = re.sub(pattern, '', name)

        # Remove common suffixes like "_전체", "_수정본", "_최종" etc.
        suffix_patterns = [
            r'_전체$',
            r'_수정본$',
            r'_최종$',
            r'_완성$',
            r'_final$',
        ]
        for pattern in suffix_patterns:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)

        # Remove author prefix (e.g., "류향_" from "류향_저스트 더 투 오브 어스")
        # Only match exactly 2 char Korean names to avoid removing title parts
        # (most Korean names are 2 chars like 류향, 김철, 이강 etc.)
        author_pattern = r'^[가-힣]{2}_'
        name = re.sub(author_pattern, '', name)

        # Convert underscores to spaces for matching (e.g., "사랑의_빚" -> "사랑의 빚")
        name = name.replace('_', ' ')

        # Clean up
        name = name.strip()
        name = re.sub(r'\s+', ' ', name)

        return name

    def _similarity_score(self, str1: str, str2: str) -> float:
        """Calculate similarity between two strings"""
        return SequenceMatcher(None, str1.lower(), str2.lower()).ratio()

    def _find_best_match(self, filename: str, cleaned_name: str) -> Optional[Dict[str, Any]]:
        """Find best matching series from CSV"""
        best_match = None
        best_score = 0.0

        for series in self.series_data:
            series_name = series.get('title', '')

            # Strategy 1: Exact match in original filename
            if series_name in filename:
                return series

            # Strategy 2: Exact match in cleaned name
            if series_name == cleaned_name:
                return series

            # Strategy 3: Fuzzy match (keep track of best)
            score = self._similarity_score(cleaned_name, series_name)
            if score > best_score:
                best_score = score
                best_match = series

        # Only return fuzzy match if score is high enough
        if best_score >= 0.8:  # 80% similarity threshold
            return best_match

        return None

    def _extract_author_from_filename(self, filename: str) -> Optional[str]:
        """Extract author name from filename (fallback)"""
        author_match = re.match(r'^([가-힣a-zA-Z]+)_', filename.replace('.txt', ''))
        if author_match:
            return author_match.group(1)
        return None

    def match(self, filename: str) -> Dict[str, Any]:
        """
        Match filename to CSV metadata

        Args:
            filename: Original filename (e.g., "류향_저스트 더 투 오브 어스_연재형.txt")

        Returns:
            {
                'original_filename': str,
                'series_name': str,
                'series_code': str or None,
                'genre': str or None,
                'publisher': str or None,
                'default_voice_id': str or None,
                'default_voice_id_jp': str or None,
                'female_voice_id': str or None,
                'male_voice_id': str or None,
                'matched': bool,  # True if matched to CSV
                'match_score': float  # Similarity score (0-1)
            }
        """
        cleaned_name = self._clean_filename(filename)
        matched_series = self._find_best_match(filename, cleaned_name)

        if matched_series:
            # Successful CSV match
            return {
                'original_filename': filename,
                'series_name': matched_series.get('title', cleaned_name),
                'series_code': matched_series.get('series_code', '').strip() or None,
                'genre': matched_series.get('genre', '').strip() or None,
                'publisher': matched_series.get('cp', '').strip() or None,
                'default_voice_id': matched_series.get('default_voice_id', '').strip() or None,
                'default_voice_id_jp': matched_series.get('default_voice_id_jp', '').strip() or None,
                'female_voice_id': matched_series.get('female_voice_id', '').strip() or None,
                'male_voice_id': matched_series.get('male_voice_id', '').strip() or None,
                'matched': True,
                'match_score': 1.0 if matched_series.get('title') in filename else 0.8
            }
        else:
            # Fallback: Use cleaned name
            return {
                'original_filename': filename,
                'series_name': cleaned_name,
                'series_code': None,
                'genre': None,
                'publisher': None,
                'default_voice_id': None,
                'default_voice_id_jp': None,
                'female_voice_id': None,
                'male_voice_id': None,
                'matched': False,
                'match_score': 0.0
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
                    'series_name': str,
                    'author': str or None,
                    'series_code': str or None,
                    'genre': str or None,
                    'publisher': str or None,
                    'matched': bool,
                    'match_score': float
                }
            }
        """
        filename = inputs['filename']
        result = self.match(filename)

        return {
            'output': result,
            'metadata': {
                'processor': 'SeriesMetadataMatcher',
                'version': '1.0.0',
                'csv_path': str(self.csv_path),
                'total_series': len(self.series_data)
            }
        }
