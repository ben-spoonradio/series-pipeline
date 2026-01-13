"""
TTS Quality Assurance Service
Verifies TTS output quality using Speech-to-Text validation

The QA system uses an "Audio-Tail Verification" approach:
1. Extract last N characters from original text (removing markers)
2. Extract last N seconds from generated audio
3. Transcribe audio using ElevenLabs STT API
4. Check if original text ending is contained in transcription
"""

import logging
import os
import re
from typing import Dict, List, Optional
from pathlib import Path
from io import BytesIO
from dataclasses import dataclass, field

import requests
from pydub import AudioSegment

logger = logging.getLogger(__name__)


# Language code mapping for ElevenLabs STT
LANGUAGE_CODE_MAP = {
    'korean': 'ko',
    'japanese': 'ja',
    'taiwanese': 'zh',  # Traditional Chinese
    'english': 'en'
}


@dataclass
class TTSQAResult:
    """Result for single chunk QA verification"""
    chunk_file: str
    chunk_index: int
    passed: bool
    original_last_chars: str = ""
    transcribed_text: str = ""
    transcribed_last_chars: str = ""
    contained: bool = False
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'chunk_file': self.chunk_file,
            'chunk_index': self.chunk_index,
            'passed': self.passed,
            'original_last_chars': self.original_last_chars,
            'transcribed_text': self.transcribed_text,
            'transcribed_last_chars': self.transcribed_last_chars,
            'contained': self.contained,
            'error': self.error
        }


@dataclass
class EpisodeQAResult:
    """Result for episode-level QA aggregation"""
    episode_number: int
    total_chunks: int
    passed_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    chunk_results: List[TTSQAResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """Episode passes if no chunks failed"""
        return self.failed_count == 0

    @property
    def pass_rate(self) -> float:
        """Calculate pass rate percentage"""
        total = self.passed_count + self.failed_count
        return (self.passed_count / total * 100) if total > 0 else 0.0


class TTSQAService:
    """
    Automated TTS quality verification using STT validation.

    Verifies that TTS-generated audio files contain the complete text
    by checking if the original text's last N characters appear in
    the transcribed audio tail.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        language: str = 'korean',
        char_count: int = 10,
        segment_duration_ms: int = 3000
    ):
        """
        Initialize TTS QA Service.

        Args:
            api_key: ElevenLabs API key (defaults to ELEVENLABS_API_KEY env var)
            language: Source language for STT (korean, japanese, taiwanese, english)
            char_count: Number of characters to extract from text end (default: 10)
            segment_duration_ms: Audio segment length for transcription in ms (default: 3000)
        """
        self.api_key = api_key or os.getenv('ELEVENLABS_API_KEY')
        if not self.api_key:
            raise ValueError(
                "ElevenLabs API key required. "
                "Set ELEVENLABS_API_KEY environment variable or pass api_key parameter."
            )

        self.language = language
        self.language_code = LANGUAGE_CODE_MAP.get(language, 'ko')
        self.char_count = char_count
        self.segment_duration_ms = segment_duration_ms
        self.base_url = "https://api.elevenlabs.io/v1"

        # Setup HTTP session with API key
        self.session = requests.Session()
        self.session.headers.update({"xi-api-key": self.api_key})

        logger.info(
            f"TTSQAService initialized: language={language} ({self.language_code}), "
            f"char_count={char_count}, segment_duration={segment_duration_ms}ms"
        )

    def extract_last_chars(
        self,
        text: str,
        char_count: Optional[int] = None,
        remove_whitespace_punctuation: bool = True
    ) -> str:
        """
        Extract last N characters from text, removing audio markers.

        Args:
            text: Original text
            char_count: Number of characters to extract (defaults to instance setting)
            remove_whitespace_punctuation: If True, remove spaces and punctuation

        Returns:
            Last N characters after cleaning
        """
        char_count = char_count or self.char_count

        # Remove [bracket] audio tags: [Sound Effect], [피아노 음악], etc.
        cleaned = re.sub(r'\[[^\]]+\]', '', text).strip()

        # Remove (parenthetical) audio tags: (emotion), (경음악), etc.
        cleaned = re.sub(r'\([^\)]+\)', '', cleaned).strip()

        # Remove SSML tags: <break time="1.5s" />, etc.
        cleaned = re.sub(r'<[^>]+>', '', cleaned).strip()

        if remove_whitespace_punctuation:
            # Keep only word characters + CJK characters
            # Korean: \uAC00-\uD7AF (Hangul syllables)
            # Japanese: \u3040-\u309F (Hiragana), \u30A0-\u30FF (Katakana)
            # Chinese: \u4E00-\u9FFF (CJK Unified Ideographs)
            cleaned = re.sub(r'[^\w\uAC00-\uD7AF\u3040-\u30FF\u4E00-\u9FFF]', '', cleaned)

        if not cleaned:
            logger.warning(f"No valid text after cleaning: {text[:100]}...")
            return ""

        # Extract last N characters
        return cleaned[-char_count:] if len(cleaned) >= char_count else cleaned

    def extract_audio_end_segment(
        self,
        audio_file: Path,
        duration_ms: Optional[int] = None
    ) -> Optional[bytes]:
        """
        Extract audio segment from end of file.

        Args:
            audio_file: Path to MP3 file
            duration_ms: Segment length in milliseconds (defaults to instance setting)

        Returns:
            Audio segment as bytes (MP3 format), or None if extraction failed
        """
        duration_ms = duration_ms or self.segment_duration_ms

        try:
            # Load audio file
            audio = AudioSegment.from_mp3(str(audio_file))
            total_duration = len(audio)

            # Extract end segment
            start_pos = max(0, total_duration - duration_ms)
            segment = audio[start_pos:]

            # Export to bytes in MP3 format
            buffer = BytesIO()
            segment.export(buffer, format="mp3")
            audio_bytes = buffer.getvalue()

            logger.debug(
                f"Extracted {len(audio_bytes)} bytes from end of {audio_file.name} "
                f"(last {duration_ms}ms of {total_duration}ms)"
            )
            return audio_bytes

        except Exception as e:
            logger.error(f"Failed to extract audio segment from {audio_file}: {e}")
            return None

    def transcribe_audio(
        self,
        audio_bytes: bytes,
        timeout: int = 60
    ) -> Optional[str]:
        """
        Transcribe audio using ElevenLabs STT API.

        Args:
            audio_bytes: Audio data in MP3 format
            timeout: Maximum wait time for result in seconds

        Returns:
            Transcribed text, or None if transcription failed
        """
        try:
            url = f"{self.base_url}/speech-to-text"

            # Prepare multipart/form-data request
            files = {'file': ('audio.mp3', audio_bytes, 'audio/mpeg')}
            data = {
                'model_id': 'scribe_v1',  # ElevenLabs STT model
                'language_code': self.language_code
            }

            logger.debug(f"Sending STT request (language: {self.language_code})...")
            response = self.session.post(url, files=files, data=data, timeout=timeout)

            if response.status_code != 200:
                logger.error(f"STT API error: HTTP {response.status_code} - {response.text}")
                return None

            # Parse response
            result = response.json()
            transcribed = result.get('text', '').strip()

            if not transcribed:
                logger.warning("Empty transcription from API")
                return None

            logger.debug(f"STT success: transcribed {len(transcribed)} chars")
            return transcribed

        except requests.exceptions.Timeout:
            logger.error(f"STT request timed out after {timeout}s")
            return None
        except Exception as e:
            logger.error(f"STT transcription failed: {e}")
            return None

    def verify_chunk_quality(
        self,
        original_text: str,
        audio_file: Path
    ) -> TTSQAResult:
        """
        QA verification for a single TTS chunk.

        Checks if the original text's last N characters appear in
        the transcribed audio tail.

        Args:
            original_text: Source text for the chunk
            audio_file: Generated audio file (MP3)

        Returns:
            TTSQAResult with verification details
        """
        result = TTSQAResult(
            chunk_file=str(audio_file),
            chunk_index=0,
            passed=False
        )

        try:
            logger.info(f"Starting QA verification for: {audio_file.name}")

            # 1. Extract last N chars from original text
            original_last = self.extract_last_chars(original_text)
            if not original_last:
                result.error = "No valid text found in original"
                logger.warning(f"QA skipped - {result.error}")
                return result
            result.original_last_chars = original_last

            # 2. Extract audio end segment
            logger.debug("Extracting audio end segment...")
            audio_segment = self.extract_audio_end_segment(audio_file)
            if not audio_segment:
                result.error = "Failed to extract audio segment"
                logger.error(f"QA failed - {result.error}")
                return result

            # 3. Transcribe audio segment
            logger.debug("Transcribing audio segment...")
            transcribed = self.transcribe_audio(audio_segment)
            if not transcribed:
                result.error = "STT transcription failed"
                logger.error(f"QA failed - {result.error}")
                return result
            result.transcribed_text = transcribed

            # 4. Extract last N chars from transcription
            transcribed_last = self.extract_last_chars(transcribed)
            result.transcribed_last_chars = transcribed_last

            # 5. Containment check: original must be in normalized transcription
            # Normalize transcription for comparison
            normalized = re.sub(r'\[[^\]]+\]', '', transcribed)  # Remove [...]
            normalized = re.sub(r'\([^\)]+\)', '', normalized)   # Remove (...)
            normalized = re.sub(r'[^\w\uAC00-\uD7AF\u3040-\u30FF\u4E00-\u9FFF]', '', normalized)

            result.contained = original_last in normalized
            result.passed = result.contained

            status = "PASS" if result.passed else "FAIL"
            logger.info(
                f"QA [{status}]: {audio_file.name} - "
                f"Original: '{original_last}' | Transcribed: '{transcribed_last}' | "
                f"Contained: {result.contained}"
            )

        except Exception as e:
            result.error = str(e)
            logger.error(f"QA verification error for {audio_file.name}: {e}")

        return result

    def verify_episode(
        self,
        episode_number: int,
        chunk_texts: List[str],
        chunk_files: List[Path]
    ) -> EpisodeQAResult:
        """
        Verify all chunks in an episode.

        Args:
            episode_number: Episode number for reporting
            chunk_texts: List of original text chunks
            chunk_files: List of corresponding audio files

        Returns:
            EpisodeQAResult with aggregated verification results
        """
        result = EpisodeQAResult(
            episode_number=episode_number,
            total_chunks=len(chunk_files)
        )

        # Handle chunk count mismatch
        max_idx = min(len(chunk_files), len(chunk_texts))
        if len(chunk_files) != len(chunk_texts):
            logger.warning(
                f"Episode {episode_number}: chunk count mismatch "
                f"({len(chunk_files)} audio vs {len(chunk_texts)} text)"
            )
            result.skipped_count = abs(len(chunk_files) - len(chunk_texts))

        # Verify each chunk
        for idx in range(max_idx):
            chunk_result = self.verify_chunk_quality(chunk_texts[idx], chunk_files[idx])
            chunk_result.chunk_index = idx
            result.chunk_results.append(chunk_result)

            if chunk_result.passed:
                result.passed_count += 1
            else:
                result.failed_count += 1

        logger.info(
            f"Episode {episode_number} QA complete: "
            f"{result.passed_count}/{result.total_chunks} passed ({result.pass_rate:.1f}%)"
        )

        return result
