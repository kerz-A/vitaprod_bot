"""
Speech-to-Text service for voice message processing.
Supports multiple STT providers: Groq Whisper, OpenAI Whisper.
"""

import logging
import os
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class STTResult:
    """Result of speech-to-text transcription."""
    text: str
    language: Optional[str] = None
    duration: Optional[float] = None
    confidence: Optional[float] = None


class STTProvider(ABC):
    """Abstract base class for STT providers."""
    
    @abstractmethod
    async def transcribe(self, audio_path: str) -> STTResult:
        """Transcribe audio file to text."""
        pass


class GroqWhisperSTT(STTProvider):
    """
    Groq Whisper STT provider.
    FREE tier available, very fast inference.
    
    Limits (free tier):
    - ~14,400 requests/day
    - ~25 requests/minute
    - 25 MB max file size
    """
    
    API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
    
    def __init__(self, api_key: str, model: str = "whisper-large-v3"):
        """
        Initialize Groq Whisper provider.
        
        Args:
            api_key: Groq API key (get free at console.groq.com)
            model: Whisper model to use:
                   - whisper-large-v3 (best quality)
                   - whisper-large-v3-turbo (faster)
        """
        self.api_key = api_key
        self.model = model
    
    async def transcribe(self, audio_path: str) -> STTResult:
        """
        Transcribe audio using Groq Whisper API.
        
        Args:
            audio_path: Path to audio file (ogg, mp3, wav, webm, etc.)
            
        Returns:
            STTResult with transcribed text
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }
        
        async with aiohttp.ClientSession() as session:
            # Read file and prepare multipart form data
            with open(audio_path, "rb") as f:
                file_data = f.read()
            
            data = aiohttp.FormData()
            data.add_field(
                "file",
                file_data,
                filename=Path(audio_path).name,
                content_type="audio/ogg"
            )
            data.add_field("model", self.model)
            data.add_field("language", "ru")  # Force Russian language
            data.add_field("response_format", "verbose_json")
            
            try:
                async with session.post(
                    self.API_URL,
                    headers=headers,
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Groq Whisper API error: {response.status} - {error_text}")
                        raise Exception(f"STT API error: {response.status}")
                    
                    result = await response.json()
                    
                    return STTResult(
                        text=result.get("text", "").strip(),
                        language=result.get("language"),
                        duration=result.get("duration"),
                    )
                    
            except aiohttp.ClientError as e:
                logger.error(f"Network error during STT: {e}")
                raise


class OpenAIWhisperSTT(STTProvider):
    """
    OpenAI Whisper STT provider.
    High quality, paid API ($0.006/minute).
    """
    
    API_URL = "https://api.openai.com/v1/audio/transcriptions"
    
    def __init__(self, api_key: str, model: str = "whisper-1"):
        self.api_key = api_key
        self.model = model
    
    async def transcribe(self, audio_path: str) -> STTResult:
        """Transcribe audio using OpenAI Whisper API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }
        
        async with aiohttp.ClientSession() as session:
            with open(audio_path, "rb") as f:
                file_data = f.read()
            
            data = aiohttp.FormData()
            data.add_field(
                "file",
                file_data,
                filename=Path(audio_path).name,
                content_type="audio/ogg"
            )
            data.add_field("model", self.model)
            data.add_field("language", "ru")
            data.add_field("response_format", "verbose_json")
            
            try:
                async with session.post(
                    self.API_URL,
                    headers=headers,
                    data=data,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"OpenAI Whisper API error: {response.status} - {error_text}")
                        raise Exception(f"STT API error: {response.status}")
                    
                    result = await response.json()
                    
                    return STTResult(
                        text=result.get("text", "").strip(),
                        language=result.get("language"),
                        duration=result.get("duration"),
                    )
                    
            except aiohttp.ClientError as e:
                logger.error(f"Network error during STT: {e}")
                raise


class STTService:
    """
    Main STT service that manages providers.
    """
    
    def __init__(self, provider: STTProvider):
        self.provider = provider
    
    async def transcribe_file(self, audio_path: str) -> STTResult:
        """
        Transcribe audio file.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            STTResult with transcribed text
        """
        return await self.provider.transcribe(audio_path)
    
    async def transcribe_telegram_voice(
        self,
        bot,
        voice_file_id: str,
    ) -> STTResult:
        """
        Download and transcribe Telegram voice message.
        
        Args:
            bot: Telegram bot instance
            voice_file_id: Telegram file ID of voice message
            
        Returns:
            STTResult with transcribed text
        """
        # Create temp directory if not exists
        temp_dir = Path(tempfile.gettempdir()) / "vitaprod_voice"
        temp_dir.mkdir(exist_ok=True)
        
        # Download voice file
        file = await bot.get_file(voice_file_id)
        
        # Generate temp file path
        temp_file = temp_dir / f"{voice_file_id}.ogg"
        
        try:
            # Download file
            await bot.download_file(file.file_path, destination=temp_file)
            
            # Transcribe
            result = await self.transcribe_file(str(temp_file))
            
            return result
            
        finally:
            # Cleanup temp file
            if temp_file.exists():
                temp_file.unlink()


# =============================================================================
# Factory function
# =============================================================================

_stt_service: Optional[STTService] = None


def get_stt_service() -> STTService:
    """Get or create STT service instance."""
    global _stt_service
    
    if _stt_service is None:
        from src.config import settings
        
        # Choose provider based on configuration (priority: Groq > OpenAI)
        if settings.groq_api_key:
            provider = GroqWhisperSTT(
                api_key=settings.groq_api_key,
                model=settings.whisper_model or "whisper-large-v3"
            )
            logger.info("Using Groq Whisper for STT (FREE)")
        elif settings.openai_api_key:
            provider = OpenAIWhisperSTT(
                api_key=settings.openai_api_key,
                model="whisper-1"
            )
            logger.info("Using OpenAI Whisper for STT")
        else:
            raise ValueError(
                "No STT provider configured. "
                "Set GROQ_API_KEY (free!) or OPENAI_API_KEY in .env"
            )
        
        _stt_service = STTService(provider)
    
    return _stt_service