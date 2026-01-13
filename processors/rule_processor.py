"""
Rule-Based Processor
Handles deterministic text processing: standardization, chunking, cleaning
Reuses logic from legacy IP/standardize_files.py
"""

import re
from typing import Dict, Any, List, Optional
import logging

from .base_processor import BaseProcessor, ProcessorType

logger = logging.getLogger(__name__)


class RuleProcessor(BaseProcessor):
    """
    Rule-based processor for deterministic text operations

    Capabilities:
    - Text standardization (remove markup, normalize whitespace)
    - Chapter extraction
    - Smart text chunking (sentence-aware)
    - Format cleaning
    """

    def __init__(self):
        super().__init__(ProcessorType.RULE_BASED)

    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process text using rule-based methods

        Args:
            input_data: {
                'operation': str,  # 'standardize', 'chunk', 'extract_chapters', 'extract_episode_metadata'
                'text': str,       # Input text
                'params': dict     # Optional parameters
            }

        Returns:
            {
                'operation': str,
                'output': Any,     # Processed result
                'metadata': dict   # Processing metadata
            }
        """
        operation = input_data.get('operation')
        text = input_data.get('text', '')
        params = input_data.get('params', {})

        if operation == 'standardize':
            output = self.standardize_text(text)
            metadata = {'original_length': len(text), 'standardized_length': len(output)}

        elif operation == 'chunk':
            max_size = params.get('max_size', 2500)
            output = self.chunk_text(text, max_size)
            metadata = {'total_chunks': len(output), 'chunk_size': max_size}

        elif operation == 'extract_chapters':
            output = self.extract_chapters(text)
            metadata = {'total_chapters': len(output)}

        elif operation == 'extract_episode_metadata':
            filename = params.get('filename', '')
            language = params.get('language', 'korean')
            output = self.extract_episode_metadata(text, filename, language)
            metadata = {'episode_number': output.get('episode_number'), 'has_title': bool(output.get('title'))}

        else:
            raise ValueError(f"Unknown operation: {operation}")

        return {
            'operation': operation,
            'output': output,
            'metadata': metadata
        }

    def validate(self, output_data: Dict[str, Any]) -> bool:
        """Validate rule processor output"""
        if 'output' not in output_data:
            return False

        output = output_data['output']

        # Check output is not empty
        if isinstance(output, str) and not output.strip():
            return False
        if isinstance(output, list) and len(output) == 0:
            return False

        return True

    # ===== Text Standardization =====

    def standardize_text(self, text: str) -> str:
        """
        Standardize text for TTS processing

        Operations:
        - Remove HTML/Markdown tags
        - Normalize whitespace
        - Fix common formatting issues
        - Preserve paragraph structure

        Args:
            text: Raw text

        Returns:
            Standardized text
        """
        if not text:
            return ""

        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)

        # Remove Markdown headers but preserve content
        text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)

        # Remove Markdown links but keep text: [text](url) -> text
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

        # Remove Markdown bold/italic: **text** or *text* -> text
        text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^\*]+)\*', r'\1', text)

        # Remove multiple spaces
        text = re.sub(r' +', ' ', text)

        # Remove trailing whitespace per line
        text = '\n'.join(line.rstrip() for line in text.split('\n'))

        # Remove excessive blank lines (more than 2)
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Strip leading/trailing whitespace
        text = text.strip()

        return text

    # ===== Chapter Extraction =====

    def extract_chapters(self, text: str) -> List[Dict[str, str]]:
        """
        Extract chapters from text

        Assumes chapters are marked by:
        - Lines starting with "Chapter", "Ch.", "Episode", "Ep.", or numbers
        - Or H1 headers (# Title)

        Args:
            text: Full text content

        Returns:
            List of {'title': str, 'content': str}
        """
        chapters = []

        # Pattern for chapter headers
        # Matches: Chapter 1, Ch. 1, Episode 1, Ep. 1, 1., # Chapter Title
        chapter_pattern = r'^(?:Chapter|Ch\.|Episode|Ep\.)\s*\d+|^\d+\.|^# .+'

        lines = text.split('\n')
        current_title = "Prologue"
        current_content = []

        for line in lines:
            # Check if line is a chapter header
            if re.match(chapter_pattern, line.strip(), re.IGNORECASE):
                # Save previous chapter
                if current_content:
                    chapters.append({
                        'title': current_title,
                        'content': '\n'.join(current_content).strip()
                    })

                # Start new chapter
                current_title = line.strip().lstrip('#').strip()
                current_content = []
            else:
                # Add to current chapter
                current_content.append(line)

        # Add last chapter
        if current_content:
            chapters.append({
                'title': current_title,
                'content': '\n'.join(current_content).strip()
            })

        return chapters

    # ===== Smart Text Chunking =====

    def chunk_text(self, text: str, max_size: int = 2500) -> List[str]:
        """
        Split text into chunks with sentence awareness

        Strategy:
        - Split by sentences (periods, question marks, exclamation marks)
        - Combine sentences until max_size is reached
        - Preserve sentence boundaries

        Args:
            text: Input text
            max_size: Maximum chunk size in characters

        Returns:
            List of text chunks
        """
        if not text:
            return []

        # Split into sentences
        sentences = self._split_into_sentences(text)

        chunks = []
        current_chunk = []
        current_length = 0

        for sentence in sentences:
            sentence_length = len(sentence)

            # If single sentence exceeds max_size, split it anyway
            if sentence_length > max_size:
                # Save current chunk if exists
                if current_chunk:
                    chunks.append(' '.join(current_chunk))
                    current_chunk = []
                    current_length = 0

                # Split long sentence
                chunks.append(sentence)
                continue

            # Check if adding this sentence exceeds max_size
            if current_length + sentence_length + 1 > max_size:
                # Save current chunk
                chunks.append(' '.join(current_chunk))
                current_chunk = [sentence]
                current_length = sentence_length
            else:
                # Add to current chunk
                current_chunk.append(sentence)
                current_length += sentence_length + 1  # +1 for space

        # Add final chunk
        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return chunks

    def _split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences

        Handles:
        - Korean: .!?。 followed by space or newline
        - Japanese: 。！？followed by anything
        - English: .!? followed by space or uppercase

        Args:
            text: Input text

        Returns:
            List of sentences
        """
        # Split by common sentence terminators
        # Pattern: .!?。！？ followed by whitespace or newline
        sentences = re.split(r'([.!?。！？][\s\n]+)', text)

        # Reconstruct sentences with punctuation
        result = []
        for i in range(0, len(sentences) - 1, 2):
            sentence = sentences[i] + sentences[i + 1].strip()
            sentence = sentence.strip()
            if sentence:
                result.append(sentence)

        # Handle last sentence if no punctuation
        if len(sentences) % 2 == 1:
            last = sentences[-1].strip()
            if last:
                result.append(last)

        return result

    # ===== Utility Methods =====

    def normalize_whitespace(self, text: str) -> str:
        """Normalize all whitespace to single spaces"""
        return ' '.join(text.split())

    def remove_special_characters(self, text: str, keep: str = '') -> str:
        """
        Remove special characters except those specified

        Args:
            text: Input text
            keep: Characters to keep (e.g., '.!?,')

        Returns:
            Cleaned text
        """
        # Keep alphanumeric, whitespace, and specified characters
        pattern = f'[^\\w\\s{re.escape(keep)}]'
        return re.sub(pattern, '', text)

    def count_words(self, text: str) -> int:
        """Count words in text (whitespace-separated)"""
        return len(text.split())

    def count_sentences(self, text: str) -> int:
        """Count sentences in text"""
        return len(self._split_into_sentences(text))

    def get_text_statistics(self, text: str) -> Dict[str, int]:
        """
        Get text statistics

        Returns:
            {
                'characters': int,
                'words': int,
                'sentences': int,
                'lines': int
            }
        """
        return {
            'characters': len(text),
            'words': self.count_words(text),
            'sentences': self.count_sentences(text),
            'lines': text.count('\n') + 1
        }

    # ===== Episode Metadata Extraction =====

    def extract_episode_metadata(
        self,
        text: str,
        filename: str = '',
        language: str = 'korean'
    ) -> Dict[str, Any]:
        """
        Extract episode metadata from text and filename

        Args:
            text: Episode content
            filename: Original filename (e.g., "episode_0001.txt", "5화.txt")
            language: Content language (korean, japanese, english)

        Returns:
            {
                'episode_number': int,
                'title': str or None,
                'formatted_filename': str,  # 001_Title.txt
                'tts_header': str,          # "에피소드 오 - 제목" or "Episode 5 - Title"
                'content': str              # Original content
            }
        """
        episode_number = None
        title = None

        # Strategy 1: Extract from filename
        if filename:
            episode_number = self._extract_episode_number_from_filename(filename)

        # Strategy 2: Extract from first line of content
        if not episode_number or not title:
            first_line_data = self._extract_episode_from_first_line(text, language)
            if not episode_number:
                episode_number = first_line_data.get('episode_number')
            if not title:
                title = first_line_data.get('title')

        # Strategy 3: Extract from Japanese metadata block
        if language == 'japanese' and not title:
            jp_metadata = self._extract_japanese_metadata(text)
            if not title:
                title = jp_metadata.get('title')
            if not episode_number:
                episode_number = jp_metadata.get('episode_number')

        # Default episode number if not found
        if not episode_number:
            episode_number = 1

        # Generate formatted outputs
        formatted_filename = self._format_episode_filename(episode_number, title)
        tts_header = self._format_tts_header(episode_number, title, language)

        return {
            'episode_number': episode_number,
            'title': title,
            'formatted_filename': formatted_filename,
            'tts_header': tts_header,
            'content': text
        }

    def _extract_episode_number_from_filename(self, filename: str) -> Optional[int]:
        """
        Extract episode number from filename

        Patterns:
        - episode_0001.txt -> 1
        - 005_Title.txt -> 5
        - Episode 12.txt -> 12
        - 3화.txt -> 3
        """
        # Pattern 1: episode_0001, episode_1
        match = re.search(r'episode[_\s]*(\d+)', filename, re.IGNORECASE)
        if match:
            return int(match.group(1))

        # Pattern 2: 001_Title, 05_Title
        match = re.search(r'^(\d+)_', filename)
        if match:
            return int(match.group(1))

        # Pattern 3: N화 (Korean)
        match = re.search(r'(\d+)화', filename)
        if match:
            return int(match.group(1))

        # Pattern 4: Just a number at start
        match = re.search(r'^(\d+)', filename)
        if match:
            return int(match.group(1))

        return None

    def _extract_episode_from_first_line(
        self,
        text: str,
        language: str = 'korean'
    ) -> Dict[str, Any]:
        """
        Extract episode number and title from first line

        Korean patterns:
        - "#1화" -> number=1, title=None
        - "5화 - 제목" -> number=5, title="제목"
        - "**12화 - 제목**" -> number=12, title="제목"

        English patterns:
        - "Chapter 1" -> number=1, title=None
        - "Episode 5 - Title" -> number=5, title="Title"
        """
        if not text:
            return {}

        first_line = text.split('\n')[0].strip()

        if language == 'korean':
            # Korean pattern: N화
            pattern = r'^[\s#*]*(\d+)화\s*-?\s*(.*?)[\s*]*$'
            match = re.match(pattern, first_line)
            if match:
                number = int(match.group(1))
                title = match.group(2).strip() if match.group(2) else None
                return {'episode_number': number, 'title': title}

        # Generic pattern: Chapter/Episode N - Title
        pattern = r'^[\s#*]*(?:Chapter|Episode|Ep\.?|Ch\.?)\s*(\d+)\s*-?\s*(.*?)[\s*]*$'
        match = re.match(pattern, first_line, re.IGNORECASE)
        if match:
            number = int(match.group(1))
            title = match.group(2).strip() if match.group(2) else None
            return {'episode_number': number, 'title': title}

        return {}

    def _extract_japanese_metadata(self, text: str) -> Dict[str, Any]:
        """
        Extract metadata from Japanese formatted content

        Format:
        【タイトル】
        プロローグ

        【公開状態】
        公開済

        【文字数】
        1,609文字
        """
        metadata = {}

        # Extract title
        title_match = re.search(r'【タイトル】\s*\n\s*([^\n【]+)', text)
        if title_match:
            metadata['title'] = title_match.group(1).strip()

        # Extract episode number if in title (e.g., "第1話")
        if 'title' in metadata:
            ep_match = re.search(r'第(\d+)話', metadata['title'])
            if ep_match:
                metadata['episode_number'] = int(ep_match.group(1))

        return metadata

    def _format_episode_filename(self, episode_number: int, title: Optional[str] = None) -> str:
        """
        Format episode filename: 001_Title.txt

        Args:
            episode_number: Episode number
            title: Episode title (optional)

        Returns:
            Formatted filename (e.g., "001_프롤로그.txt", "005_Episode.txt")
        """
        # Zero-padded 3-digit number
        num_str = f"{episode_number:03d}"

        if title:
            # Clean title for filename (remove special characters)
            safe_title = "".join([c for c in title if c.isalnum() or c in (' ', '-', '_')])
            safe_title = safe_title.strip().replace(' ', '_')
            return f"{num_str}_{safe_title}.txt"
        else:
            return f"{num_str}_Episode.txt"

    def _format_tts_header(
        self,
        episode_number: int,
        title: Optional[str] = None,
        language: str = 'korean'
    ) -> str:
        """
        Format TTS-friendly episode header

        Args:
            episode_number: Episode number
            title: Episode title (optional)
            language: Target language

        Returns:
            TTS header string
            - Korean: "에피소드 오 - 제목"
            - Japanese: "エピソード五 - タイトル"
            - English: "Episode 5 - Title"
        """
        if language == 'korean':
            korean_num = self._number_to_korean(episode_number)
            prefix = f"에피소드 {korean_num}"
        elif language == 'japanese':
            jp_num = self._number_to_japanese(episode_number)
            prefix = f"エピソード{jp_num}"
        else:  # English
            prefix = f"Episode {episode_number}"

        if title:
            return f"{prefix} - {title}"
        else:
            return prefix

    def _number_to_korean(self, num: int) -> str:
        """
        Convert number to Korean words (1-99)

        Examples:
            1 -> "일"
            5 -> "오"
            10 -> "십"
            12 -> "십이"
            25 -> "이십오"
        """
        ones = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"]

        if num == 0:
            return "영"
        elif num < 10:
            return ones[num]
        elif num == 10:
            return "십"
        elif num < 20:
            return "십" + ones[num - 10]
        else:
            tens = num // 10
            remainder = num % 10
            result = ones[tens] + "십"
            if remainder > 0:
                result += ones[remainder]
            return result

    def _number_to_japanese(self, num: int) -> str:
        """
        Convert number to Japanese Kanji (1-99)

        Examples:
            1 -> "一"
            5 -> "五"
            10 -> "十"
            12 -> "十二"
        """
        ones = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九"]

        if num == 0:
            return "零"
        elif num < 10:
            return ones[num]
        elif num == 10:
            return "十"
        elif num < 20:
            return "十" + ones[num - 10]
        else:
            tens = num // 10
            remainder = num % 10
            result = ones[tens] + "十"
            if remainder > 0:
                result += ones[remainder]
            return result
