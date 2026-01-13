"""
Audio Text Formatter - TTS optimization for audio narration
Based on legacy TTS_FORMATTER_PROMPT
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class AudioTextFormatter:
    """Format text for optimal TTS audio narration"""

    def __init__(self, llm_processor):
        """
        Initialize audio formatter

        Args:
            llm_processor: LLMProcessor instance for text formatting
        """
        self.llm_processor = llm_processor

    def format_for_tts(
        self,
        text: str,
        language: str = 'korean',
        episode_title: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Format text for TTS optimization

        Args:
            text: Raw text content
            language: Source language (korean, japanese, english, chinese)
            episode_title: Optional episode title to preserve

        Returns:
            Dictionary with formatted text and metadata
        """
        try:
            # Use LLM to format text for audio
            result = self.llm_processor.execute({
                'text': text,
                'operation': 'format_audio',
                'params': {
                    'language': language,
                    'episode_title': episode_title
                }
            })

            formatted_text = result['output']

            # Restore episode title if it was provided and not in output
            if episode_title and not formatted_text.startswith(episode_title):
                formatted_text = f"{episode_title}\n\n{formatted_text}"

            return {
                'output': formatted_text,
                'metadata': {
                    'language': language,
                    'original_length': len(text),
                    'formatted_length': len(formatted_text),
                    'has_title': episode_title is not None
                }
            }

        except Exception as e:
            logger.error(f"Failed to format text for TTS: {e}")
            # Return original text as fallback
            return {
                'output': text,
                'metadata': {
                    'language': language,
                    'original_length': len(text),
                    'formatted_length': len(text),
                    'error': str(e)
                }
            }

    def remove_visual_markers(self, text: str) -> str:
        """
        Remove visual markers like [Sound Effect], (emotion), etc.

        Args:
            text: Text with visual markers

        Returns:
            Cleaned text
        """
        import re

        # Remove [brackets] markers
        text = re.sub(r'\[([^\]]+)\]', '', text)

        # Remove (parenthetical) markers
        text = re.sub(r'\(([^)]+)\)', '', text)

        # Remove multiple spaces
        text = re.sub(r'\s+', ' ', text)

        # Remove multiple newlines
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)

        return text.strip()

    def optimize_sentence_structure(self, text: str, language: str = 'korean') -> str:
        """
        Optimize sentence structure for TTS

        Args:
            text: Input text
            language: Language code

        Returns:
            Optimized text
        """
        # Language-specific optimizations
        if language == 'korean':
            # For Korean TTS: already handled in LLM prompt
            # - Convert formal endings (-습니다) to plain form (-다)
            # - Spell out numbers
            # - Simplify sentences
            pass

        elif language == 'japanese':
            # For Japanese TTS: already handled in LLM prompt
            # - Use hiragana for particles
            # - Provide readings for ambiguous kanji
            pass

        return text

    def chunk_for_tts(
        self,
        text: str,
        max_chars: int = 2500,
        preserve_paragraphs: bool = True
    ) -> list:
        """
        Chunk text for TTS generation

        Args:
            text: Text to chunk
            max_chars: Maximum characters per chunk
            preserve_paragraphs: Try to preserve paragraph boundaries

        Returns:
            List of text chunks
        """
        if len(text) <= max_chars:
            return [text]

        chunks = []

        if preserve_paragraphs:
            # Split by paragraphs first
            paragraphs = text.split('\n\n')
            current_chunk = ""

            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue

                # If paragraph itself is too long, split by sentences
                if len(para) > max_chars:
                    sentences = para.split('.')
                    for sentence in sentences:
                        sentence = sentence.strip()
                        if not sentence:
                            continue

                        sentence = sentence + '.'

                        if len(current_chunk) + len(sentence) > max_chars:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                            current_chunk = sentence
                        else:
                            current_chunk += '\n' + sentence if current_chunk else sentence

                # Normal paragraph
                elif len(current_chunk) + len(para) > max_chars:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = para
                else:
                    current_chunk += '\n\n' + para if current_chunk else para

            # Add final chunk
            if current_chunk:
                chunks.append(current_chunk.strip())

        else:
            # Simple sentence-based chunking
            sentences = text.split('.')
            current_chunk = ""

            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue

                sentence = sentence + '.'

                if len(current_chunk) + len(sentence) > max_chars:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence
                else:
                    current_chunk += ' ' + sentence if current_chunk else sentence

            if current_chunk:
                chunks.append(current_chunk.strip())

        logger.info(f"Chunked text into {len(chunks)} segments")
        return chunks

    def validate_tts_text(self, text: str) -> Dict[str, Any]:
        """
        Validate text for TTS generation

        Args:
            text: Text to validate

        Returns:
            Validation result with warnings
        """
        warnings = []

        # Check for visual markers
        import re
        if re.search(r'\[([^\]]+)\]', text):
            warnings.append("Contains [bracketed] markers that should be removed")

        if re.search(r'\(([^)]+)\)', text):
            warnings.append("Contains (parenthetical) markers that should be removed")

        # Check for excessive punctuation
        if text.count('!!!') > 0 or text.count('???') > 0:
            warnings.append("Contains excessive punctuation (!!!, ???)")

        # Check for very long sentences (Korean/Japanese)
        sentences = text.split('.')
        long_sentences = [s for s in sentences if len(s) > 500]
        if long_sentences:
            warnings.append(f"Contains {len(long_sentences)} very long sentences (>500 chars)")

        # Check for numbers
        if re.search(r'\d{3,}', text):
            warnings.append("Contains numbers that should be spelled out")

        return {
            'valid': len(warnings) == 0,
            'warnings': warnings,
            'length': len(text)
        }
