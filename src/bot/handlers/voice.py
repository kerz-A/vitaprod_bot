"""
Voice message handler for Telegram bot.
Converts voice messages to text and processes them through the same pipeline as text messages.
"""

import logging
import tempfile
import os
import inspect

from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from src.core.graph import chat  # Главный pipeline с RAG
from src.core.orders.intent import quick_order_check, is_order_confirmation

router = Router(name="voice")
logger = logging.getLogger(__name__)


def get_stt_service():
    """Get STT service with fallback."""
    try:
        from src.integrations.stt import get_stt_service as _get_stt
        return _get_stt()
    except ImportError:
        logger.warning("STT module not found")
        return None


def is_stt_available(stt_service) -> bool:
    """Check if STT service is available (works with different implementations)."""
    if stt_service is None:
        return False
    
    # Try different attribute names
    if hasattr(stt_service, 'is_available'):
        return stt_service.is_available
    elif hasattr(stt_service, 'available'):
        return stt_service.available
    elif hasattr(stt_service, 'api_key'):
        return bool(stt_service.api_key)
    
    # Assume available if service exists
    return True


async def transcribe_audio(stt_service, file_path: str, language: str = "ru") -> str:
    """Transcribe audio file (works with different STT implementations)."""
    
    # Find the transcribe method
    if hasattr(stt_service, 'transcribe_file'):
        method = stt_service.transcribe_file
    elif hasattr(stt_service, 'transcribe'):
        method = stt_service.transcribe
    elif hasattr(stt_service, 'recognize'):
        method = stt_service.recognize
    else:
        raise AttributeError("STT service has no transcribe method")
    
    # Check if method accepts 'language' parameter
    try:
        sig = inspect.signature(method)
        params = sig.parameters
        
        if 'language' in params:
            result = await method(file_path, language=language)
        elif 'lang' in params:
            result = await method(file_path, lang=language)
        else:
            # Call without language parameter
            result = await method(file_path)
    except (ValueError, TypeError):
        # Fallback: try with language, then without
        try:
            result = await method(file_path, language=language)
        except TypeError:
            result = await method(file_path)
    
    # FIX: Handle STTResult objects — extract text string
    if hasattr(result, 'text'):
        return result.text
    elif isinstance(result, str):
        return result
    else:
        logger.warning(f"Unexpected STT result type: {type(result)}, converting to str")
        return str(result)


@router.message(F.voice)
async def handle_voice_message(message: Message, state: FSMContext, bot: Bot) -> None:
    """
    Handle voice messages.
    
    1. Download voice file from Telegram
    2. Transcribe to text using STT service
    3. Process through the SAME pipeline as text messages (RAG + LLM)
    """
    user_id = message.from_user.id
    user_name = message.from_user.full_name or message.from_user.username
    
    # Check if user is in order FSM state
    current_state = await state.get_state()
    if current_state and "OrderStates" in str(current_state):
        await message.answer(
            "🎤 Пожалуйста, введите данные текстом.\n"
            "Голосовые сообщения недоступны во время оформления заказа."
        )
        return
    
    # Check if STT service is available
    stt_service = get_stt_service()
    if not is_stt_available(stt_service):
        await message.answer(
            "🎤 Голосовые сообщения временно недоступны.\n"
            "Пожалуйста, напишите текстом."
        )
        return
    
    # Show typing indicator
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    try:
        # Get voice file info
        voice = message.voice
        file_id = voice.file_id
        duration = voice.duration
        
        logger.info(f"Received voice message from {user_id}, duration: {duration}s")
        
        # Check duration (most STT services have limits)
        if duration > 120:  # 2 minutes max
            await message.answer(
                "🎤 Голосовое сообщение слишком длинное (максимум 2 минуты).\n"
                "Пожалуйста, запишите более короткое сообщение."
            )
            return
        
        # Download voice file
        file = await bot.get_file(file_id)
        file_path = file.file_path
        
        # Create temp file for audio
        with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as tmp:
            tmp_path = tmp.name
        
        try:
            # Download to temp file
            await bot.download_file(file_path, destination=tmp_path)
            
            # Transcribe
            text = await transcribe_audio(stt_service, tmp_path, language="ru")
            
            if not text or not text.strip():
                await message.answer(
                    "🎤 Не удалось распознать голосовое сообщение.\n"
                    "Попробуйте записать ещё раз или напишите текстом."
                )
                return
            
            text = text.strip()
            
            # Log transcription
            logger.info(f"Transcribed voice from {user_id}: {text[:100]}...")
            
            # Show what was recognized
            await message.answer(f"🎤 <i>Распознано:</i> «{text}»")
            
            # Show typing again for LLM response
            await bot.send_chat_action(chat_id=message.chat.id, action="typing")
            
            # ============================================
            # ВАЖНО: Обрабатываем через тот же pipeline
            # что и текстовые сообщения (с RAG!)
            # ============================================
            
            # Check for order intent
            order_started = False
            
            if is_order_confirmation(text):
                # "да", "оформить" — проверяем контекст
                order_started = await try_start_order_from_voice(
                    message, state, user_id, text
                )
            elif quick_order_check(text):
                # "хочу чернику 10 кг" — явный заказ
                order_started = await try_start_order_from_voice(
                    message, state, user_id, text
                )
            
            if order_started:
                return
            
            # Regular conversation through LangGraph (with RAG!)
            response = await chat(
                user_id=user_id,
                message=text,
                user_name=user_name,
            )
            
            # Send response
            await message.answer(response)
            
            logger.info(f"Voice processed for {user_id}: {text[:50]}...")
                
        finally:
            # Cleanup temp file
            try:
                os.unlink(tmp_path)
            except:
                pass
                
    except Exception as e:
        logger.error(f"Error processing voice message: {e}", exc_info=True)
        await message.answer(
            "🎤 Произошла ошибка при обработке голосового сообщения.\n"
            "Пожалуйста, попробуйте ещё раз или напишите текстом."
        )


async def try_start_order_from_voice(
    message: Message, 
    state: FSMContext, 
    user_id: int, 
    text: str
) -> bool:
    """
    Try to start order from voice transcription.
    Uses the same logic as text messages.
    """
    from src.core.graph import get_conversation_history
    from src.core.rag.retriever import get_retriever
    from src.core.orders.intent import detect_order_intent
    
    try:
        # Get conversation history
        history = await get_conversation_history(user_id)
        context = "\n".join([
            f"{'Клиент' if h['role'] == 'user' else 'Бот'}: {h['content']}" 
            for h in history[-6:]
        ]) if history else ""
        
        # Get relevant products from RAG
        retriever = get_retriever()
        result = await retriever.retrieve(query=text, top_k=10)
        
        products = []
        if result and result.products:
            for p in result.products:
                if hasattr(p, 'model_dump'):
                    products.append(p.model_dump())
                elif isinstance(p, dict):
                    products.append(p)
                else:
                    products.append(vars(p))
        
        if not products:
            return False
        
        # Detect order intent
        intent = await detect_order_intent(
            user_message=text,
            conversation_context=context,
            available_products=products,
        )
        
        if intent.is_order and intent.items and intent.confidence >= 0.7:
            from src.bot.handlers.order import start_order_from_cart
            await start_order_from_cart(message, state, intent.items)
            return True
        
    except Exception as e:
        logger.warning(f"Order intent detection from voice failed: {e}")
    
    return False


@router.message(F.audio)
async def handle_audio_file(message: Message) -> None:
    """Handle audio files (not voice messages)."""
    await message.answer(
        "🎵 Я принимаю только голосовые сообщения.\n"
        "Нажмите и удерживайте 🎤 чтобы записать голосовое сообщение."
    )


@router.message(F.video_note)
async def handle_video_note(message: Message) -> None:
    """Handle video notes (круглые видео)."""
    await message.answer(
        "🎥 К сожалению, я пока не умею обрабатывать видеосообщения.\n"
        "Пожалуйста, запишите голосовое сообщение или напишите текстом."
    )
