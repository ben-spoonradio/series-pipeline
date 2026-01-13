"""
Voice Generator - ElevenLabs API Integration
Handles voice creation and TTS generation
"""

import os
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from elevenlabs.client import ElevenLabs
    from elevenlabs import VoiceSettings
    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False
    logger.warning("elevenlabs package not available")


class VoiceGenerator:
    """ElevenLabs voice generation and TTS"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize voice generator

        Args:
            api_key: ElevenLabs API key (default from ELEVENLABS_API_KEY env)
        """
        if not ELEVENLABS_AVAILABLE:
            raise ImportError("elevenlabs package is required. Install with: pip install elevenlabs")

        self.api_key = api_key or os.getenv('ELEVENLABS_API_KEY')
        if not self.api_key:
            raise ValueError("ElevenLabs API key is required")

        self.client = ElevenLabs(api_key=self.api_key)
        self.default_model = "eleven_v3"  # Supports Korean, Japanese, English, Chinese
        logger.info("VoiceGenerator initialized")

    def create_custom_voice(
        self,
        name: str,
        description: str,
        labels: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Create custom voice using Voice Clone API (requires audio samples)

        Note: For text-to-voice design without audio samples,
              use design_voice() and save_designed_voice() instead.

        Args:
            name: Voice name
            description: Voice character description
            labels: Optional metadata labels

        Returns:
            Voice ID
        """
        try:
            # Use Voice Clone API (requires audio samples)
            voice = self.client.voices.add(
                name=name,
                description=description,
                labels=labels or {}
            )

            logger.info(f"Created custom voice: {name} (ID: {voice.voice_id})")
            return voice.voice_id

        except Exception as e:
            logger.error(f"Failed to create voice: {e}")
            raise

    def design_voice(
        self,
        voice_description: str,
        sample_text: str = "Hello, this is a sample of my voice for the audiobook narration. I will be reading stories with various emotions and tones, bringing characters to life through expressive storytelling.",
        model: str = "eleven_ttv_v3",
        guidance_scale: float = 3.0,
        seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Design a new voice using ElevenLabs Voice Design API (eleven_ttv_v3)

        This creates a preview voice from a text description without requiring
        audio samples. The generated voice can be saved using save_designed_voice().

        Args:
            voice_description: Voice description in English (20-1000 chars)
                               Format: [age/gender] + [tone] + [accent] + [emotion] + [pacing]
                               Example: "A warm female voice in her mid-30s with a gentle Korean accent.
                                        Speaks with a calm, storytelling tone and moderate pacing."
            sample_text: Sample text for preview audio generation
            model: Voice Design model (eleven_ttv_v3 or eleven_ttv_v2)
            guidance_scale: How closely to follow the description (1.0-5.0, default: 3.0)
            seed: Random seed for reproducibility (optional)

        Returns:
            Dict with:
                - voice_id: Temporary voice ID (use save_designed_voice to make permanent)
                - preview_audio: Preview audio bytes (MP3)
                - is_preview: True (indicates this is a preview, not saved)
        """
        if len(voice_description) < 20:
            raise ValueError("Voice description must be at least 20 characters")
        if len(voice_description) > 1000:
            raise ValueError("Voice description must be at most 1000 characters")

        try:
            import base64

            # Try SDK 2.x API first (text_to_voice.design)
            if hasattr(self.client, 'text_to_voice'):
                design_kwargs = {
                    "voice_description": voice_description,
                    "text": sample_text,
                }
                if guidance_scale != 3.0:
                    design_kwargs["guidance_scale"] = guidance_scale
                if seed is not None:
                    design_kwargs["seed"] = seed

                preview = self.client.text_to_voice.design(**design_kwargs)

                # SDK 2.x returns 'previews' attribute with VoicePreviewResponseModel objects
                previews = getattr(preview, 'previews', None) or getattr(preview, 'voice_previews', None)
                if previews and len(previews) > 0:
                    first_preview = previews[0]
                    # generated_voice_id is used for saving, audio_base_64 for preview audio
                    voice_id = first_preview.generated_voice_id
                    audio_data = getattr(first_preview, 'audio_base_64', None) or getattr(first_preview, 'preview_base64', None)

                    audio_bytes = None
                    if audio_data and isinstance(audio_data, str):
                        audio_bytes = base64.b64decode(audio_data)
                    elif audio_data:
                        audio_bytes = audio_data

                    logger.info(f"Voice preview generated (SDK 2.x): {voice_id}")
                    return {
                        'voice_id': voice_id,
                        'preview_audio': audio_bytes,
                        'is_preview': True,
                        'description': voice_description
                    }
                else:
                    raise ValueError("No voice preview generated")

            # Fallback for SDK 1.x (voice_generation)
            elif hasattr(self.client, 'voice_generation'):
                result = self.client.voice_generation.generate(
                    gender="female",
                    accent="korean",
                    age="young",
                    accent_strength=1.0,
                    text=sample_text
                )

                if hasattr(result, 'generated_voice_id'):
                    voice_id = result.generated_voice_id
                    audio_data = result.audio_base_64 if hasattr(result, 'audio_base_64') else None

                    audio_bytes = None
                    if audio_data and isinstance(audio_data, str):
                        audio_bytes = base64.b64decode(audio_data)
                    elif audio_data:
                        audio_bytes = audio_data

                    logger.info(f"Voice preview generated (SDK 1.x): {voice_id}")
                    return {
                        'voice_id': voice_id,
                        'preview_audio': audio_bytes,
                        'is_preview': True,
                        'description': voice_description
                    }
                else:
                    raise ValueError("No voice generated from Voice Generation API")
            else:
                raise ValueError("ElevenLabs SDK version not supported. Please upgrade: pip install elevenlabs --upgrade")

        except Exception as e:
            logger.error(f"Failed to design voice: {e}")
            raise

    def save_designed_voice(
        self,
        name: str,
        voice_description: str,
        generated_voice_id: str,
        labels: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Save a designed voice preview as a permanent voice in your account

        Args:
            name: Display name for the voice
            voice_description: Original voice description used in design_voice()
            generated_voice_id: Temporary voice ID from design_voice()
            labels: Optional metadata labels

        Returns:
            Permanent Voice ID (use this for TTS generation)
        """
        try:
            # Try SDK 2.x API first (text_to_voice.create)
            if hasattr(self.client, 'text_to_voice'):
                saved_voice = self.client.text_to_voice.create(
                    voice_name=name,
                    voice_description=voice_description,
                    generated_voice_id=generated_voice_id,
                    labels=labels or {}
                )
            # Fallback for SDK 1.x (voice_generation)
            elif hasattr(self.client, 'voice_generation'):
                saved_voice = self.client.voice_generation.create_a_previously_generated_voice(
                    voice_name=name,
                    voice_description=voice_description,
                    generated_voice_id=generated_voice_id,
                    labels=labels or {}
                )
            else:
                raise ValueError("ElevenLabs SDK version not supported")

            voice_id = saved_voice.voice_id
            logger.info(f"Voice saved permanently: {name} (ID: {voice_id})")
            return voice_id

        except Exception as e:
            logger.error(f"Failed to save designed voice: {e}")
            raise

    def design_and_save_voice(
        self,
        name: str,
        voice_description: str,
        sample_text: str = "Hello, this is a sample of my voice for the audiobook narration. I will be reading stories with various emotions and tones, bringing characters to life through expressive storytelling.",
        model: str = "eleven_ttv_v3",
        guidance_scale: float = 3.0,
        seed: Optional[int] = None,
        labels: Optional[Dict[str, str]] = None,
        save_preview: bool = False,
        preview_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Design and save a voice in one operation

        Combines design_voice() and save_designed_voice() for convenience.

        Args:
            name: Display name for the voice
            voice_description: Voice description in English (20-1000 chars)
            sample_text: Sample text for preview generation
            model: Voice Design model
            guidance_scale: Description adherence (1.0-5.0)
            seed: Random seed for reproducibility
            labels: Optional metadata labels
            save_preview: Whether to save preview audio to disk
            preview_path: Path to save preview audio (required if save_preview=True)

        Returns:
            Dict with:
                - voice_id: Permanent Voice ID
                - name: Voice name
                - description: Voice description
                - preview_audio: Preview audio bytes (if generated)
                - preview_path: Path to saved preview (if save_preview=True)
        """
        # Step 1: Generate preview
        preview = self.design_voice(
            voice_description=voice_description,
            sample_text=sample_text,
            model=model,
            guidance_scale=guidance_scale,
            seed=seed
        )

        # Step 2: Save preview audio if requested
        preview_saved_path = None
        if save_preview and preview_path:
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            preview_path.write_bytes(preview['preview_audio'])
            preview_saved_path = preview_path
            logger.info(f"Preview audio saved to: {preview_path}")

        # Step 3: Save voice permanently
        voice_id = self.save_designed_voice(
            name=name,
            voice_description=voice_description,
            generated_voice_id=preview['voice_id'],
            labels=labels
        )

        return {
            'voice_id': voice_id,
            'name': name,
            'description': voice_description,
            'preview_audio': preview['preview_audio'],
            'preview_path': preview_saved_path
        }

    def list_voices(self) -> List[Dict]:
        """
        List available voices

        Returns:
            List of voice info dictionaries
        """
        try:
            voices = self.client.voices.get_all()
            return [
                {
                    'voice_id': v.voice_id,
                    'name': v.name,
                    'category': v.category,
                    'description': v.description if hasattr(v, 'description') else None
                }
                for v in voices.voices
            ]
        except Exception as e:
            logger.error(f"Failed to list voices: {e}")
            return []

    def generate_speech(
        self,
        text: str,
        voice_id: str,
        model: Optional[str] = None,
        stability: float = 0.5,
        similarity_boost: float = 0.75,
        style: float = 0.0,
        use_speaker_boost: bool = True
    ) -> bytes:
        """
        Generate speech from text

        Args:
            text: Text to convert to speech
            voice_id: Voice ID to use
            model: TTS model (default: eleven_v3)
            stability: Voice stability (0.0-1.0)
            similarity_boost: Voice similarity (0.0-1.0)
            style: Style exaggeration (0.0-1.0)
            use_speaker_boost: Enable speaker boost

        Returns:
            Audio data in bytes (MP3 format)
        """
        if not text.strip():
            raise ValueError("Text cannot be empty")

        try:
            model = model or self.default_model

            # Create voice settings
            voice_settings = VoiceSettings(
                stability=stability,
                similarity_boost=similarity_boost,
                style=style,
                use_speaker_boost=use_speaker_boost
            )

            # Generate audio using SDK 2.x API (text_to_speech.convert)
            audio = self.client.text_to_speech.convert(
                text=text,
                voice_id=voice_id,
                model_id=model,
                voice_settings=voice_settings,
                output_format="mp3_44100_128"
            )

            # Convert generator to bytes
            audio_bytes = b''.join(audio)
            logger.info(f"Generated {len(audio_bytes)} bytes of audio")
            return audio_bytes

        except Exception as e:
            logger.error(f"Failed to generate speech: {e}")
            raise

    def generate_speech_file(
        self,
        text: str,
        voice_id: str,
        output_path: Path,
        model: Optional[str] = None,
        **voice_settings
    ) -> Path:
        """
        Generate speech and save to file

        Args:
            text: Text to convert
            voice_id: Voice ID
            output_path: Output file path
            model: TTS model
            **voice_settings: Voice settings (stability, similarity_boost, etc.)

        Returns:
            Path to saved audio file
        """
        audio_bytes = self.generate_speech(
            text=text,
            voice_id=voice_id,
            model=model,
            **voice_settings
        )

        # Save to file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(audio_bytes)

        logger.info(f"Saved audio to: {output_path}")
        return output_path

    def chunk_text(self, text: str, max_chars: int = 2500) -> List[str]:
        """
        Split text into chunks for TTS generation

        Args:
            text: Text to chunk
            max_chars: Maximum characters per chunk

        Returns:
            List of text chunks with pause tags at start and end
        """
        # Pause tag to add natural pauses at chunk boundaries
        # This helps TTS produce more natural speech rhythm
        pause_tag = '[멈칫하며]'

        if len(text) <= max_chars:
            return [f"{pause_tag} {text} {pause_tag}"]

        chunks = []
        current_chunk = ""

        # Split by sentences
        sentences = text.split('.')

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            sentence = sentence + '.'

            # If adding this sentence exceeds max_chars, save current chunk
            if len(current_chunk) + len(sentence) > max_chars:
                if current_chunk:
                    chunks.append(f"{pause_tag} {current_chunk.strip()} {pause_tag}")
                current_chunk = sentence
            else:
                current_chunk += ' ' + sentence if current_chunk else sentence

        # Add final chunk
        if current_chunk:
            chunks.append(f"{pause_tag} {current_chunk.strip()} {pause_tag}")

        logger.info(f"Split text into {len(chunks)} chunks (with pause tags)")
        return chunks

    def generate_speech_chunks(
        self,
        text: str,
        voice_id: str,
        output_dir: Path,
        max_chars: int = 2500,
        model: Optional[str] = None,
        **voice_settings
    ) -> List[Path]:
        """
        Generate speech for chunked text

        Args:
            text: Full text
            voice_id: Voice ID
            output_dir: Output directory for chunks
            max_chars: Max characters per chunk
            model: TTS model
            **voice_settings: Voice settings

        Returns:
            List of chunk file paths
        """
        chunks = self.chunk_text(text, max_chars)
        chunk_files = []

        output_dir.mkdir(parents=True, exist_ok=True)

        for i, chunk in enumerate(chunks):
            chunk_file = output_dir / f"chunk_{i:04d}.mp3"

            try:
                self.generate_speech_file(
                    text=chunk,
                    voice_id=voice_id,
                    output_path=chunk_file,
                    model=model,
                    **voice_settings
                )
                chunk_files.append(chunk_file)

            except Exception as e:
                logger.error(f"Failed to generate chunk {i}: {e}")
                # Continue with next chunk
                continue

        logger.info(f"Generated {len(chunk_files)}/{len(chunks)} audio chunks")
        return chunk_files

    def generate_music(
        self,
        prompt: str,
        duration_ms: int = 120000,
        output_path: Optional[Path] = None
    ) -> bytes:
        """
        Generate background music using ElevenLabs Music API

        Creates instrumental background music suitable for audiobook narration.
        The music is designed to be loopable for seamless background audio.

        Args:
            prompt: Text description of the desired music (max 400 chars)
                    Should include: genre, tempo (BPM), key, instruments, mood
                    Example: "Ambient lo-fi, 70 BPM, F major. Soft piano with warm synth pad.
                             Gentle romantic atmosphere. Seamless ambient loop."
            duration_ms: Duration in milliseconds (3000-300000, default: 120000 = 2 minutes)
            output_path: Optional path to save the audio file

        Returns:
            Audio data in bytes (MP3 format)

        Raises:
            ValueError: If duration is out of range or prompt is invalid
            Exception: If API call fails
        """
        if duration_ms < 3000 or duration_ms > 300000:
            raise ValueError("Duration must be between 3000ms (3s) and 300000ms (5min)")

        if not prompt.strip():
            raise ValueError("Music prompt cannot be empty")

        try:
            # Check if music API is available
            if not hasattr(self.client, 'music'):
                raise ValueError("ElevenLabs Music API not available. Please upgrade SDK: pip install elevenlabs --upgrade")

            logger.info(f"Generating music ({duration_ms}ms): {prompt[:100]}...")

            # Generate music using ElevenLabs Music API
            # Note: output_format is a query param, not body param in the API
            audio_chunks = self.client.music.compose(
                prompt=prompt,
                music_length_ms=duration_ms,
                force_instrumental=True,
                model_id="music_v1"
            )

            # Collect all chunks
            audio_bytes = b''.join(audio_chunks)
            logger.info(f"Generated {len(audio_bytes)} bytes of music")

            # Save to file if path provided
            if output_path:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(audio_bytes)
                logger.info(f"Saved music to: {output_path}")

            return audio_bytes

        except Exception as e:
            logger.error(f"Failed to generate music: {e}")
            raise
