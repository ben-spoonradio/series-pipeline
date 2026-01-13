#!/usr/bin/env python3
"""
Series Pipeline Configuration

Centralized configuration for source and output paths.
Can be overridden via environment variables or .env file.
Supports automatic Google Drive path detection across different computers.
"""

import os
import platform
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load .env file from project root (parent directory)
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / '.env')


def auto_detect_google_drive(shared_drive_name: str = "Spoon Series") -> Optional[Path]:
    """
    Automatically detect Google Drive shared drive path.

    Works across different computers without manual configuration.
    Supports macOS, Windows, and Linux.

    Args:
        shared_drive_name: Name of the shared drive (fixed value)

    Returns:
        Detected path or None if not found
    """
    system = platform.system()

    if system == "Darwin":  # macOS
        base = Path.home() / "Library/CloudStorage"
        # Find GoogleDrive-{email} folder automatically
        if base.exists():
            for folder in base.glob("GoogleDrive-*"):
                drive_path = folder / "공유 드라이브" / shared_drive_name
                if drive_path.exists():
                    return drive_path

    elif system == "Windows":
        # Common Windows paths for Google Drive
        possible_paths = [
            Path.home() / "Google Drive" / "Shared drives" / shared_drive_name,
            Path.home() / "GoogleDrive" / "Shared drives" / shared_drive_name,
            Path("G:") / "Shared drives" / shared_drive_name,
            Path("G:") / "공유 드라이브" / shared_drive_name,
        ]
        for path in possible_paths:
            if path.exists():
                return path

    elif system == "Linux":
        # Linux (rare but supported)
        possible_paths = [
            Path.home() / "google-drive" / shared_drive_name,
            Path.home() / "Google Drive" / shared_drive_name,
        ]
        for path in possible_paths:
            if path.exists():
                return path

    return None


class Config:
    """Pipeline configuration with environment variable support and auto-detection."""

    # Base directories
    # Default: relative to series-pipeline folder
    _BASE_DIR = Path(__file__).parent

    # Auto-detect Google Drive shared drive
    _GOOGLE_DRIVE: Optional[Path] = auto_detect_google_drive()

    # Google Drive IP folder (base for SOURCE, OUTPUT, REVIEW when using Google Drive)
    _GOOGLE_DRIVE_IP: Optional[Path] = _GOOGLE_DRIVE / "IP" if _GOOGLE_DRIVE else None

    @classmethod
    def _get_source_dir(cls) -> Path:
        """Determine source directory with fallback chain."""
        # 1. Check environment variable first
        env_source = os.getenv('SERIES_SOURCE_DIR')
        if env_source:
            return Path(env_source)

        # 2. Use Google Drive IP/_SOURCE if available
        if cls._GOOGLE_DRIVE_IP:
            return cls._GOOGLE_DRIVE_IP / "_SOURCE"

        # 3. Default to local origin folder
        return cls._BASE_DIR / 'origin'

    @classmethod
    def _get_output_dir(cls) -> Path:
        """Determine output directory with fallback chain."""
        # 1. Check environment variable first
        env_output = os.getenv('SERIES_OUTPUT_DIR')
        if env_output:
            return Path(env_output)

        # 2. Use Google Drive IP/_PROCESSED if available
        if cls._GOOGLE_DRIVE_IP:
            return cls._GOOGLE_DRIVE_IP / "_PROCESSED"

        # 3. Default to local processed folder
        return cls._BASE_DIR / 'processed'

    @classmethod
    def _get_review_dir(cls) -> Optional[Path]:
        """Determine review directory with fallback chain."""
        # 1. Check environment variable first
        env_review = os.getenv('SERIES_REVIEW_DIR')
        if env_review:
            return Path(env_review)

        # 2. Use Google Drive IP/_REVIEW if available
        if cls._GOOGLE_DRIVE_IP:
            return cls._GOOGLE_DRIVE_IP / "_REVIEW"

        # 3. Return None (will fall back to OUTPUT_DIR/_review)
        return None

    # These will be dynamically determined
    SOURCE_DIR: Path = None  # Set after class definition
    OUTPUT_DIR: Path = None  # Set after class definition
    REVIEW_DIR: Optional[Path] = None  # Set after class definition

    # Data folder for reference files (CSV, JSON)
    # Prefer Google Drive root (where IP_LIST.csv is located), fallback to local data folder
    DATA_DIR: Path = Path(os.getenv(
        'SERIES_DATA_DIR',
        str(_GOOGLE_DRIVE) if _GOOGLE_DRIVE else str(_BASE_DIR / 'data')
    ))

    @classmethod
    def get_source_dir(cls) -> Path:
        """Get source directory path."""
        return cls._get_source_dir()

    @classmethod
    def get_output_dir(cls) -> Path:
        """Get output directory path."""
        return cls._get_output_dir()

    @classmethod
    def get_review_dir(cls) -> Path:
        """Get review directory path. Returns OUTPUT_DIR if not set."""
        review_dir = cls._get_review_dir()
        return review_dir if review_dir else cls.get_output_dir()

    @classmethod
    def get_data_dir(cls) -> Path:
        """Get data directory path."""
        return cls.DATA_DIR

    @classmethod
    def get_series_folder(cls, publisher: str, series_name: str) -> Path:
        """Get full path to a series folder in output directory."""
        return cls.get_output_dir() / publisher / series_name

    @classmethod
    def get_source_file(cls, language: str, publisher: str, series_name: str, filename: str) -> Path:
        """Get full path to a source file."""
        return cls.get_source_dir() / language / publisher / series_name / filename

    @classmethod
    def print_config(cls):
        """Print current configuration."""
        print("=" * 80)
        print("  Series Pipeline Configuration")
        print("=" * 80)
        print(f"  SOURCE_DIR:    {cls.get_source_dir()}")
        print(f"  OUTPUT_DIR:    {cls.get_output_dir()}")
        print(f"  REVIEW_DIR:    {cls.get_review_dir()}")
        print(f"  DATA_DIR:      {cls.DATA_DIR}")
        print("-" * 80)
        gdrive_status = cls._GOOGLE_DRIVE if cls._GOOGLE_DRIVE else "(not detected)"
        print(f"  GOOGLE_DRIVE:  {gdrive_status}")
        env_any = any([os.getenv('SERIES_SOURCE_DIR'), os.getenv('SERIES_OUTPUT_DIR'), os.getenv('SERIES_REVIEW_DIR')])
        print(f"  ENV_OVERRIDE:  {'Yes' if env_any else 'No (using auto-detect)'}")
        print("=" * 80)

    @classmethod
    def ensure_dirs(cls):
        """Create directories if they don't exist."""
        cls.get_source_dir().mkdir(parents=True, exist_ok=True)
        cls.get_output_dir().mkdir(parents=True, exist_ok=True)
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        review_dir = cls._get_review_dir()
        if review_dir:
            review_dir.mkdir(parents=True, exist_ok=True)


# Convenience functions
def get_source_dir() -> Path:
    return Config.get_source_dir()

def get_output_dir() -> Path:
    return Config.get_output_dir()

def get_review_dir() -> Path:
    return Config.get_review_dir()

def get_data_dir() -> Path:
    return Config.get_data_dir()


if __name__ == '__main__':
    Config.print_config()
