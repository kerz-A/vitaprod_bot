"""
Speech-to-Text integration module.
"""

from src.integrations.stt.service import (
    STTResult,
    STTProvider,
    STTService,
    GroqWhisperSTT,
    OpenAIWhisperSTT,
    get_stt_service,
)

__all__ = [
    "STTResult",
    "STTProvider", 
    "STTService",
    "GroqWhisperSTT",
    "OpenAIWhisperSTT",
    "get_stt_service",
]