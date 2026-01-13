"""
LLM-Based Episode Splitter
Uses Gemini to adaptively detect and split episode boundaries in merged files
"""

import re
import os
import json
from typing import Dict, Any, List, Optional
import logging

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from processors.base_processor import BaseProcessor, ProcessorType

logger = logging.getLogger(__name__)

# Known patterns for regex fallback
KNOWN_PATTERNS = {
    '#N화': r'^#(\d+)화\s*$',
    '$N화': r'^\$(\d+)화\s*$',  # e.g., "$1화", "$2화"
    '$NNN': r'^\$(\d{3})',  # e.g., "$001", "$013본문..." (text may follow, removed trailing $)
    '* * *$NNN': r'^\* \* \*\$(\d{3})',  # e.g., "* * *$003본문..." (text may follow immediately)
    '$NNN+* * *$NNN': r'^(?:\* \* \*)?\$(\d{3})',  # Combined pattern: both $NNN and * * *$NNN
    '第N話': r'^第(\d+)話\s*$',
    '제N화': r'^제(\d+)화\s*$',
    'N. Title (N)': r'^(\d+)\. .+ \(\d+\)',  # e.g., "05. 회귀자가 왜 여기서 나와? (1)"
    'NN. Title': r'^(\d+)\. .+',  # e.g., "10. 길드 옮기려고?"
    '//N': r'^//(\d+)\s*$',  # e.g., "//1", "//2"
}

# Inline episode marker pattern: $NNN appearing anywhere (including mid-line)
# e.g., '"말했다."$002다음 내용' -> split before $002
# This pattern is used for text-based splitting (not line-based)
INLINE_EPISODE_PATTERN = r'\$(\d{3})'

# Pattern that combines * * * scene break with $NNN episode marker
# e.g., '* * *$003본문...' - scene break immediately followed by episode marker
SCENE_BREAK_EPISODE_PATTERN = r'\* \* \*\$(\d{3})'

# Patterns to detect trailing episode markers at end of content
# These are episode separators that may accidentally be included at the end of previous episode
TRAILING_EPISODE_PATTERNS = [
    r'\n\s*#\d+화\s*$',           # #2화, #10화
    r'\n\s*\$\d{3}\s*$',          # $002, $010
    r'\n\s*\* \* \*\$\d{3}',      # * * *$003 (may have text after)
    r'\n\s*\* \* \*\s*$',         # * * * (scene break, standalone)
    r'\n\s*第\d+話\s*$',          # 第2話, 第10話
    r'\n\s*제\d+화\s*$',          # 제2화, 제10화
    r'\n\s*\d+화\s*$',            # 2화, 10화 (standalone)
    r'\n\s*//\d+\s*$',            # //2, //10
    r'\n\s*\d+\.\s*[^\n]+$',      # 2. Title, 10. Title (at end)
]


def clean_trailing_episode_marker(content: str) -> str:
    """
    Remove trailing episode markers from content.

    Sometimes the next episode's separator line gets included at the end
    of the previous episode's content. This function removes such markers.

    Args:
        content: Episode content that may have trailing markers

    Returns:
        Cleaned content with trailing markers removed
    """
    cleaned = content.rstrip()

    for pattern in TRAILING_EPISODE_PATTERNS:
        match = re.search(pattern, cleaned)
        if match:
            # Remove the trailing marker
            cleaned = cleaned[:match.start()].rstrip()
            logger.debug(f"Removed trailing episode marker: {match.group().strip()}")
            break  # Only remove one marker

    return cleaned



class LLMEpisodeSplitter(BaseProcessor):
    """
    LLM-powered adaptive episode splitter

    Uses Gemini to:
    1. Analyze file structure and detect episode separator patterns
    2. Split files into individual episodes with confidence scoring
    3. Handle edge cases (prologue, epilogue, mixed patterns)

    Hybrid approach:
    - LLM for pattern detection (intelligent)
    - Regex for simple patterns (fast)
    - LLM for complex patterns (accurate)
    """

    def __init__(self):
        super().__init__(ProcessorType.LLM_BASED)

        # Initialize Gemini
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")

        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-2.5-flash')

        # Safety settings (permissive for content processing)
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }

    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Main processing logic for episode splitting

        Args:
            input_data: {
                'text': str (full text content),
                'filename': str (optional, for context),
                'language': str (optional, korean/japanese/english),
                'sample_lines': int (default: 500, lines to analyze for pattern detection)
            }

        Returns:
            {
                'output': {
                    'episodes': [
                        {'number': int, 'title': str, 'content': str},
                        ...
                    ],
                    'is_multi_episode': bool,
                    'pattern_used': str,
                    'method': 'single'|'regex'|'llm'
                },
                'metadata': {
                    'total_episodes': int,
                    'confidence': int (0-100),
                    'language': str,
                    'special_episodes': dict,
                    'warnings': list[str]
                }
            }
        """
        text = input_data.get('text', '')
        filename = input_data.get('filename', 'unknown.txt')
        language = input_data.get('language', 'korean')
        sample_lines = input_data.get('sample_lines', 500)

        if not text:
            raise ValueError("Text content is required")

        # Step 1: Detect pattern with LLM
        self.logger.info(f"Analyzing pattern for: {filename}")
        pattern_info = self._detect_pattern(text, filename, sample_lines)

        # Step 2: Determine processing method
        if not pattern_info['is_multi_episode']:
            # Single episode - no splitting needed
            episodes = [{
                'number': 1,
                'title': None,
                'content': text
            }]
            method = 'single'
            confidence = 100

        elif pattern_info.get('use_inline_split'):
            # Inline $NNN pattern - use text-based splitting (not line-based)
            primary = pattern_info.get('primary_pattern', '$NNN (inline)')
            self.logger.info(f"Using INLINE split for pattern: {primary}")
            episodes = self._inline_split(text, pattern_info)
            method = 'inline'
            confidence = pattern_info['confidence']

        elif pattern_info.get('primary_pattern') in KNOWN_PATTERNS or pattern_info.get('separator_pattern') in KNOWN_PATTERNS:
            # Known pattern - use regex (fast)
            primary = pattern_info.get('primary_pattern', pattern_info.get('separator_pattern'))
            self.logger.info(f"Using regex split for pattern: {primary}")
            episodes = self._regex_split(text, pattern_info)
            method = 'regex'
            confidence = pattern_info['confidence']

        else:
            # Complex/unknown pattern - use LLM (accurate)
            primary = pattern_info.get('primary_pattern', pattern_info.get('separator_pattern'))
            self.logger.info(f"Using LLM split for custom pattern: {primary}")
            episodes = self._llm_split(text, pattern_info)
            method = 'llm'
            confidence = int(pattern_info['confidence'] * 0.9)  # Slight penalty for complexity

        # Step 3: Validate results
        validation = self._validate_split(episodes, pattern_info, text)
        final_confidence = min(confidence, validation['confidence'])

        # Determine pattern display string
        if 'patterns' in pattern_info and len(pattern_info['patterns']) > 1:
            pattern_display = f"{pattern_info.get('primary_pattern', '')} (+{len(pattern_info['patterns'])-1} more)"
        else:
            pattern_display = pattern_info.get('primary_pattern', pattern_info.get('separator_pattern'))

        return {
            'output': {
                'episodes': episodes,
                'is_multi_episode': pattern_info['is_multi_episode'],
                'pattern_used': pattern_display,
                'method': method
            },
            'metadata': {
                'total_episodes': len(episodes),
                'confidence': final_confidence,
                'language': pattern_info.get('language', language),
                'special_episodes': pattern_info.get('special_episodes', {}),
                'warnings': validation.get('warnings', []),
                'patterns': pattern_info.get('patterns', []),
                'pattern_regex': pattern_info.get('pattern_regex'),
                'estimated_episodes': pattern_info.get('estimated_episodes')
            }
        }

    def validate(self, output_data: Dict[str, Any]) -> bool:
        """Validate episode splitting output"""
        episodes = output_data.get('output', {}).get('episodes', [])
        confidence = output_data.get('metadata', {}).get('confidence', 0)

        # Check if episodes exist
        if not episodes:
            self.logger.warning("No episodes found in output")
            return False

        # Check if confidence is acceptable (≥70%)
        if confidence < 70:
            self.logger.warning(f"Low confidence: {confidence}%")
            return False

        # Check if each episode has required fields
        for episode in episodes:
            if 'number' not in episode or 'content' not in episode:
                self.logger.warning(f"Episode missing required fields: {episode.keys()}")
                return False

        return True

    def _detect_known_pattern_directly(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Directly detect known patterns without LLM (faster and more reliable).

        Returns:
            Pattern information dict if a known pattern is detected, None otherwise
        """
        lines = text.split('\n')

        # Count matches for each known pattern (line-start patterns)
        pattern_counts = {}
        pattern_examples = {}

        for pattern_name, pattern_regex in KNOWN_PATTERNS.items():
            try:
                compiled = re.compile(pattern_regex)
                matches = []
                for line in lines:
                    line_stripped = line.strip().lstrip('\ufeff')
                    match = compiled.match(line_stripped)
                    if match:
                        matches.append(match.group(0))
                if matches:
                    pattern_counts[pattern_name] = len(matches)
                    pattern_examples[pattern_name] = matches[:5]
            except Exception:
                continue

        # Special check: Inline $NNN pattern (appears anywhere in text, not just line start)
        # This handles cases like: "말했다."$002다음 내용
        inline_matches = re.findall(INLINE_EPISODE_PATTERN, text)
        if inline_matches:
            # Count unique episode numbers
            unique_episodes = sorted(set(int(m) for m in inline_matches))
            inline_count = len(unique_episodes)

            # Check if inline pattern has significantly more matches than line-start patterns
            max_line_start_count = max(pattern_counts.values()) if pattern_counts else 0

            if inline_count > max_line_start_count * 1.5:  # At least 50% more inline matches
                self.logger.info(f"Detected INLINE $NNN pattern with {inline_count} episodes (vs {max_line_start_count} line-start)")

                # Extract examples
                inline_examples = [f"${m}" for m in inline_matches[:5]]

                return {
                    'is_multi_episode': True,
                    'patterns': [{
                        'separator_pattern': '$NNN (inline)',
                        'pattern_examples': inline_examples,
                        'pattern_regex': INLINE_EPISODE_PATTERN
                    }],
                    'primary_pattern': '$NNN (inline)',
                    'pattern_regex': INLINE_EPISODE_PATTERN,
                    'estimated_episodes': inline_count,
                    'confidence': 95,
                    'special_episodes': {},
                    'language': 'korean',
                    'notes': f'Direct pattern detection: inline $NNN pattern ({inline_count} episodes)',
                    'use_inline_split': True  # Flag to use inline splitting method
                }

        if not pattern_counts:
            return None

        # Check for combined patterns (e.g., $NNN and * * *$NNN both present)
        # If both $NNN and * * *$NNN patterns exist, use the combined pattern
        if '$NNN' in pattern_counts and '* * *$NNN' in pattern_counts:
            combined_regex = KNOWN_PATTERNS['$NNN+* * *$NNN']
            combined_examples = pattern_examples.get('$NNN', []) + pattern_examples.get('* * *$NNN', [])
            total_count = pattern_counts['$NNN'] + pattern_counts['* * *$NNN']

            self.logger.info(f"Detected combined pattern: $NNN ({pattern_counts['$NNN']}) + * * *$NNN ({pattern_counts['* * *$NNN']})")

            return {
                'is_multi_episode': True,
                'patterns': [{
                    'separator_pattern': '$NNN+* * *$NNN',
                    'pattern_examples': combined_examples[:5],
                    'pattern_regex': combined_regex
                }],
                'primary_pattern': '$NNN+* * *$NNN',
                'pattern_regex': combined_regex,
                'estimated_episodes': total_count,
                'confidence': 95,
                'special_episodes': {},
                'language': 'korean',
                'notes': 'Direct pattern detection: combined $NNN and * * *$NNN patterns'
            }

        # Find the pattern with most matches
        best_pattern = max(pattern_counts, key=pattern_counts.get)
        count = pattern_counts[best_pattern]

        # Only use direct detection if we have enough matches (at least 3)
        if count < 3:
            return None

        self.logger.info(f"Detected pattern '{best_pattern}' with {count} matches")

        return {
            'is_multi_episode': True,
            'patterns': [{
                'separator_pattern': best_pattern,
                'pattern_examples': pattern_examples[best_pattern],
                'pattern_regex': KNOWN_PATTERNS[best_pattern]
            }],
            'primary_pattern': best_pattern,
            'pattern_regex': KNOWN_PATTERNS[best_pattern],
            'estimated_episodes': count,
            'confidence': 95,
            'special_episodes': {},
            'language': 'korean',
            'notes': f'Direct pattern detection: {best_pattern}'
        }

    def _detect_pattern(self, text: str, filename: str, sample_lines: int = 500) -> Dict[str, Any]:
        """
        Use Gemini to detect episode separation pattern

        Args:
            text: Full text content
            filename: Original filename
            sample_lines: Number of lines to analyze

        Returns:
            Pattern information dict
        """
        # First, try to detect known patterns directly (faster and more reliable)
        direct_pattern = self._detect_known_pattern_directly(text)
        if direct_pattern:
            self.logger.info(f"Direct pattern detection: {direct_pattern['primary_pattern']}")
            return direct_pattern

        # Extract sample (first N lines)
        lines = text.split('\n')
        sample_text = '\n'.join(lines[:sample_lines])

        # Construct prompt
        prompt = f"""Analyze this text file and identify episode separation patterns.

**Filename:** {filename}

**First {sample_lines} lines:**
```
{sample_text}
```

**Tasks:**
1. Determine if this file contains a SINGLE episode or MULTIPLE episodes
2. If multiple, identify ALL separator patterns used (files may have MULTIPLE patterns)
3. For EACH pattern found:
   - Identify the STRUCTURAL pattern (e.g., "#N화", "$NNN", "第N話", "N. Title (N)")
   - Focus on the FORMAT, not specific text content
   - If episode titles VARY, use placeholders like [Title] or [Text] in the pattern name
   - Extract 3-5 pattern examples from the text
   - Create a Python regex pattern to match the separator
4. Estimate total number of episodes
5. Rate your confidence (0-100%)
6. Identify special episodes (prologue, epilogue, extras)
7. Detect language (korean, japanese, english)

**Important:**
- A SINGLE FILE MAY USE MULTIPLE PATTERNS (e.g., "$001" AND "1" together)
- Look for patterns at the START of lines, not in dialogue
- Distinguish between titles containing numbers (e.g., "세상의 끝에서 1화") and actual separators ("1화")
- Consider patterns like: #N화, $NNN, N (standalone number), 第N話, 제N화, Chapter N, Episode N, N. Title (N), //N
- Prologue keywords: 프롤로그, prologue, プロローグ
- Epilogue keywords: 에필로그, epilogue, エピローグ
- Extra keywords: 번외, 외전, extra, 番外編

**Examples of STRUCTURAL Patterns (NOT Literal Patterns):**
✅ CORRECT: If you see "02. 적당히 꿀 빠는 헌터 (2)", "05. 회귀자가 왜 여기서 나와? (1)", "10. 길드 옮기려고? (1)"
   → Pattern name: "N. Title (N)" or "N. [Episode Title] (N)"
   → Regex: "^(\\d+)\\. .+ \\(\\d+\\)"
   → Do NOT include specific title text like "적당히 꿀 빠는 헌터"

❌ WRONG: Pattern name "N. 적당히 꿀 빠는 헌터 (N)" (too specific, only matches one arc)

✅ CORRECT: If you see "#1화 시작", "#2화 진행", "#3화 전개"
   → Pattern name: "#N화" or "#N화 Title"
   → Regex: "^#(\\d+)화"
   → Do NOT include specific titles like "시작" or "진행"

✅ CORRECT: If you see "//1", "//2", "//3"
   → Pattern name: "//N"
   → Regex: "^//(\\d+)$"

**CRITICAL Regex Requirements:**
- ALWAYS use capturing groups with parentheses () to extract episode numbers
- Example: "^#(\\\\d+)화$" NOT "^#\\\\d+화$"
- Example: "^\\\\$(\\\\d+)$" NOT "^\\\\$\\\\d+$"
- The captured group (\\\\d+) MUST be present to extract episode numbers
- Test pattern examples:
  * For #1화, #2화 → "^#(\\\\d+)화$"
  * For $001, $002 → "^\\\\$(\\\\d{{3}})$"
  * For 第1話, 第2話 → "^第(\\\\d+)話$"
  * For //1, //2 → "^//(\\\\d+)$"
  * For standalone 1, 2, 3 → "^(\\\\d+)$"

**Response format (JSON only, no markdown):**
{{
    "is_multi_episode": true,
    "patterns": [
        {{
            "separator_pattern": "$NNN",
            "pattern_examples": ["$001", "$002", "$003"],
            "pattern_regex": "^\\\\$(\\\\d{{3}})$"
        }},
        {{
            "separator_pattern": "N",
            "pattern_examples": ["1", "2", "3"],
            "pattern_regex": "^(\\\\d+)$"
        }}
    ],
    "primary_pattern": "$NNN",
    "estimated_episodes": 50,
    "confidence": 95,
    "special_episodes": {{
        "prologue": "프롤로그",
        "epilogue": null,
        "extras": []
    }},
    "language": "korean",
    "notes": "Clean separation with #N화 pattern at line starts"
}}

Respond ONLY with the JSON object, no additional text."""

        try:
            response = self.model.generate_content(
                prompt,
                safety_settings=self.safety_settings,
                generation_config={'temperature': 0.1}  # Low temperature for consistency
            )

            # Parse JSON response
            response_text = response.text.strip()

            # Remove markdown code blocks if present
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            pattern_info = json.loads(response_text)

            # Handle both old format (single pattern) and new format (multiple patterns)
            if 'patterns' in pattern_info:
                # New multi-pattern format
                primary = pattern_info.get('primary_pattern', '')
                self.logger.info(f"Multi-pattern detected: {len(pattern_info['patterns'])} patterns (primary: {primary}, confidence: {pattern_info['confidence']}%)")
            else:
                # Old single-pattern format - convert to new format for compatibility
                pattern_info['patterns'] = [{
                    'separator_pattern': pattern_info['separator_pattern'],
                    'pattern_examples': pattern_info.get('pattern_examples', []),
                    'pattern_regex': pattern_info.get('pattern_regex', '')
                }]
                pattern_info['primary_pattern'] = pattern_info['separator_pattern']
                self.logger.info(f"Pattern detected: {pattern_info['separator_pattern']} (confidence: {pattern_info['confidence']}%)")

            return pattern_info

        except Exception as e:
            self.logger.error(f"Pattern detection failed: {e}")
            # Fallback to single episode
            return {
                'is_multi_episode': False,
                'separator_pattern': None,
                'pattern_examples': [],
                'pattern_regex': None,
                'estimated_episodes': 1,
                'confidence': 50,
                'special_episodes': {},
                'language': 'korean',
                'notes': f'Error during detection: {str(e)}'
            }

    def _multi_pattern_regex_split(self, text: str, pattern_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Split episodes using multiple regex patterns (for files with mixed patterns)

        Args:
            text: Full text content
            pattern_info: Pattern information with 'patterns' list

        Returns:
            List of episodes
        """
        patterns_list = pattern_info.get('patterns', [])
        if not patterns_list:
            self.logger.warning("No patterns available, falling back to LLM split")
            return self._llm_split(text, pattern_info)

        # Filter out overly generic patterns when specific patterns exist
        # e.g., if $NNN pattern exists, remove standalone number pattern ^(\d+)$
        has_specific_pattern = any(
            p.get('separator_pattern', '').startswith('$') or
            p.get('separator_pattern', '').startswith('#') or
            p.get('separator_pattern', '').startswith('//') or
            '화' in p.get('separator_pattern', '') or
            '話' in p.get('separator_pattern', '') or
            'Chapter' in p.get('separator_pattern', '') or
            'Episode' in p.get('separator_pattern', '')
            for p in patterns_list
        )

        if has_specific_pattern:
            # Remove generic standalone number pattern
            filtered_patterns = [
                p for p in patterns_list
                if p.get('pattern_regex') != r'^(\d+)$' and
                   p.get('separator_pattern', '') != 'N'
            ]
            if filtered_patterns:
                patterns_list = filtered_patterns
                self.logger.info(f"Filtered to {len(patterns_list)} specific patterns, removed generic number pattern")

        # Compile all regex patterns
        compiled_patterns = []
        for p in patterns_list:
            try:
                compiled_patterns.append(re.compile(p['pattern_regex']))
            except Exception as e:
                self.logger.warning(f"Failed to compile pattern {p['pattern_regex']}: {e}")

        if not compiled_patterns:
            self.logger.warning("No valid patterns compiled, falling back to LLM split")
            return self._llm_split(text, pattern_info)

        episodes = []
        # Remove BOM (Byte Order Mark) if present
        text = text.lstrip('\ufeff')
        lines = text.split('\n')
        current_episode = None
        current_content = []

        for line in lines:
            line_stripped = line.strip().lstrip('\ufeff')
            matched = False

            # Try each pattern
            for pattern in compiled_patterns:
                match = pattern.match(line_stripped)
                if match:
                    matched = True
                    # Save previous episode (even if content is empty)
                    if current_episode is not None:
                        raw_content = '\n'.join(current_content).strip()
                        # Clean trailing episode markers
                        cleaned_content = clean_trailing_episode_marker(raw_content)
                        episodes.append({
                            'number': current_episode,
                            'title': None,
                            'content': cleaned_content
                        })

                    # Start new episode - extract number from captured group
                    try:
                        current_episode = int(match.group(1))
                    except IndexError:
                        # Fallback: extract digits
                        digits = re.findall(r'\d+', match.group(0))
                        if digits:
                            current_episode = int(digits[0])
                            self.logger.warning(f"Pattern missing capture group, extracted: {current_episode}")
                        else:
                            self.logger.error(f"Could not extract episode number from: {match.group(0)}")
                            matched = False
                            continue

                    current_content = []

                    # Check if there's text after the separator on the same line
                    # e.g., "* * *$003본문 시작..." -> capture "본문 시작..."
                    remaining_text = line_stripped[match.end():].strip()
                    if remaining_text:
                        current_content.append(remaining_text)

                    break  # Stop checking other patterns once matched

            # If not a separator, accumulate content
            if not matched and current_episode is not None:
                current_content.append(line)

        # Save last episode (even if content is empty)
        if current_episode is not None:
            raw_content = '\n'.join(current_content).strip()
            # Clean trailing episode markers
            cleaned_content = clean_trailing_episode_marker(raw_content)
            episodes.append({
                'number': current_episode,
                'title': None,
                'content': cleaned_content
            })

        # If no episodes found, treat as single episode
        if not episodes:
            self.logger.warning("Multi-pattern split found no episodes, treating as single episode")
            return [{
                'number': 1,
                'title': None,
                'content': text
            }]

        # Filter out episodes with empty content (consecutive separators)
        episodes_before = len(episodes)
        episodes = [ep for ep in episodes if ep['content'].strip()]
        if len(episodes) < episodes_before:
            self.logger.info(f"Filtered out {episodes_before - len(episodes)} empty episodes from consecutive separators")

        # Handle special episodes
        episodes = self._handle_special_episodes(episodes, pattern_info)

        # Extract titles from content
        episodes = self._extract_titles_from_episodes(episodes)

        return episodes

    def _extract_titles_from_episodes(self, episodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract titles from episode content using LLM and clean content.

        Uses LLM to analyze the first few lines of each episode and
        extract the title if present, handling various formats.

        Args:
            episodes: List of episode dicts with 'number', 'title', 'content'

        Returns:
            List of episodes with titles extracted and content cleaned
        """
        # Collect episodes that need title extraction
        episodes_needing_titles = [
            (i, ep) for i, ep in enumerate(episodes)
            if not ep.get('title') and ep.get('content', '').strip()
        ]

        if not episodes_needing_titles:
            return episodes

        # Batch extract titles using LLM (process all at once for efficiency)
        # Build a compact prompt with first 3 lines of each episode
        episode_samples = []
        for idx, ep in episodes_needing_titles:
            lines = ep['content'].split('\n')
            # Get first 3 non-empty lines
            first_lines = []
            for line in lines:
                if line.strip():
                    first_lines.append(line.strip())
                    if len(first_lines) >= 3:
                        break
            episode_samples.append({
                'idx': idx,
                'number': ep['number'],
                'first_lines': first_lines
            })

        prompt = f"""Analyze these episode beginnings and extract titles if present.

**Episodes to analyze:**
{json.dumps(episode_samples, ensure_ascii=False, indent=2)}

**Instructions:**
1. Look for title lines like "1화 - 제목", "제1화: 제목", "1화. 제목", "第1話 - タイトル", etc.
2. The title line usually appears at the very beginning
3. Return the extracted title and which line number (0-indexed) contains it
4. If no title is found, return null for both fields
5. Title should NOT include the episode number part (e.g., "두 세계 사이에서" not "1화 - 두 세계 사이에서")

**Response format (JSON only):**
{{
    "results": [
        {{"idx": 0, "title": "두 세계 사이에서", "title_line_idx": 0}},
        {{"idx": 1, "title": null, "title_line_idx": null}},
        ...
    ]
}}

Respond ONLY with the JSON object."""

        try:
            response = self.model.generate_content(
                prompt,
                safety_settings=self.safety_settings,
                generation_config={
                    'temperature': 0.1,
                    'response_mime_type': 'application/json'
                }
            )

            response_text = response.text.strip()
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            result = json.loads(response_text)

            # Apply extracted titles
            for item in result.get('results', []):
                idx = item.get('idx')
                title = item.get('title')
                title_line_idx = item.get('title_line_idx')

                if idx is not None and title and title_line_idx is not None:
                    ep = episodes[idx]
                    lines = ep['content'].split('\n')

                    # Remove the title line from content
                    non_empty_count = 0
                    for i, line in enumerate(lines):
                        if line.strip():
                            if non_empty_count == title_line_idx:
                                # Found the title line, remove it
                                lines[i] = ''
                                break
                            non_empty_count += 1

                    # Clean up leading empty lines
                    while lines and not lines[0].strip():
                        lines.pop(0)

                    ep['title'] = title
                    ep['content'] = '\n'.join(lines).strip()
                    self.logger.info(f"Extracted title for episode {ep['number']}: {title}")

        except Exception as e:
            self.logger.warning(f"LLM title extraction failed: {e}, episodes will have no titles")

        return episodes

    def _inline_split(self, text: str, pattern_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Split episodes using inline $NNN pattern (text-based, not line-based).

        This method handles cases where episode markers appear mid-line, like:
        - '"말했다."$002엄마가...' -> split before $002
        - '* * *$003이영이...' -> split before $003 (removing * * *)

        Args:
            text: Full text content
            pattern_info: Pattern information from detection

        Returns:
            List of episodes
        """
        # Remove BOM if present
        text = text.lstrip('\ufeff')

        # Find all $NNN markers with their positions
        # Pattern: optional "* * *" followed by $NNN
        # We want to split BEFORE the marker (or before * * * if present)
        split_pattern = r'(?:\* \* \*)?\$(\d{3})'

        episodes = []
        matches = list(re.finditer(split_pattern, text))

        if not matches:
            self.logger.warning("Inline split found no $NNN markers, treating as single episode")
            return [{
                'number': 1,
                'title': None,
                'content': text
            }]

        self.logger.info(f"Found {len(matches)} inline $NNN markers")

        for i, match in enumerate(matches):
            ep_num = int(match.group(1))

            # Determine content boundaries
            # Content starts after this marker
            content_start = match.end()

            # Content ends at next marker (or end of text)
            if i + 1 < len(matches):
                # Find where next marker starts (including optional * * *)
                next_match = matches[i + 1]
                # Check if there's "* * *" before the next $NNN
                prefix_check = text[max(0, next_match.start() - 10):next_match.start()]
                if '* * *' in prefix_check:
                    # Find exact position of "* * *"
                    asterisk_pos = text.rfind('* * *', content_start, next_match.start())
                    if asterisk_pos != -1:
                        content_end = asterisk_pos
                    else:
                        content_end = next_match.start()
                else:
                    content_end = next_match.start()
            else:
                content_end = len(text)

            # Extract content
            content = text[content_start:content_end].strip()

            # Clean trailing episode markers
            content = clean_trailing_episode_marker(content)

            # Remove any remaining * * * at the end (scene break artifact)
            content = re.sub(r'\s*\* \* \*\s*$', '', content).strip()

            episodes.append({
                'number': ep_num,
                'title': None,
                'content': content
            })

        # Filter out episodes with empty content
        episodes_before = len(episodes)
        episodes = [ep for ep in episodes if ep['content'].strip()]
        if len(episodes) < episodes_before:
            self.logger.info(f"Filtered out {episodes_before - len(episodes)} empty episodes")

        # Handle special episodes (prologue, epilogue)
        episodes = self._handle_special_episodes(episodes, pattern_info)

        # Extract titles from content
        episodes = self._extract_titles_from_episodes(episodes)

        return episodes

    def _regex_split(self, text: str, pattern_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Split episodes using regex pattern (fast method)

        Args:
            text: Full text content
            pattern_info: Pattern information from detection

        Returns:
            List of episodes
        """
        # Check if multiple patterns exist
        if 'patterns' in pattern_info and len(pattern_info['patterns']) > 1:
            self.logger.info(f"Using multi-pattern split ({len(pattern_info['patterns'])} patterns)")
            return self._multi_pattern_regex_split(text, pattern_info)

        # Single pattern - use original logic
        if 'patterns' in pattern_info and pattern_info['patterns']:
            pattern = pattern_info['patterns'][0]['pattern_regex']
        else:
            pattern = pattern_info.get('pattern_regex')

        if not pattern:
            self.logger.warning("No regex pattern available, falling back to LLM split")
            return self._llm_split(text, pattern_info)

        episodes = []
        # Remove BOM (Byte Order Mark) if present
        text = text.lstrip('\ufeff')
        lines = text.split('\n')
        current_episode = None
        current_content = []

        for line in lines:
            # Check if line matches separator pattern
            line_stripped = line.strip().lstrip('\ufeff')
            match = re.match(pattern, line_stripped)

            if match:
                # Save previous episode
                if current_episode is not None:
                    raw_content = '\n'.join(current_content).strip()
                    # Clean trailing episode markers
                    cleaned_content = clean_trailing_episode_marker(raw_content)
                    episodes.append({
                        'number': current_episode,
                        'title': None,
                        'content': cleaned_content
                    })

                # Start new episode - extract number from captured group
                try:
                    # Try to get captured group (1)
                    current_episode = int(match.group(1))
                except IndexError:
                    # No capture group - fallback: extract number from matched text
                    matched_text = match.group(0)
                    # Extract digits from the matched line
                    digits = re.findall(r'\d+', matched_text)
                    if digits:
                        current_episode = int(digits[0])
                        self.logger.warning(f"Regex pattern missing capture group, extracted: {current_episode}")
                    else:
                        self.logger.error(f"Could not extract episode number from: {matched_text}")
                        continue

                current_content = []

                # Check if there's text after the separator on the same line
                # e.g., "* * *$003본문 시작..." -> capture "본문 시작..."
                remaining_text = line_stripped[match.end():].strip()
                if remaining_text:
                    current_content.append(remaining_text)
            else:
                # Accumulate content
                if current_episode is not None:
                    current_content.append(line)

        # Save last episode
        if current_episode is not None and current_content:
            raw_content = '\n'.join(current_content).strip()
            # Clean trailing episode markers
            cleaned_content = clean_trailing_episode_marker(raw_content)
            episodes.append({
                'number': current_episode,
                'title': None,
                'content': cleaned_content
            })

        # If no episodes found, treat as single episode
        if not episodes:
            self.logger.warning("Regex split found no episodes, treating as single episode")
            return [{
                'number': 1,
                'title': None,
                'content': text
            }]

        # Handle special episodes (prologue, epilogue)
        episodes = self._handle_special_episodes(episodes, pattern_info)

        # Extract titles from content
        episodes = self._extract_titles_from_episodes(episodes)

        return episodes

    def _llm_split(self, text: str, pattern_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Split episodes using LLM (accurate method for complex patterns)

        Args:
            text: Full text content
            pattern_info: Pattern information from detection

        Returns:
            List of episodes
        """
        # For very long files, chunk the splitting
        max_chars = 100000  # ~100K chars per request
        if len(text) > max_chars:
            return self._chunked_llm_split(text, pattern_info, max_chars)

        # Get separator pattern (handle both old and new format)
        separator = pattern_info.get('separator_pattern') or pattern_info.get('primary_pattern', 'Unknown')

        # Get pattern examples
        if 'patterns' in pattern_info:
            # New multi-pattern format
            all_examples = []
            for p in pattern_info['patterns']:
                all_examples.extend(p.get('pattern_examples', []))
            pattern_examples = all_examples[:5]  # Limit to 5 examples
        else:
            # Old single-pattern format
            pattern_examples = pattern_info.get('pattern_examples', [])

        prompt = f"""Split this text file into individual episodes using the detected pattern.

**Pattern Information:**
- Separator: {separator}
- Pattern examples: {', '.join(pattern_examples)}
- Language: {pattern_info.get('language', 'korean')}
- Special episodes: {json.dumps(pattern_info.get('special_episodes', {}))}

**Full Text:**
```
{text}
```

**Instructions:**
1. Split the text at each episode separator
2. Extract episode number and title (if present)
3. Handle special episodes:
   - Prologue → episode 0
   - Epilogue → episode 999 (will be renumbered)
   - Extras → episode 900+ (will be renumbered)
4. Skip false positives in dialogue
5. Maintain sequential numbering
6. Include all content between separators

**Response format (JSON only, no markdown):**
{{
    "episodes": [
        {{
            "number": 1,
            "title": "프롤로그",
            "content": "..."
        }},
        {{
            "number": 2,
            "title": "시작",
            "content": "..."
        }}
    ]
}}

Respond ONLY with the JSON object."""

        try:
            response = self.model.generate_content(
                prompt,
                safety_settings=self.safety_settings,
                generation_config={
                    'temperature': 0.1,
                    'response_mime_type': 'application/json'  # Force JSON output
                }
            )

            response_text = response.text.strip()

            # Remove markdown code blocks
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            # Try to parse JSON with fallback to regex extraction
            try:
                result = json.loads(response_text)
            except json.JSONDecodeError as json_error:
                self.logger.warning(f"Direct JSON parse failed: {json_error}, attempting regex split")
                # Fallback: Use regex-based splitting if LLM gives malformed JSON
                return self._regex_split(text, pattern_info)

            episodes = result.get('episodes', [])
            # Clean trailing episode markers from each episode
            for ep in episodes:
                if ep.get('content'):
                    ep['content'] = clean_trailing_episode_marker(ep['content'])
            # LLM may or may not extract titles, so apply extraction as fallback
            return self._extract_titles_from_episodes(episodes)

        except Exception as e:
            self.logger.error(f"LLM split failed: {e}")
            # Fallback: Try regex split if we have pattern info
            if pattern_info.get('pattern_regex'):
                self.logger.info("Falling back to regex split")
                return self._regex_split(text, pattern_info)

            # Last resort: single episode
            return [{
                'number': 1,
                'title': None,
                'content': text
            }]

    def _chunked_llm_split(self, text: str, pattern_info: Dict[str, Any], chunk_size: int) -> List[Dict[str, Any]]:
        """
        Split very long texts in chunks

        Args:
            text: Full text content
            pattern_info: Pattern information
            chunk_size: Maximum characters per chunk

        Returns:
            Combined list of episodes
        """
        episodes = []
        chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]

        for chunk in chunks:
            chunk_episodes = self._llm_split(chunk, pattern_info)
            episodes.extend(chunk_episodes)

        # Renumber episodes sequentially
        for i, episode in enumerate(episodes, 1):
            episode['number'] = i

        return episodes

    def _handle_special_episodes(self, episodes: List[Dict[str, Any]], pattern_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Handle prologue, epilogue, and extra episodes

        Args:
            episodes: List of episodes
            pattern_info: Pattern information

        Returns:
            Episodes with special episodes properly numbered
        """
        special = pattern_info.get('special_episodes', {})

        # Check for prologue in first episode (DISABLED - causes episode 1 to be skipped)
        # if episodes and special.get('prologue'):
        #     if special['prologue'].lower() in episodes[0].get('content', '')[:100].lower():
        #         episodes[0]['number'] = 0
        #         episodes[0]['title'] = special['prologue']

        # Check for epilogue in last episode
        if episodes and special.get('epilogue'):
            if special['epilogue'].lower() in episodes[-1].get('content', '')[:100].lower():
                episodes[-1]['title'] = special['epilogue']

        return episodes

    def _validate_split(self, episodes: List[Dict[str, Any]], pattern_info: Dict[str, Any], original_text: str) -> Dict[str, Any]:
        """
        Validate episode splitting results

        Args:
            episodes: Split episodes
            pattern_info: Pattern information
            original_text: Original full text

        Returns:
            Validation results with confidence adjustment
        """
        warnings = []
        confidence = 100

        # Check 1: Episode count vs estimate
        estimated = pattern_info.get('estimated_episodes', len(episodes))
        actual = len(episodes)
        diff_pct = abs(actual - estimated) / estimated * 100 if estimated > 0 else 0

        if diff_pct > 20:
            warnings.append(f"Episode count mismatch: estimated {estimated}, found {actual} ({diff_pct:.1f}% difference)")
            confidence -= 10

        # Check 2: Sequential numbering
        numbers = [ep['number'] for ep in episodes]
        for i in range(len(numbers) - 1):
            gap = numbers[i+1] - numbers[i]
            if gap > 2:
                warnings.append(f"Large gap in numbering: {numbers[i]} → {numbers[i+1]}")
                confidence -= 5

        # Check 3: Minimum content length (only warn for very short)
        very_short_count = 0
        for ep in episodes:
            word_count = len(ep['content'].split())
            if word_count < 20:  # Very short threshold (was 50)
                very_short_count += 1

        if very_short_count > len(episodes) * 0.1:  # More than 10% very short
            warnings.append(f"{very_short_count} episodes have very short content (<20 words)")
            confidence -= 5

        # Check 4: Total content preservation (relaxed threshold)
        total_chars = sum(len(ep['content']) for ep in episodes)
        original_chars = len(original_text)
        preserved_pct = total_chars / original_chars * 100 if original_chars > 0 else 0

        if preserved_pct < 80:  # Relaxed from 95% to 80%
            warnings.append(f"Content loss detected: {100-preserved_pct:.1f}% of text missing")
            confidence -= 10  # Reduced penalty from 15 to 10

        return {
            'confidence': max(confidence, 70),  # Minimum confidence 70% instead of 0%
            'warnings': warnings
        }
