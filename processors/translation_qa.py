"""
Translation QA Validator
Validates translation quality by checking:
1. Language mixing (source language appearing in target)
2. Glossary consistency (correct terms used)
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# Unicode ranges for language detection
UNICODE_RANGES = {
    'korean': (0xAC00, 0xD7AF),      # Korean syllables
    'korean_jamo': (0x1100, 0x11FF), # Korean Jamo
    'chinese': (0x4E00, 0x9FFF),     # CJK Unified Ideographs
    'hiragana': (0x3040, 0x309F),    # Japanese Hiragana
    'katakana': (0x30A0, 0x30FF),    # Japanese Katakana
}


# Korean onomatopoeia/mimetic words that might intentionally remain untranslated
# These are style choices - marked as warnings instead of errors
KOREAN_ONOMATOPOEIA = {
    # Sound effects
    '킁킁', '쿵', '쾅', '짝짝', '딩동', '띵동', '뚝뚝', '졸졸', '철썩', '쨍그랑',
    '빵', '펑', '탁', '딱', '쩝쩝', '찍찍', '끽끽', '끼익', '삐걱', '덜컹',
    '쿵쿵', '쾅쾅', '두근두근', '콩닥콩닥',
    # Emotional expressions
    '훗', '흥', '헉', '엉엉', '흑흑', '앙앙', '깔깔', '히히', '호호', '끄덕끄덕',
    '푸하하', '껄껄', '키득키득', '끙끙', '쩝', '푸', '헐', '엥', '에잇',
    # Movement/state
    '살금살금', '후다닥', '뚜벅뚜벅', '터벅터벅', '휘청휘청', '비틀비틀',
    '아장아장', '뒤뚱뒤뚱', '사뿐사뿐',
}


# Similar characters that LLMs often confuse
# Format: correct_char -> [incorrect_alternatives]
SIMILAR_CHARACTERS = {
    # 현 (hyeon)
    '賢': ['炫', '玄', '鉉', '泫', '眩'],
    # 준 (jun)
    '俊': ['浚', '峻', '駿', '濬'],
    # 민 (min)
    '敏': ['民', '珉', '旻', '玟', '憫'],
    # 조 (jo) - surname
    '趙': ['曹', '兆', '朝'],
    # 휘 (hwi)
    '輝': ['煇', '暉', '徽', '揮'],
    # 인 (in)
    '仁': ['仁', '寅', '認'],
    # 수 (su)
    '秀': ['洙', '壽', '修', '守'],
    # 혁 (hyeok)
    '赫': ['赫', '爀', '嚇'],
    # 윤 (yun)
    '允': ['尹', '潤', '倫'],
    # 제 (je)
    '濟': ['済', '祭', '制'],
    # 아 (a)
    '雅': ['亞', '娥', '芽'],
}


@dataclass
class QAIssue:
    """Single QA issue found in translation"""
    type: str  # 'language_mixing', 'untranslated_term', 'glossary_mismatch'
    severity: str  # 'error', 'warning'
    text: str  # The problematic text
    message: str  # Human-readable description
    position: Optional[int] = None  # Character position in text
    expected: Optional[str] = None  # Expected text (for mismatches)
    context: Optional[str] = None  # Surrounding context


@dataclass
class QAResult:
    """Result of QA validation"""
    passed: bool
    issues: list = field(default_factory=list)
    episode_number: Optional[int] = None

    @property
    def has_critical_issues(self) -> bool:
        """Check if there are any error-level issues"""
        return any(i.severity == 'error' for i in self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == 'error')

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == 'warning')

    def to_report(self) -> str:
        """Generate human-readable report"""
        status = 'PASS' if self.passed else 'FAIL'
        lines = [f"QA Result: {status}"]

        if self.episode_number:
            lines[0] = f"Episode {self.episode_number} - QA Result: {status}"

        if self.issues:
            lines.append(f"  Errors: {self.error_count}, Warnings: {self.warning_count}")
            for issue in self.issues:
                lines.append(f"  [{issue.severity.upper()}] {issue.message}")
                if issue.context:
                    lines.append(f"    Context: ...{issue.context}...")

        return '\n'.join(lines)


class TranslationQAValidator:
    """Validates translation quality"""

    def __init__(
        self,
        source_lang: str = 'korean',
        target_lang: str = 'traditional_chinese',
        glossary: dict = None,
        skip_language_mixing: bool = None
    ):
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.glossary = glossary or {'terms': []}

        # Auto-detect: skip language mixing check if source == target
        # This handles cases like Korean→Korean, Japanese→Japanese, etc.
        if skip_language_mixing is None:
            # Normalize language names for comparison
            source_normalized = self._normalize_language(source_lang)
            target_normalized = self._normalize_language(target_lang)
            self.skip_language_mixing = (source_normalized == target_normalized)
        else:
            self.skip_language_mixing = skip_language_mixing

        # Build lookup tables from glossary
        self._build_lookup_tables()

    def _normalize_language(self, lang: str) -> str:
        """Normalize language name for comparison"""
        lang_map = {
            'korean': 'korean',
            'japanese': 'japanese',
            'taiwanese': 'chinese',
            'traditional_chinese': 'chinese',
            'chinese': 'chinese',
            'mandarin': 'chinese'
        }
        return lang_map.get(lang.lower(), lang.lower())

    def _build_lookup_tables(self):
        """Build efficient lookup tables from glossary"""
        self.term_map = {}  # original -> translation
        self.char_terms = []  # Character terms for mismatch checking
        self.known_variants = {}  # known_wrong_variant -> correct_translation

        for term in self.glossary.get('terms', []):
            original = term.get('original', '')
            translation = term.get('translation', '')
            category = term.get('category', '')
            variants = term.get('known_wrong_variants', [])

            if original and translation:
                self.term_map[original] = translation

                # Register known wrong variants for detection
                for variant in variants:
                    if variant and variant != translation:
                        self.known_variants[variant] = translation

                if category == 'character':
                    self.char_terms.append({
                        'original': original,
                        'translation': translation,
                        'context': term.get('context', ''),
                        'known_wrong_variants': variants
                    })

    def validate(self, text: str, episode_number: int = None) -> QAResult:
        """Run all validation checks on translated text"""
        issues = []

        # Skip all translation checks if source == target (no translation occurred)
        if self.skip_language_mixing:
            # Source and target are the same language, no translation QA needed
            return QAResult(
                passed=True,
                issues=[],
                episode_number=episode_number
            )

        # Check for source language mixing
        issues.extend(self.check_language_mixing(text))

        # Check glossary consistency
        issues.extend(self.check_glossary_consistency(text))

        passed = len([i for i in issues if i.severity == 'error']) == 0

        return QAResult(
            passed=passed,
            issues=issues,
            episode_number=episode_number
        )

    def check_language_mixing(self, text: str) -> list:
        """
        Detect source language (Korean) appearing in target text.
        Returns list of QAIssue.

        Onomatopoeia and mimetic words are marked as warnings (style choices),
        while other Korean text is marked as errors (translation failures).
        """
        issues = []

        if self.source_lang != 'korean':
            return issues

        # Korean syllable pattern
        korean_pattern = re.compile(r'[\uAC00-\uD7AF]+')

        # Find all Korean text in the translation
        for match in korean_pattern.finditer(text):
            korean_text = match.group()
            position = match.start()

            # Get surrounding context (30 chars before and after)
            start = max(0, position - 30)
            end = min(len(text), position + len(korean_text) + 30)
            context = text[start:end]

            # Check if this is onomatopoeia (style choice vs error)
            if korean_text in KOREAN_ONOMATOPOEIA:
                severity = 'warning'
                message = f'의성어/의태어 유지됨 (스타일 선택): "{korean_text}"'
            else:
                severity = 'error'
                message = f'소스 언어(한국어) 발견: "{korean_text}"'

            issues.append(QAIssue(
                type='language_mixing',
                severity=severity,
                text=korean_text,
                position=position,
                context=context,
                message=message
            ))

        return issues

    def check_glossary_consistency(self, text: str) -> list:
        """
        Check if glossary terms are used correctly.
        - Untranslated terms (original Korean in target text)
        - Wrong character variants used (similar Han characters)
        - Known wrong variants (explicitly defined in glossary)
        """
        issues = []

        # Check for untranslated terms
        for original, expected in self.term_map.items():
            if original in text:
                issues.append(QAIssue(
                    type='untranslated_term',
                    severity='error',
                    text=original,
                    expected=expected,
                    message=f'번역되지 않은 용어: "{original}" → "{expected}"'
                ))

        # Check for known wrong variants (e.g., アイドゥン instead of アイデン)
        for wrong_variant, correct_translation in self.known_variants.items():
            if wrong_variant in text:
                # Find all occurrences
                pos = 0
                while True:
                    pos = text.find(wrong_variant, pos)
                    if pos == -1:
                        break

                    # Get context
                    start = max(0, pos - 20)
                    end = min(len(text), pos + len(wrong_variant) + 20)
                    context = text[start:end]

                    issues.append(QAIssue(
                        type='glossary_mismatch',
                        severity='error',
                        text=wrong_variant,
                        expected=correct_translation,
                        position=pos,
                        context=context,
                        message=f'잘못된 번역 변형: "{wrong_variant}" → "{correct_translation}" 사용 필요'
                    ))
                    pos += len(wrong_variant)  # Move past this occurrence

        # Check for similar character substitutions in character names
        for term in self.char_terms:
            expected = term['translation']
            alternatives = self._get_similar_alternatives(expected)

            for alt in alternatives:
                if alt in text and alt != expected:
                    # Find position and context
                    pos = text.find(alt)
                    start = max(0, pos - 20)
                    end = min(len(text), pos + len(alt) + 20)
                    context = text[start:end]

                    issues.append(QAIssue(
                        type='glossary_mismatch',
                        severity='error',
                        text=alt,
                        expected=expected,
                        context=context,
                        message=f'용어 불일치: "{alt}" → "{expected}" 사용 필요'
                    ))

        return issues

    def _get_similar_alternatives(self, text: str) -> list:
        """
        Generate all possible wrong variants of a text by substituting
        similar-looking characters.
        """
        alternatives = set()

        for i, char in enumerate(text):
            if char in SIMILAR_CHARACTERS:
                for alt_char in SIMILAR_CHARACTERS[char]:
                    if alt_char != char:
                        # Create alternative with this character substituted
                        alt_text = text[:i] + alt_char + text[i+1:]
                        alternatives.add(alt_text)

        return list(alternatives)

    def auto_fix(self, text: str, issues: list, llm_processor=None) -> tuple:
        """
        Attempt to automatically fix translation issues.

        Handles:
        - glossary_mismatch: Simple string replacement
        - language_mixing: LLM-based re-translation (requires llm_processor)
        - untranslated_term: LLM-based re-translation (requires llm_processor)

        Returns (fixed_text, fixed_count, unfixed_issues)
        """
        fixed_text = text
        fixed_count = 0
        unfixed_issues = []

        # Collect language_mixing issues for batch processing
        language_mixing_issues = []

        for issue in issues:
            if issue.type == 'glossary_mismatch' and issue.expected:
                # Simple string replacement
                if issue.text in fixed_text:
                    fixed_text = fixed_text.replace(issue.text, issue.expected)
                    fixed_count += 1
                    logger.info(f"Auto-fixed glossary: {issue.text} → {issue.expected}")
            elif issue.type == 'language_mixing' and issue.severity == 'error':
                # Collect for LLM-based fix
                language_mixing_issues.append(issue)
            elif issue.type == 'untranslated_term' and issue.expected:
                # Simple replacement with glossary term
                if issue.text in fixed_text:
                    fixed_text = fixed_text.replace(issue.text, issue.expected)
                    fixed_count += 1
                    logger.info(f"Auto-fixed untranslated: {issue.text} → {issue.expected}")
            else:
                unfixed_issues.append(issue)

        # Process language_mixing issues with LLM
        if language_mixing_issues and llm_processor:
            fixed_text, mixing_fixed_count, mixing_unfixed = self._fix_language_mixing(
                fixed_text, language_mixing_issues, llm_processor
            )
            fixed_count += mixing_fixed_count
            unfixed_issues.extend(mixing_unfixed)
        elif language_mixing_issues:
            # No LLM processor provided, cannot fix
            unfixed_issues.extend(language_mixing_issues)

        return fixed_text, fixed_count, unfixed_issues

    def _fix_language_mixing(self, text: str, issues: list, llm_processor) -> tuple:
        """
        Fix language mixing issues by re-translating Korean segments.

        Args:
            text: Text containing Korean segments
            issues: List of language_mixing QAIssue
            llm_processor: LLMProcessor instance for translation

        Returns:
            (fixed_text, fixed_count, unfixed_issues)
        """
        fixed_text = text
        fixed_count = 0
        unfixed_issues = []

        # Map target language
        target_lang_map = {
            'japanese': 'japanese',
            'traditional_chinese': 'taiwanese',
            'taiwanese': 'taiwanese'
        }
        target = target_lang_map.get(self.target_lang, self.target_lang)

        # Process each Korean segment
        for issue in issues:
            korean_text = issue.text
            context = issue.context or ''

            # Skip if already processed (might be duplicate from overlapping matches)
            if korean_text not in fixed_text:
                continue

            try:
                # Create targeted translation prompt
                result = llm_processor.execute({
                    'text': korean_text,
                    'operation': 'translate_segment',
                    'params': {
                        'source_lang': 'korean',
                        'target_lang': target,
                        'context': context,
                        'glossary': self.glossary
                    }
                })

                # LLMProcessor returns {'output': str, 'metadata': dict}
                if result and result.get('output'):
                    translated = result['output'].strip()

                    # Validate: ensure translation doesn't contain Korean
                    korean_pattern = re.compile(r'[\uAC00-\uD7AF]+')
                    if not korean_pattern.search(translated):
                        fixed_text = fixed_text.replace(korean_text, translated, 1)
                        fixed_count += 1
                        logger.info(f"Auto-fixed language mixing: {korean_text} → {translated}")
                    else:
                        logger.warning(f"Translation still contains Korean: {korean_text} → {translated}")
                        unfixed_issues.append(issue)
                else:
                    logger.warning(f"LLM translation failed for: {korean_text}")
                    unfixed_issues.append(issue)

            except Exception as e:
                logger.error(f"Error fixing language mixing for '{korean_text}': {e}")
                unfixed_issues.append(issue)

        return fixed_text, fixed_count, unfixed_issues


def validate_episode(
    content: str,
    episode_number: int,
    glossary: dict,
    source_lang: str = 'korean',
    target_lang: str = 'traditional_chinese'
) -> QAResult:
    """
    Convenience function to validate a single episode.
    """
    validator = TranslationQAValidator(
        source_lang=source_lang,
        target_lang=target_lang,
        glossary=glossary
    )
    return validator.validate(content, episode_number)


def batch_validate(
    episodes: list,
    glossary: dict,
    source_lang: str = 'korean',
    target_lang: str = 'traditional_chinese'
) -> dict:
    """
    Validate multiple episodes and return summary.

    Args:
        episodes: List of dicts with 'episode_number' and 'content'
        glossary: Glossary dictionary

    Returns:
        Dict with 'results', 'passed_count', 'failed_count', 'total_issues'
    """
    validator = TranslationQAValidator(
        source_lang=source_lang,
        target_lang=target_lang,
        glossary=glossary
    )

    results = []
    passed_count = 0
    failed_count = 0
    total_issues = 0

    for ep in episodes:
        result = validator.validate(
            ep['content'],
            ep.get('episode_number')
        )
        results.append(result)

        if result.passed:
            passed_count += 1
        else:
            failed_count += 1

        total_issues += len(result.issues)

    return {
        'results': results,
        'passed_count': passed_count,
        'failed_count': failed_count,
        'total_issues': total_issues,
        'pass_rate': passed_count / len(episodes) if episodes else 0
    }
