"""
Glossary Manager for Translation Consistency
Manages terminology dictionaries for consistent translation across episodes.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class GlossaryManager:
    """
    Manages glossary (terminology dictionary) for translation consistency.

    Features:
    - Create and load glossary files
    - Add, update, and search terms
    - Ensure consistent translation of character names, locations, and technical terms
    """

    def __init__(self, glossary_path: Optional[Path] = None):
        """
        Initialize GlossaryManager.

        Args:
            glossary_path: Path to existing glossary file (optional)
        """
        self.glossary_path = glossary_path
        self.glossary_data = {
            'series_name': '',
            'source_language': '',
            'target_language': '',
            'created_date': '',
            'last_updated': '',
            'terms': []
        }

        if glossary_path and glossary_path.exists():
            self.load()

    def create(
        self,
        series_name: str,
        source_language: str,
        target_language: str,
        terms: List[Dict[str, str]] = None
    ) -> None:
        """
        Create new glossary.

        Args:
            series_name: Name of the series
            source_language: Source language (e.g., 'korean')
            target_language: Target language (e.g., 'japanese')
            terms: Initial list of terms (optional)
        """
        now = datetime.now().isoformat()

        self.glossary_data = {
            'series_name': series_name,
            'source_language': source_language,
            'target_language': target_language,
            'created_date': now,
            'last_updated': now,
            'terms': terms or []
        }

        logger.info(f"Created glossary for '{series_name}' ({source_language} -> {target_language})")

    def load(self) -> Dict[str, Any]:
        """
        Load glossary from file.

        Returns:
            Glossary data dictionary
        """
        if not self.glossary_path or not self.glossary_path.exists():
            raise FileNotFoundError(f"Glossary file not found: {self.glossary_path}")

        with open(self.glossary_path, 'r', encoding='utf-8') as f:
            self.glossary_data = json.load(f)

        logger.info(f"Loaded glossary: {self.glossary_path}")
        return self.glossary_data

    def save(self, path: Optional[Path] = None) -> None:
        """
        Save glossary to file.

        Args:
            path: Save path (uses self.glossary_path if not provided)
        """
        save_path = path or self.glossary_path

        if not save_path:
            raise ValueError("No save path specified")

        # Update last_updated timestamp
        self.glossary_data['last_updated'] = datetime.now().isoformat()

        # Create parent directory if needed
        save_path.parent.mkdir(parents=True, exist_ok=True)

        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(self.glossary_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Saved glossary: {save_path}")

        # Update internal path
        self.glossary_path = save_path

    def add_term(
        self,
        original: str,
        translation: str,
        category: str,
        first_appearance: str = '',
        context: str = ''
    ) -> None:
        """
        Add new term to glossary.

        Args:
            original: Original term in source language
            translation: Translated term in target language
            category: Term category ('character', 'location', 'skill', 'term')
            first_appearance: Episode where term first appeared (e.g., 'episode_001')
            context: Additional context or description
        """
        # Check if term already exists
        existing = self.find_term(original)
        if existing:
            logger.warning(f"Term '{original}' already exists in glossary")
            return

        term_entry = {
            'original': original,
            'translation': translation,
            'category': category,
            'first_appearance': first_appearance,
            'context': context
        }

        self.glossary_data['terms'].append(term_entry)
        logger.info(f"Added term: {original} -> {translation} ({category})")

    def update_term(self, original: str, **kwargs) -> bool:
        """
        Update existing term.

        Args:
            original: Original term to update
            **kwargs: Fields to update (translation, category, context, etc.)

        Returns:
            True if term was updated, False if not found
        """
        for term in self.glossary_data['terms']:
            if term['original'] == original:
                term.update(kwargs)
                logger.info(f"Updated term: {original}")
                return True

        logger.warning(f"Term not found: {original}")
        return False

    def find_term(self, original: str) -> Optional[Dict[str, str]]:
        """
        Find term by original text.

        Args:
            original: Original term to find

        Returns:
            Term entry if found, None otherwise
        """
        for term in self.glossary_data['terms']:
            if term['original'] == original:
                return term
        return None

    def get_translation(self, original: str) -> Optional[str]:
        """
        Get translation for a term.

        Args:
            original: Original term

        Returns:
            Translation if found, None otherwise
        """
        term = self.find_term(original)
        return term['translation'] if term else None

    def get_all_terms(self) -> List[Dict[str, str]]:
        """
        Get all terms in glossary.

        Returns:
            List of all term entries
        """
        return self.glossary_data['terms']

    def get_terms_by_category(self, category: str) -> List[Dict[str, str]]:
        """
        Get terms by category.

        Args:
            category: Category to filter by ('character', 'location', 'skill', 'term')

        Returns:
            List of terms in specified category
        """
        return [
            term for term in self.glossary_data['terms']
            if term.get('category') == category
        ]

    def get_term_count(self) -> int:
        """Get total number of terms in glossary."""
        return len(self.glossary_data['terms'])

    def get_all_originals(self) -> List[str]:
        """
        Get list of all original terms (for checking if new terms exist).

        Returns:
            List of original terms
        """
        return [term['original'] for term in self.glossary_data['terms']]

    def filter_new_terms(self, term_candidates: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """
        Filter out terms that already exist in glossary.

        Args:
            term_candidates: List of potential new terms from extraction

        Returns:
            List of terms that don't exist in glossary yet
        """
        existing_originals = set(self.get_all_originals())
        new_terms = [
            term for term in term_candidates
            if term.get('original') not in existing_originals
        ]

        if new_terms:
            logger.info(f"Found {len(new_terms)} new terms (out of {len(term_candidates)} candidates)")

        return new_terms

    def format_for_prompt(self) -> str:
        """
        Format glossary as text for LLM prompt.

        Returns:
            Formatted glossary string
        """
        if not self.glossary_data['terms']:
            return "No terms in glossary."

        lines = ["=== GLOSSARY ==="]

        # Group by category
        categories = {}
        for term in self.glossary_data['terms']:
            cat = term.get('category', 'term')
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(term)

        # Format each category
        for category, terms in sorted(categories.items()):
            lines.append(f"\n[{category.upper()}]")
            for term in terms:
                line = f"- {term['original']} → {term['translation']}"
                if term.get('context'):
                    line += f" ({term['context']})"
                lines.append(line)

        lines.append("\n=== END GLOSSARY ===")
        return '\n'.join(lines)

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"GlossaryManager("
            f"series='{self.glossary_data.get('series_name', 'Unknown')}', "
            f"terms={self.get_term_count()}, "
            f"path={self.glossary_path})"
        )
