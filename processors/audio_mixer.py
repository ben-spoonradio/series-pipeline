"""
Audio Mixer - Audio processing and mixing utilities
Based on legacy/TTS/automation/utils/audio_utils.py
"""

import os
import logging
import shutil
import subprocess
from typing import List, Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from pydub import AudioSegment
    from pydub.utils import which

    # FFmpeg path setup for pydub
    if not which("ffmpeg"):
        ffmpeg_paths = [
            "/opt/homebrew/bin/ffmpeg",  # macOS M1/M2
            "/usr/local/bin/ffmpeg",     # macOS Intel / Linux
            "/usr/bin/ffmpeg"            # Linux
        ]
        for path in ffmpeg_paths:
            if os.path.exists(path):
                AudioSegment.converter = path
                AudioSegment.ffmpeg = path
                AudioSegment.ffprobe = path.replace("ffmpeg", "ffprobe")
                break

    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    logger.warning("pydub not available, will use ffmpeg only")


class AudioMixer:
    """Audio file processing and mixing"""

    def __init__(self, temp_folder: Optional[Path] = None, output_folder: Optional[Path] = None):
        """
        Initialize audio mixer

        Args:
            temp_folder: Temporary files directory
            output_folder: Output files directory
        """
        self.temp_folder = temp_folder or Path("./temp_audio")
        self.output_folder = output_folder or Path("./output_audio")
        self.ffmpeg_path = self._find_ffmpeg()
        self.ensure_folders()

    def _find_ffmpeg(self) -> str:
        """Find ffmpeg executable"""
        result = shutil.which("ffmpeg")
        if result:
            logger.info(f"FFmpeg found at: {result}")
            return result

        common_paths = [
            "/opt/homebrew/bin/ffmpeg",
            "/usr/local/bin/ffmpeg",
            "/usr/bin/ffmpeg",
            "C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe",
            "C:\\ffmpeg\\bin\\ffmpeg.exe"
        ]

        for path in common_paths:
            if os.path.exists(path):
                logger.info(f"FFmpeg found at: {path}")
                return path

        logger.warning("FFmpeg not found in system PATH")
        return "ffmpeg"

    def check_ffmpeg(self) -> bool:
        """Check if ffmpeg is available"""
        try:
            if not os.path.exists(self.ffmpeg_path) and not shutil.which(self.ffmpeg_path):
                return False

            result = subprocess.run(
                [self.ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def ensure_folders(self):
        """Create necessary folders"""
        self.temp_folder.mkdir(parents=True, exist_ok=True)
        self.output_folder.mkdir(parents=True, exist_ok=True)

    def concatenate_audio_files(
        self,
        audio_files: List[Path],
        output_file: Path,
        gap_duration_ms: int = 1000
    ) -> bool:
        """
        Concatenate multiple audio files with gaps between them

        Args:
            audio_files: List of audio file paths
            output_file: Output file path
            gap_duration_ms: Gap duration in milliseconds (default: 1000ms)

        Returns:
            Success status
        """
        if not audio_files:
            logger.error("No audio files to concatenate")
            return False

        if len(audio_files) == 1:
            shutil.copy2(audio_files[0], output_file)
            return True

        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Try pydub first
            if PYDUB_AVAILABLE:
                try:
                    combined = AudioSegment.empty()
                    silence = AudioSegment.silent(duration=gap_duration_ms)

                    for i, audio_file in enumerate(audio_files):
                        if audio_file.exists():
                            audio = AudioSegment.from_mp3(str(audio_file))
                            combined += audio

                            # Add gap except after last file
                            if i < len(audio_files) - 1:
                                combined += silence

                    combined.export(str(output_file), format="mp3", bitrate="192k")
                    logger.info(f"Concatenated {len(audio_files)} files with pydub")
                    return True

                except Exception as e:
                    logger.warning(f"pydub failed: {e}, trying ffmpeg")

            # Fallback to ffmpeg
            if not self.check_ffmpeg():
                logger.error("FFmpeg not available and pydub failed")
                return False

            # Create concat list file
            list_file = self.temp_folder / f"concat_{os.getpid()}.txt"
            with open(list_file, 'w') as f:
                for audio_file in audio_files:
                    abs_path = os.path.abspath(audio_file)
                    f.write(f"file '{abs_path}'\n")

            cmd = [
                self.ffmpeg_path, "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(list_file),
                "-c:a", "libmp3lame",
                "-b:a", "192k",
                "-ar", "44100",
                str(output_file)
            ]

            logger.info(f"Concatenating {len(audio_files)} files with ffmpeg")
            subprocess.run(cmd, capture_output=True, text=True, check=True)

            logger.info(f"Successfully concatenated audio: {output_file}")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Error concatenating audio: {e}")
            return False
        finally:
            # Cleanup
            try:
                if 'list_file' in locals() and list_file.exists():
                    list_file.unlink()
            except:
                pass

    def mix_voice_with_music(
        self,
        voice_file: Path,
        music_file: Path,
        output_file: Path,
        music_volume: float = 0.3,
        fade_duration: float = 2.0
    ) -> bool:
        """
        Mix voice audio with background music

        Args:
            voice_file: Voice audio file path
            music_file: Background music file path
            output_file: Output file path
            music_volume: Music volume (0.0 - 1.0)
            fade_duration: Fade in/out duration in seconds

        Returns:
            Success status
        """
        if not voice_file.exists():
            logger.error(f"Voice file not found: {voice_file}")
            return False
        if not music_file.exists():
            logger.error(f"Music file not found: {music_file}")
            return False

        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Try pydub first
            if PYDUB_AVAILABLE:
                try:
                    voice = AudioSegment.from_mp3(str(voice_file))
                    music = AudioSegment.from_mp3(str(music_file))

                    # Adjust music volume (convert to dB)
                    music_db = 20 * (music_volume ** 0.5) - 20
                    music = music + music_db

                    # Loop music to match voice duration
                    voice_duration_ms = len(voice)
                    if len(music) < voice_duration_ms:
                        loops_needed = (voice_duration_ms // len(music)) + 1
                        music = music * loops_needed

                    # Trim music to match voice duration
                    music = music[:voice_duration_ms]

                    # Apply fade in/out
                    fade_ms = int(fade_duration * 1000)
                    music = music.fade_in(fade_ms).fade_out(fade_ms)

                    # Mix voice and music
                    final = voice.overlay(music)

                    # Export
                    final.export(str(output_file), format="mp3", bitrate="192k")
                    logger.info(f"Mixed audio created with pydub: {output_file}")
                    return True

                except Exception as e:
                    logger.warning(f"pydub failed: {e}, trying ffmpeg")

            # Fallback to ffmpeg
            if not self.check_ffmpeg():
                logger.error("FFmpeg not available and pydub failed")
                return False

            # Get voice duration
            voice_duration = self.get_audio_duration(voice_file)

            # FFmpeg command for mixing
            cmd = [
                self.ffmpeg_path, "-y",
                "-i", str(voice_file),
                "-i", str(music_file),
                "-filter_complex",
                f"[1:a]volume={music_volume},aloop=loop=-1:size=44100*30,atrim=0:{voice_duration},"
                f"afade=t=in:st=0:d={fade_duration},afade=t=out:st={max(0, voice_duration-fade_duration)}:d={fade_duration}[music];"
                f"[0:a][music]amix=inputs=2:duration=first:dropout_transition=0[out]",
                "-map", "[out]",
                "-codec:a", "libmp3lame",
                "-b:a", "192k",
                "-ar", "44100",
                str(output_file)
            ]

            subprocess.run(cmd, capture_output=True, text=True, check=True)
            logger.info(f"Mixed audio created with ffmpeg: {output_file}")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Error mixing audio: {e}")
            return False

    def get_audio_duration(self, audio_file: Path) -> float:
        """
        Get audio file duration in seconds

        Args:
            audio_file: Audio file path

        Returns:
            Duration in seconds
        """
        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_file}")

        # Try pydub first
        if PYDUB_AVAILABLE:
            try:
                audio = AudioSegment.from_file(str(audio_file), format="mp3")
                duration_seconds = len(audio) / 1000.0
                logger.info(f"Duration (pydub): {duration_seconds}s")
                return duration_seconds
            except Exception as e:
                logger.warning(f"pydub failed: {e}")

        # Try ffprobe
        if self.check_ffmpeg():
            ffprobe = self.ffmpeg_path.replace("ffmpeg", "ffprobe")

            if os.path.exists(ffprobe) or shutil.which("ffprobe"):
                ffprobe_cmd = ffprobe if os.path.exists(ffprobe) else "ffprobe"

                cmd = [
                    ffprobe_cmd,
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(audio_file)
                ]

                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                    duration = float(result.stdout.strip())
                    logger.info(f"Duration (ffprobe): {duration}s")
                    return duration
                except Exception as e:
                    logger.warning(f"ffprobe failed: {e}")

        # Default fallback
        logger.warning("Could not get audio duration, using default 30s")
        return 30.0

    def loop_music_to_duration(
        self,
        music_file: Path,
        target_duration: float,
        output_file: Path
    ) -> bool:
        """
        Loop background music to match target duration

        Args:
            music_file: Music file path
            target_duration: Target duration in seconds
            output_file: Output file path

        Returns:
            Success status
        """
        if not music_file.exists():
            logger.error(f"Music file not found: {music_file}")
            return False

        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)

            if PYDUB_AVAILABLE:
                music = AudioSegment.from_mp3(str(music_file))
                target_ms = int(target_duration * 1000)

                # Loop music
                if len(music) < target_ms:
                    loops_needed = (target_ms // len(music)) + 1
                    music = music * loops_needed

                # Trim to exact duration
                music = music[:target_ms]

                music.export(str(output_file), format="mp3", bitrate="192k")
                logger.info(f"Looped music to {target_duration}s")
                return True

            # Fallback to copy if short enough
            music_duration = self.get_audio_duration(music_file)
            if music_duration >= target_duration:
                shutil.copy2(music_file, output_file)
                return True

            logger.error("Cannot loop music without pydub")
            return False

        except Exception as e:
            logger.error(f"Error looping music: {e}")
            return False

    def master_audio(
        self,
        input_file: Path,
        output_file: Path,
        target_peak_db: float = -3.0,
        target_rms_db: float = -20.0,
        sample_rate: int = 44100,
        bitrate: str = "192k"
    ) -> bool:
        """
        Apply audio mastering for audiobook standards

        Standards applied:
        - Peak Level: target_peak_db (default -3dB)
        - RMS/Loudness: target_rms_db (default -20 LUFS, range -23 to -18)
        - Noise Floor: improved via highpass filter
        - Sample Rate: 44.1kHz
        - Bitrate: 192kbps

        Args:
            input_file: Input audio file path
            output_file: Output file path
            target_peak_db: Target peak level in dB (default: -3.0)
            target_rms_db: Target RMS/loudness level in LUFS (default: -20.0)
            sample_rate: Output sample rate (default: 44100)
            bitrate: Output bitrate (default: "192k")

        Returns:
            Success status
        """
        if not input_file.exists():
            logger.error(f"Input file not found: {input_file}")
            return False

        if not self.check_ffmpeg():
            logger.error("FFmpeg not available for mastering")
            return False

        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Build FFmpeg filter chain for audiobook mastering
            # 1. highpass: Remove low-frequency noise (below 80Hz)
            # 2. loudnorm: EBU R128 loudness normalization
            # 3. alimiter: Hard limiter for peak protection
            filter_chain = (
                f"highpass=f=80,"
                f"loudnorm=I={target_rms_db}:TP={target_peak_db}:LRA=7,"
                f"alimiter=limit={target_peak_db}dB"
            )

            cmd = [
                self.ffmpeg_path, "-y",
                "-i", str(input_file),
                "-af", filter_chain,
                "-ar", str(sample_rate),
                "-b:a", bitrate,
                "-codec:a", "libmp3lame",
                str(output_file)
            ]

            logger.info(f"Mastering audio: {input_file.name}")
            logger.info(f"  Target Peak: {target_peak_db}dB, Target RMS: {target_rms_db}LUFS")

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"FFmpeg mastering error: {result.stderr}")
                return False

            logger.info(f"Mastered audio saved: {output_file}")
            return True

        except Exception as e:
            logger.error(f"Error mastering audio: {e}")
            return False

    def mix_voice_with_intro_outro_music(
        self,
        voice_file: Path,
        music_file: Path,
        output_file: Path,
        intro_music_duration: float = 30.0,
        outro_music_duration: float = 30.0,
        voice_start_delay: float = 5.0,
        fade_duration: float = 5.0,
        music_volume: float = 0.3
    ) -> bool:
        """
        Mix voice audio with intro and outro background music

        Timeline:
        - [0s ~ 5s]: Music only (fade in)
        - [5s ~ 30s]: Voice starts + music continues (fade out at 25-30s)
        - [30s ~ end-30s]: Voice only
        - [end-30s ~ end]: Voice + outro music (fade in/out)

        Args:
            voice_file: Voice audio file path
            music_file: Background music file path
            output_file: Output file path
            intro_music_duration: Duration of intro music in seconds (default: 30.0)
            outro_music_duration: Duration of outro music in seconds (default: 30.0)
            voice_start_delay: Delay before voice starts in seconds (default: 5.0)
            fade_duration: Fade in/out duration in seconds (default: 5.0)
            music_volume: Music volume (0.0 - 1.0)

        Returns:
            Success status
        """
        if not voice_file.exists():
            logger.error(f"Voice file not found: {voice_file}")
            return False
        if not music_file.exists():
            logger.error(f"Music file not found: {music_file}")
            return False

        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)

            if not PYDUB_AVAILABLE:
                logger.error("pydub is required for intro/outro music mixing")
                return False

            # 1. Load audio files
            voice = AudioSegment.from_mp3(str(voice_file))
            music = AudioSegment.from_mp3(str(music_file))

            # 2. Adjust music volume
            music_db = 20 * (music_volume ** 0.5) - 20
            music = music + music_db

            # 3. Convert to milliseconds
            intro_ms = int(intro_music_duration * 1000)
            outro_ms = int(outro_music_duration * 1000)
            delay_ms = int(voice_start_delay * 1000)
            fade_ms = int(fade_duration * 1000)

            # 4. Prepare intro music (first 30 seconds with fade in/out)
            # Loop music if needed
            if len(music) < intro_ms:
                loops_needed = (intro_ms // len(music)) + 1
                music_looped = music * loops_needed
            else:
                music_looped = music

            intro_music = music_looped[:intro_ms]
            intro_music = intro_music.fade_in(fade_ms).fade_out(fade_ms)

            # 5. Prepare outro music (30 seconds with fade in/out)
            outro_music = music_looped[:outro_ms]
            outro_music = outro_music.fade_in(fade_ms).fade_out(fade_ms)

            # 6. Add silence before voice (5 second delay)
            voice_with_delay = AudioSegment.silent(duration=delay_ms) + voice

            # 7. Calculate total duration
            total_duration_ms = len(voice_with_delay)

            # 8. Create base track with voice
            final = voice_with_delay

            # 9. Overlay intro music at position 0
            final = final.overlay(intro_music, position=0)

            # 10. Overlay outro music at (total_duration - outro_duration)
            outro_start_ms = max(0, total_duration_ms - outro_ms)
            final = final.overlay(outro_music, position=outro_start_ms)

            # 11. Export
            final.export(str(output_file), format="mp3", bitrate="192k")

            logger.info(f"Mixed audio with intro/outro created: {output_file}")
            logger.info(f"  Total duration: {total_duration_ms/1000:.1f}s")
            logger.info(f"  Intro music: 0-{intro_music_duration}s (voice starts at {voice_start_delay}s)")
            logger.info(f"  Outro music: {outro_start_ms/1000:.1f}s-{total_duration_ms/1000:.1f}s")

            return True

        except Exception as e:
            logger.error(f"Error mixing audio with intro/outro: {e}")
            return False

    def analyze_audio(self, audio_file: Path) -> dict:
        """
        Analyze audio file for quality metrics

        Returns:
            Dictionary with peak_db, rms_db, duration, sample_rate
        """
        if not audio_file.exists():
            logger.error(f"Audio file not found: {audio_file}")
            return {}

        if not self.check_ffmpeg():
            logger.warning("FFmpeg not available for analysis")
            return {}

        try:
            ffprobe = self.ffmpeg_path.replace("ffmpeg", "ffprobe")

            # Get audio stats using ffprobe
            cmd = [
                ffprobe,
                "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=sample_rate,bit_rate:format=duration",
                "-of", "json",
                str(audio_file)
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                return {}

            import json
            data = json.loads(result.stdout)

            # Get loudness stats using ffmpeg
            loudness_cmd = [
                self.ffmpeg_path,
                "-i", str(audio_file),
                "-af", "loudnorm=print_format=json",
                "-f", "null", "-"
            ]

            loudness_result = subprocess.run(loudness_cmd, capture_output=True, text=True)

            # Parse loudness info from stderr (ffmpeg outputs to stderr)
            loudness_info = {}
            if "input_i" in loudness_result.stderr:
                # Extract JSON from ffmpeg output
                import re
                json_match = re.search(r'\{[^}]+\}', loudness_result.stderr, re.DOTALL)
                if json_match:
                    try:
                        loudness_info = json.loads(json_match.group())
                    except:
                        pass

            return {
                'duration': float(data.get('format', {}).get('duration', 0)),
                'sample_rate': int(data.get('streams', [{}])[0].get('sample_rate', 0)),
                'bit_rate': data.get('streams', [{}])[0].get('bit_rate', 'unknown'),
                'input_i': loudness_info.get('input_i', 'unknown'),  # Integrated loudness
                'input_tp': loudness_info.get('input_tp', 'unknown'),  # True peak
                'input_lra': loudness_info.get('input_lra', 'unknown'),  # Loudness range
            }

        except Exception as e:
            logger.error(f"Error analyzing audio: {e}")
            return {}
