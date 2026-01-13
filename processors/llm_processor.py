"""
LLM Processor for Text Transformation
Handles TTS formatting, translation, and emotional tagging using Gemini or Qwen3.
"""

import os
import logging
import time
import requests
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from processors.base_processor import BaseProcessor, ProcessorType
from processors.prompts import (
    TTS_FORMAT_PROMPT_KR,
    TTS_FORMAT_PROMPT_JP,
    TTS_FORMAT_PROMPT_TW,
    TRANSLATION_PROMPT,
    EMOTIONAL_TAGGING_PROMPT,
    TERM_EXTRACTION_PROMPT,
    GLOSSARY_TRANSLATION_PROMPT,
    TAIWAN_GLOSSARY_TRANSLATION_PROMPT,
    JAPANESE_GLOSSARY_TRANSLATION_PROMPT,
    TERM_TRANSLATION_PROMPT,
    TAIWAN_TERM_TRANSLATION_PROMPT,
    JAPANESE_TERM_TRANSLATION_PROMPT,
    AUDIO_NARRATOR_PROMPT,
    SERIES_SUMMARY_PROMPT,
    VOICE_CHARACTER_PROMPT,
    VOICE_DESIGN_PROMPT_KR,
    VOICE_DESIGN_PROMPT_JP,
    VOICE_DESIGN_PROMPT_TW,
    VOICE_VARIABLE_EXTRACTION_PROMPT,
    EPISODE_TITLE_PROMPT_KR,
    EPISODE_TITLE_PROMPT_JP,
    EPISODE_TITLE_PROMPT_TW,
    MUSIC_GENERATION_PROMPT,
    CHARACTER_EXTRACTION_PROMPT,
    SPEAKER_TAGGING_PROMPT_KR,
    SPEAKER_TAGGING_PROMPT_JP,
    SPEAKER_TAGGING_PROMPT_TW
)

logger = logging.getLogger(__name__)


class LLMProcessor(BaseProcessor):
    """
    Processor for LLM-based text transformations.
    Supports:
    1. TTS Formatting (optimizing text for audio)
    2. Translation (preserving style and format)
    3. Emotional Tagging (for voice modulation)

    Models:
    - Gemini (default): gemini-2.5-flash, gemini-2.5-pro
    - Qwen3 (via Ollama API): qwen3
    """

    def __init__(self, model_type: str = None):
        super().__init__(ProcessorType.LLM_BASED)

        # Determine model type from env if not specified
        self.model_type = model_type or os.getenv('LLM_MODEL', 'gemini')
        self.logger.info(f"Initializing LLMProcessor with model: {self.model_type}")

        if self.model_type == 'qwen':
            self._init_qwen()
        else:
            self._init_gemini()

    def _init_gemini(self):
        """Initialize Gemini models"""
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash')
        self.model_pro = genai.GenerativeModel('gemini-2.5-pro')
        # Fallback model for content that gets blocked by 2.5
        self.model_fallback = genai.GenerativeModel('gemini-2.0-flash')

        # Safety settings for Gemini
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }

    def _init_qwen(self):
        """Initialize Qwen3 via Ollama API"""
        self.ollama_api_key = os.getenv('OLLAMA_API_KEY')
        self.ollama_base_url = os.getenv('OLLAMA_BASE_URL', 'https://api.ollama.ai/v1')
        self.ollama_model = os.getenv('OLLAMA_MODEL', 'qwen3')

        if not self.ollama_api_key:
            raise ValueError("OLLAMA_API_KEY not found in environment variables")

        self.logger.info(f"Qwen3 initialized: {self.ollama_base_url}, model: {self.ollama_model}")

    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main processing logic.
        
        Args:
            input_data: {
                'text': str,
                'operation': 'format' | 'translate' | 'tag',
                'params': dict (language, target_lang, etc.)
            }
            
        Returns:
            {
                'output': str (processed text),
                'metadata': dict
            }
        """
        text = input_data.get('text', '')
        operation = input_data.get('operation')
        params = input_data.get('params', {})

        # Some operations don't require text (e.g., design_voice uses params)
        text_required_ops = {'format', 'translate', 'tag', 'format_audio'}
        if not text and operation in text_required_ops:
            raise ValueError("Text content is required")
        if not operation:
            raise ValueError("Operation is required")

        start_time = time.time()
        output_text = ""
        metadata = {}

        try:
            if operation == 'format':
                language = params.get('language', 'korean')
                output_text = self.format_for_tts(text, language)
            
            elif operation == 'translate':
                source_lang = params.get('source_lang', 'korean')
                target_lang = params.get('target_lang', 'english')
                glossary = params.get('glossary')
                use_pro_model = params.get('use_pro_model', True)  # Default to Pro for accuracy

                if glossary:
                    # Format glossary for prompt
                    glossary_str = "\n".join([f"- {t['original']} → {t['translation']}" for t in glossary])
                    output_text = self.translate_with_glossary(
                        text, source_lang, target_lang, glossary_str, use_pro_model=use_pro_model
                    )
                else:
                    output_text = self.translate(text, source_lang, target_lang)

            elif operation == 'translate_segment':
                # Translate a short segment (for QA auto-fix)
                source_lang = params.get('source_lang', 'korean')
                target_lang = params.get('target_lang', 'japanese')
                context = params.get('context', '')
                glossary = params.get('glossary', {})

                output_text = self.translate_segment(
                    text, source_lang, target_lang, context, glossary
                )

            elif operation == 'translate_title':
                # Translate episode title
                source_lang = params.get('source_lang', 'korean')
                target_lang = params.get('target_lang', 'japanese')
                glossary = params.get('glossary', [])

                output_text = self.translate_title(
                    text, source_lang, target_lang, glossary
                )

            elif operation == 'tag':
                output_text = self.tag_emotions(text)

            elif operation == 'format_audio':
                language = params.get('language', 'korean')
                prompt = AUDIO_NARRATOR_PROMPT.format(language=language, text=text)
                output_text = self._generate_content(prompt)

            elif operation == 'summarize_series':
                series_name = params.get('series_name', '')
                sample_text = params.get('sample_text', text[:5000])
                prompt = SERIES_SUMMARY_PROMPT.format(series_name=series_name, sample_text=sample_text)
                output_text = self._generate_content(prompt)

            elif operation == 'design_voice':
                series_summary = params.get('series_summary', '')
                genre = params.get('genre', 'web novel')
                prompt = VOICE_CHARACTER_PROMPT.format(series_summary=series_summary, genre=genre)
                output_text = self._generate_content(prompt)

            elif operation == 'design_voice_api':
                # ElevenLabs Voice Design API optimized prompt (English-based)
                series_summary = params.get('series_summary', '')
                genre = params.get('genre', 'web novel')
                target_language = params.get('target_language', 'korean')

                # Map internal language code to display name for prompt
                language_display = {
                    'korean': 'Korean (한국어)',
                    'japanese': 'Japanese (日本語)',
                    'taiwanese': 'Taiwanese Mandarin (繁體中文)'
                }
                language_name = language_display.get(target_language, 'Korean (한국어)')

                # Use unified English prompt with language parameter
                prompt = VOICE_DESIGN_PROMPT_KR.format(
                    series_summary=series_summary,
                    genre=genre,
                    target_language=language_name
                )
                output_text = self._generate_content(prompt)

            elif operation == 'generate_title':
                series_name = params.get('series_name', '')
                episode_number = params.get('episode_number', 1)
                target_language = params.get('language', 'korean')
                output_text = self.generate_title(text, series_name, episode_number, target_language)

            elif operation == 'generate_music_prompt':
                # Generate music prompt for ElevenLabs Music API
                synopsis = params.get('synopsis', '')
                genre = params.get('genre', 'web novel')
                prompt = MUSIC_GENERATION_PROMPT.format(synopsis=synopsis, genre=genre)
                output_text = self._generate_content(prompt, temperature=0.7)
                # Clean up output - should be single line, max 400 chars
                output_text = output_text.strip().replace('\n', ' ')
                if len(output_text) > 400:
                    output_text = output_text[:400]

            elif operation == 'extract_voice_variables':
                # Extract voice design variables from synopsis (JSON output)
                import json
                import re

                series_summary = params.get('series_summary', '')
                genre = params.get('genre', 'web novel')
                target_language = params.get('target_language', 'korean')

                # Map internal language code to display name
                language_display = {
                    'korean': 'Korean',
                    'japanese': 'Japanese',
                    'taiwanese': 'Taiwanese Mandarin'
                }
                lang_name = language_display.get(target_language, 'Korean')

                prompt = VOICE_VARIABLE_EXTRACTION_PROMPT.format(
                    series_summary=series_summary,
                    genre=genre,
                    target_language=lang_name
                )

                raw_output = self._generate_content(prompt, temperature=0.3)

                # Parse JSON from output
                try:
                    # Remove markdown code blocks if present
                    if '```' in raw_output:
                        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw_output)
                        if json_match:
                            raw_output = json_match.group(1)

                    variables = json.loads(raw_output.strip())
                    output_text = json.dumps(variables, ensure_ascii=False)
                except json.JSONDecodeError:
                    self.logger.warning("Failed to parse voice variables JSON, using defaults")
                    variables = self._get_default_voice_variables(target_language)
                    output_text = json.dumps(variables, ensure_ascii=False)

                # Store parsed variables in metadata for easy access
                metadata['voice_variables'] = variables if isinstance(variables, dict) else json.loads(output_text)

            elif operation == 'extract_characters':
                # Extract character dictionary from series text
                output_text = self.extract_characters(text)

            elif operation == 'tag_speakers':
                # Tag speakers in text using character dictionary
                character_dict = params.get('character_dict', {})
                language = params.get('language', 'korean')
                output_text = self.tag_speakers(text, character_dict, language)

            elif operation == 'translate_term':
                # Translate a single term (character name, etc.)
                source_lang = params.get('source_language', 'korean')
                target_lang = params.get('target_language', 'japanese')
                output_text = self.translate_term(text, source_lang, target_lang)

            else:
                raise ValueError(f"Unknown operation: {operation}")

            metadata['processing_time'] = time.time() - start_time
            metadata['operation'] = operation
            
            return {
                'output': output_text,
                'metadata': metadata
            }

        except Exception as e:
            self.logger.error(f"LLM processing failed ({operation}): {e}")
            raise

    def validate(self, output_data: Dict[str, Any]) -> bool:
        """Validate output"""
        output = output_data.get('output')
        if not output or not isinstance(output, str):
            return False
        return True

    def format_for_tts(self, text: str, language: str = 'korean') -> str:
        """Format text for TTS optimization"""
        language_lower = language.lower()

        if language_lower == 'korean':
            prompt_template = TTS_FORMAT_PROMPT_KR
        elif language_lower == 'japanese':
            prompt_template = TTS_FORMAT_PROMPT_JP
        elif language_lower in ('taiwanese', 'traditional_chinese', 'zh-tw'):
            prompt_template = TTS_FORMAT_PROMPT_TW
        else:
            # Default to Korean prompt if unknown
            self.logger.warning(f"Unsupported language for formatting: {language}. Using Korean prompt.")
            prompt_template = TTS_FORMAT_PROMPT_KR

        prompt = prompt_template.format(text=text)
        return self._generate_content(prompt)

    def detect_language(self, text: str) -> str:
        """
        Detect the source language of text using Unicode character analysis.

        Args:
            text: Text to analyze

        Returns:
            'korean' or 'japanese' based on character distribution
        """
        if not text:
            return 'korean'  # Default

        # Sample first 2000 characters for analysis
        sample = text[:2000]

        # Count character types
        korean_count = 0
        japanese_count = 0

        for char in sample:
            code = ord(char)

            # Korean Hangul (AC00-D7AF: Syllables, 1100-11FF: Jamo)
            if (0xAC00 <= code <= 0xD7AF) or (0x1100 <= code <= 0x11FF):
                korean_count += 1

            # Japanese Hiragana (3040-309F) and Katakana (30A0-30FF)
            elif (0x3040 <= code <= 0x309F) or (0x30A0 <= code <= 0x30FF):
                japanese_count += 1

        self.logger.info(f"Language detection: Korean={korean_count}, Japanese={japanese_count}")

        if japanese_count > korean_count:
            return 'japanese'
        else:
            return 'korean'

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Translate text"""
        prompt = TRANSLATION_PROMPT.format(
            source_lang=source_lang,
            target_lang=target_lang,
            text=text
        )
        return self._generate_content(prompt)

    def translate_segment(
        self,
        segment: str,
        source_lang: str,
        target_lang: str,
        context: str = '',
        glossary: dict = None
    ) -> str:
        """
        Translate a short segment of text (for QA auto-fix).
        Uses context to ensure accurate translation.

        Args:
            segment: The Korean text segment to translate
            source_lang: Source language (korean)
            target_lang: Target language (japanese, taiwanese)
            context: Surrounding context for better translation
            glossary: Glossary dict with 'terms' list

        Returns:
            Translated segment in target language
        """
        # Map language codes to display names
        lang_display = {
            'korean': 'Korean',
            'japanese': 'Japanese',
            'taiwanese': 'Traditional Chinese (Taiwanese Mandarin)'
        }
        target_display = lang_display.get(target_lang, target_lang)

        # Format glossary terms if available
        glossary_section = ""
        if glossary and glossary.get('terms'):
            relevant_terms = []
            # Normalize text for matching (remove spaces for Korean consistency)
            normalized_segment = segment.replace(' ', '')
            normalized_context = context.replace(' ', '') if context else ''

            for term in glossary['terms']:
                # Only include terms that might be relevant to this segment
                original = term.get('original', '')
                normalized_original = original.replace(' ', '')

                # Match with normalized comparison (handles spacing variations like "서 박사" vs "서박사")
                if normalized_original in normalized_segment or normalized_original in normalized_context:
                    relevant_terms.append(f"- {term['original']} → {term['translation']}")
            if relevant_terms:
                glossary_section = f"\n\n[Glossary - Use these translations]\n" + "\n".join(relevant_terms)

        prompt = f"""[Task]
Translate the following Korean text segment to {target_display}.
Output ONLY the translated text, nothing else.

[Context]
The segment appears in this context:
"{context}"

[Korean segment to translate]
{segment}
{glossary_section}

[Translation Rules]
1. Translate naturally into {target_display}
2. Match the tone and style of the surrounding context
3. Do NOT include any Korean characters in your output
4. Do NOT add explanations or notes
5. Output ONLY the translated text

[Translated segment]"""

        result = self._generate_content(prompt, temperature=0.3)

        # Clean result - remove any markdown or extra formatting
        result = result.strip()
        if result.startswith('"') and result.endswith('"'):
            result = result[1:-1]
        if result.startswith("'") and result.endswith("'"):
            result = result[1:-1]

        return result

    def translate_title(
        self,
        title: str,
        source_lang: str,
        target_lang: str,
        glossary: list = None
    ) -> str:
        """
        Translate episode title to target language.

        Args:
            title: Episode title to translate
            source_lang: Source language (korean)
            target_lang: Target language (japanese, taiwanese)
            glossary: List of glossary terms

        Returns:
            Translated title
        """
        # Map language codes to display names
        lang_display = {
            'korean': 'Korean',
            'japanese': 'Japanese',
            'taiwanese': 'Traditional Chinese (Taiwanese Mandarin)'
        }
        target_display = lang_display.get(target_lang, target_lang)

        # Format glossary for reference
        glossary_section = ""
        if glossary:
            relevant_terms = []
            # Normalize title for matching (remove spaces for Korean consistency)
            normalized_title = title.replace(' ', '')

            for term in glossary:
                original = term.get('original', '')
                translation = term.get('translation', '')
                normalized_original = original.replace(' ', '')

                # Match with normalized comparison (handles spacing variations)
                if original and translation and normalized_original in normalized_title:
                    relevant_terms.append(f"- {original} → {translation}")
            if relevant_terms:
                glossary_section = "\n\n[Glossary]\n" + "\n".join(relevant_terms)

        prompt = f"""[Task]
Translate the following episode title from {lang_display.get(source_lang, source_lang)} to {target_display}.

[Title to translate]
{title}
{glossary_section}

[Rules]
1. Output ONLY the translated title, nothing else
2. Keep the title concise and natural in {target_display}
3. Do NOT add quotation marks or explanation
4. Do NOT change the meaning or add extra information
5. For Japanese: Use natural Japanese title style
6. For Taiwanese: Use natural Traditional Chinese title style

[Translated title]"""

        result = self._generate_content(prompt, temperature=0.3)

        # Clean result
        result = result.strip()
        if result.startswith('"') and result.endswith('"'):
            result = result[1:-1]
        if result.startswith("'") and result.endswith("'"):
            result = result[1:-1]
        # Remove any leading colon or dash
        result = result.lstrip(':').lstrip('-').strip()

        return result

    def tag_emotions(self, text: str) -> str:
        """Add emotional tags"""
        prompt = EMOTIONAL_TAGGING_PROMPT.format(text=text)
        result = self._generate_content(prompt)

        # Remove LLM preamble if present (e.g., "好的，AI語音導演就位..." or similar)
        result = self._clean_llm_preamble(result)

        return result

    def _clean_llm_preamble(self, text: str) -> str:
        """
        Remove LLM preamble/intro text that may appear before actual content.

        Common patterns:
        - Chinese: "好的，AI語音導演就位。以下是為您的文本添加了..."
        - Japanese: "はい、AI音声ディレクターです。以下は..."
        - Korean: "네, AI 음성 디렉터입니다..."
        - English: "Sure, here is the text with emotion tags..."
        """
        import re

        # List of preamble patterns to remove
        preamble_patterns = [
            # Chinese preamble patterns
            r'^好的[，,].*?[：:。]\s*\n+',
            r'^以下是.*?[：:。]\s*\n+',
            r'^AI語音導演.*?[：:。]\s*\n+',
            # Japanese preamble patterns
            r'^はい[、,].*?[：:。]\s*\n+',
            r'^以下は.*?[：:。]\s*\n+',
            # Korean preamble patterns
            r'^네[,]?\s*AI.*?[.。]\s*\n+',
            r'^다음은.*?[.。]\s*\n+',
            # English preamble patterns
            r'^(?:Sure|OK|Okay|Here)[,.]?\s+(?:here\s+)?(?:is|are).*?[:。.]\s*\n+',
            r'^(?:I\'ve|I have).*?[:。.]\s*\n+',
        ]

        cleaned = text
        for pattern in preamble_patterns:
            cleaned = re.sub(pattern, '', cleaned, count=1, flags=re.IGNORECASE | re.MULTILINE)

        return cleaned.strip()

    def generate_title(self, content: str, series_name: str, episode_number: int, language: str = 'korean') -> str:
        """
        Generate episode title from content in the specified language.

        Args:
            content: Episode content
            series_name: Series name
            episode_number: Episode number
            language: Target language ('korean', 'japanese', 'taiwanese')

        Returns:
            Generated title in the target language
        """
        # Use first 3000 chars for title generation (enough context, save tokens)
        content_sample = content[:3000] if len(content) > 3000 else content

        # Select prompt based on language
        prompt_map = {
            'korean': EPISODE_TITLE_PROMPT_KR,
            'japanese': EPISODE_TITLE_PROMPT_JP,
            'taiwanese': EPISODE_TITLE_PROMPT_TW
        }
        prompt_template = prompt_map.get(language, EPISODE_TITLE_PROMPT_KR)

        prompt = prompt_template.format(
            series_name=series_name,
            episode_number=episode_number,
            content=content_sample
        )

        title = self._generate_content(prompt, temperature=0.7)

        # Clean up the title
        title = title.strip().strip('"\'')

        # Validate length
        max_length = 30 if language == 'korean' else 40
        if len(title) > max_length:
            self.logger.warning(f"Generated title too long ({len(title)} chars), truncating")
            title = title[:max_length]

        return title

    def extract_terms(self, text: str, use_pro_model: bool = False) -> list:
        """
        Extract key terms from text for glossary creation.

        Args:
            text: Text to extract terms from
            use_pro_model: Use Gemini 2.5 Pro for large context (default: False)

        Returns:
            List of term dictionaries with 'original', 'category', and 'context'
        """
        import json

        prompt = TERM_EXTRACTION_PROMPT.format(text=text)

        # Use Pro model for large context, Flash for smaller texts
        if use_pro_model:
            self.logger.info(f"Using Gemini 2.5 Pro for term extraction ({len(text):,} chars)")
            response = self._generate_content_pro(prompt)
        else:
            response = self._generate_content(prompt)

        # Strip markdown code blocks if present (```json ... ```)
        response = response.strip()
        if response.startswith('```'):
            # Remove opening code fence
            lines = response.split('\n')
            lines = lines[1:]  # Remove first line (```json or ```)

            # Remove closing code fence
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]

            response = '\n'.join(lines).strip()

        try:
            # Parse JSON response
            terms = json.loads(response)
            self.logger.info(f"Extracted {len(terms)} terms")
            return terms
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse term extraction response: {e}")
            self.logger.error(f"Full response was: {response[:500]}...")
            return []

    def extract_terms_from_full_series(self, episodes_content: list) -> list:
        """
        Extract terms from entire series using Gemini 2.5 Pro's large context.

        Args:
            episodes_content: List of episode content strings

        Returns:
            List of term dictionaries
        """
        # Combine all episodes with markers
        combined_text = ""
        for i, content in enumerate(episodes_content, 1):
            combined_text += f"\n=== Episode {i} ===\n{content}\n"

        self.logger.info(f"Extracting terms from full series: {len(episodes_content)} episodes, {len(combined_text):,} chars")

        return self.extract_terms(combined_text, use_pro_model=True)

    def translate_term(
        self,
        term: str,
        source_lang: str,
        target_lang: str,
        category: str = 'term',
        context: str = ''
    ) -> str:
        """
        Translate a single term for glossary creation.
        Uses stricter prompt and lower temperature to prevent script generation.

        Args:
            term: Term to translate
            source_lang: Source language
            target_lang: Target language
            category: Term category (character, location, etc.)
            context: Brief context for the term

        Returns:
            Translated term (simple, concise)
        """
        import json

        # Use language-specific prompts for term translation
        if target_lang == 'traditional_chinese':
            prompt_template = TAIWAN_TERM_TRANSLATION_PROMPT
        elif target_lang in ('japanese', 'jp'):
            prompt_template = JAPANESE_TERM_TRANSLATION_PROMPT
        else:
            prompt_template = TERM_TRANSLATION_PROMPT

        prompt = prompt_template.format(
            term=term,
            source_lang=source_lang,
            target_lang=target_lang,
            category=category,
            context=context or 'N/A'
        )

        # Use temperature 0 for strict, deterministic translation
        try:
            translation = self._generate_content(prompt, temperature=0.0)

            # Strip markdown code blocks if present
            if translation.startswith('```'):
                lines = translation.split('\n')
                lines = lines[1:]  # Remove first line
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                translation = '\n'.join(lines).strip()

            # Validate length - reject if too long (likely a script)
            max_length = 100 if category == 'location' else 50
            if len(translation) > max_length:
                self.logger.warning(
                    f"Translation too long for term '{term}': {len(translation)} chars. "
                    f"Likely a script instead of simple translation."
                )
                # Return original term as fallback for overly long translations
                return term

            return translation

        except Exception as e:
            # Re-raise API errors (429, 500, etc.) so they can be handled properly
            self.logger.error(f"Term translation failed for '{term}': {e}")
            raise  # Don't fallback to original - let caller handle the error

    def translate_with_glossary(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        glossary: str,
        use_pro_model: bool = False
    ) -> str:
        """
        Translate text using glossary for consistency.

        Args:
            text: Text to translate
            source_lang: Source language (korean, japanese)
            target_lang: Target language (korean, japanese, taiwanese/traditional_chinese)
            glossary: Formatted glossary string
            use_pro_model: If True, use Gemini 2.5 Pro for more accurate glossary adherence

        Returns:
            Translated text
        """
        # Select prompt based on source and target language
        source_lower = source_lang.lower()
        target_lower = target_lang.lower()

        if source_lower == 'japanese':
            # Japanese source → use Japanese-specific prompt
            prompt_template = JAPANESE_GLOSSARY_TRANSLATION_PROMPT
        elif target_lower in ('japanese', 'jp'):
            # Korean source → Japanese target
            prompt_template = JAPANESE_GLOSSARY_TRANSLATION_PROMPT
        elif target_lower in ('taiwanese', 'traditional_chinese', 'zh-tw'):
            # Korean source → Taiwan target
            prompt_template = TAIWAN_GLOSSARY_TRANSLATION_PROMPT
        else:
            # Korean source → other targets (default)
            prompt_template = GLOSSARY_TRANSLATION_PROMPT

        prompt = prompt_template.format(
            glossary=glossary,
            source_lang=source_lang,
            target_lang=target_lang,
            text=text
        )
        if use_pro_model:
            return self._generate_content_pro(prompt)
        return self._generate_content(prompt)

    def _get_default_voice_variables(self, language: str) -> dict:
        """
        Get default voice variables for a given language.
        Used as fallback when LLM JSON parsing fails.

        Args:
            language: Target language ('korean', 'japanese', 'taiwanese')

        Returns:
            Dictionary of default voice variables in English
        """
        nationality_map = {
            'korean': 'Korean',
            'japanese': 'Japanese',
            'taiwanese': 'Taiwanese'
        }
        return {
            'age': 'around thirty',
            'gender': 'female',
            'nationality': nationality_map.get(language, 'Korean'),
            'voice_pitch': 'clear mid-range',
            'voice_texture': 'soft and steady',
            'base_emotion': 'calmly',
            'emotional_range': 'restrained',
            'speech_speed': 'moderate pace',
            'diction': 'Accurate pronunciation with clear diction',
            'style_reference': 'Perfect for audiobooks',
            'narrator_type': 'professional narrator style',
            'template_type': 'narrative',
            'characteristic_keyword': 'Warm, Steady'
        }

    def _generate_content(self, prompt: str, temperature: float = 0.3) -> str:
        """Generate content with error handling"""
        if self.model_type == 'qwen':
            return self._generate_content_qwen(prompt, temperature)
        else:
            return self._generate_content_gemini(prompt, temperature)

    def _generate_content_pro(self, prompt: str, temperature: float = 0.2) -> str:
        """Generate content using Pro model for large context tasks"""
        if self.model_type == 'qwen':
            # Qwen3 handles large context natively
            return self._generate_content_qwen(prompt, temperature)
        else:
            return self._generate_content_gemini_pro(prompt, temperature)

    def _generate_content_gemini(self, prompt: str, temperature: float = 0.3) -> str:
        """Generate content using Gemini Flash with fallback to 1.5 for blocked content"""
        try:
            response = self.model.generate_content(
                prompt,
                safety_settings=self.safety_settings,
                generation_config={'temperature': temperature}
            )
            return response.text.strip()
        except Exception as e:
            error_str = str(e)
            # If blocked by content filter, try fallback model (gemini-1.5-flash)
            if 'PROHIBITED_CONTENT' in error_str or 'block_reason' in error_str:
                self.logger.warning(f"Content blocked by Gemini 2.5, trying fallback model (1.5-flash)")
                try:
                    response = self.model_fallback.generate_content(
                        prompt,
                        safety_settings=self.safety_settings,
                        generation_config={'temperature': temperature}
                    )
                    return response.text.strip()
                except Exception as fallback_e:
                    self.logger.error(f"Fallback model also failed: {fallback_e}")
                    raise fallback_e
            self.logger.error(f"Gemini API error: {e}")
            raise

    def _generate_content_gemini_pro(self, prompt: str, temperature: float = 0.2) -> str:
        """Generate content using Gemini 2.5 Pro"""
        try:
            response = self.model_pro.generate_content(
                prompt,
                safety_settings=self.safety_settings,
                generation_config={'temperature': temperature}
            )
            return response.text.strip()
        except Exception as e:
            self.logger.error(f"Gemini Pro API error: {e}")
            raise

    def _generate_content_qwen(self, prompt: str, temperature: float = 0.3) -> str:
        """Generate content using Qwen3 via Ollama API"""
        try:
            headers = {
                'Authorization': f'Bearer {self.ollama_api_key}',
                'Content-Type': 'application/json'
            }

            payload = {
                'model': self.ollama_model,
                'messages': [
                    {'role': 'user', 'content': prompt}
                ],
                'temperature': temperature,
                'stream': False
            }

            response = requests.post(
                f'{self.ollama_base_url}/chat/completions',
                headers=headers,
                json=payload,
                timeout=120
            )
            response.raise_for_status()

            result = response.json()
            return result['choices'][0]['message']['content'].strip()

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Qwen API error: {e}")
            raise
        except (KeyError, IndexError) as e:
            self.logger.error(f"Qwen API response parsing error: {e}")
            raise

    def extract_characters(self, text: str) -> str:
        """
        Extract character dictionary from series text.

        Args:
            text: Combined text from all episodes

        Returns:
            JSON string of extracted characters
        """
        import json
        import re

        prompt = CHARACTER_EXTRACTION_PROMPT.format(text=text)

        # Use Pro model for large context (full series)
        if len(text) > 50000:
            self.logger.info(f"Using Gemini Pro for character extraction ({len(text):,} chars)")
            response = self._generate_content_pro(prompt, temperature=0.3)
        else:
            response = self._generate_content(prompt, temperature=0.3)

        # Clean response - remove markdown code blocks
        response = response.strip()
        if response.startswith('```'):
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
            if json_match:
                response = json_match.group(1)
            else:
                # Remove first and last lines if they contain ```
                lines = response.split('\n')
                if lines[0].strip().startswith('```'):
                    lines = lines[1:]
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                response = '\n'.join(lines)

        # Validate JSON
        try:
            characters = json.loads(response.strip())
            if not isinstance(characters, list):
                self.logger.warning("Character extraction returned non-list, wrapping in list")
                characters = [characters] if characters else []
            self.logger.info(f"Extracted {len(characters)} characters")
            return json.dumps(characters, ensure_ascii=False)
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse character extraction JSON: {e}")
            self.logger.error(f"Response was: {response[:500]}...")
            return "[]"

    def tag_speakers(self, text: str, character_dict: dict, language: str = 'korean') -> str:
        """
        Tag speakers in text using character dictionary.

        Args:
            text: Episode text to tag
            character_dict: Character dictionary with character info
            language: Target language ('korean', 'japanese', 'taiwanese')

        Returns:
            Text with speaker tags applied
        """
        import json

        # Select prompt based on language
        prompt_map = {
            'korean': SPEAKER_TAGGING_PROMPT_KR,
            'japanese': SPEAKER_TAGGING_PROMPT_JP,
            'taiwanese': SPEAKER_TAGGING_PROMPT_TW
        }
        prompt_template = prompt_map.get(language, SPEAKER_TAGGING_PROMPT_KR)

        # Format character dictionary for prompt
        if isinstance(character_dict, str):
            char_dict_str = character_dict
        else:
            char_dict_str = json.dumps(character_dict, ensure_ascii=False, indent=2)

        prompt = prompt_template.format(
            character_dict=char_dict_str,
            text=text
        )

        result = self._generate_content(prompt, temperature=0.3)

        # Clean LLM preamble if present
        result = self._clean_llm_preamble(result)

        return result

    # NOTE: translate_term method is defined at line ~679 with full parameters
    # (category, context). Do not duplicate here.
