# ai_personalization/api/tts_views.py
"""
Text-to-Speech API sử dụng Google Cloud TTS hoặc gTTS
"""
import os
import base64
import logging
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
from io import BytesIO

logger = logging.getLogger(__name__)


class TextToSpeechView(APIView):
    """
    POST /api/student/ai/tts/
    
    Chuyển văn bản thành giọng nói tiếng Việt
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        text = request.data.get('text', '').strip()
        
        if not text:
            return Response(
                {'error': 'Text is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Giới hạn độ dài text
        if len(text) > 500:
            text = text[:500]
        
        # Làm sạch text (bỏ emoji)
        import re
        clean_text = re.sub(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002600-\U000026FF\U00002700-\U000027BF]', '', text)
        clean_text = clean_text.strip()
        
        if not clean_text:
            return Response(
                {'error': 'No valid text after cleaning'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Thử Google Cloud TTS trước (nếu có key)
        google_tts_key = os.environ.get('GOOGLE_TTS_API_KEY')
        if google_tts_key:
            result = self._google_cloud_tts(clean_text, google_tts_key)
            if result:
                return result
        
        # Fallback: dùng gTTS (miễn phí)
        result = self._gtts_fallback(clean_text)
        if result:
            return result
        
        return Response(
            {'error': 'TTS service unavailable'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    
    def _google_cloud_tts(self, text, api_key):
        """Google Cloud Text-to-Speech API"""
        import requests
        
        try:
            url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
            
            payload = {
                "input": {"text": text},
                "voice": {
                    "languageCode": "vi-VN",
                    "name": "vi-VN-Neural2-A",  # Giọng nữ tự nhiên
                    "ssmlGender": "FEMALE"
                },
                "audioConfig": {
                    "audioEncoding": "MP3",
                    "speakingRate": 0.9,  # Chậm hơn cho trẻ em
                    "pitch": 1.0
                }
            }
            
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                audio_content = data.get('audioContent')
                if audio_content:
                    # Decode base64 và trả về audio
                    audio_bytes = base64.b64decode(audio_content)
                    return HttpResponse(
                        audio_bytes,
                        content_type='audio/mpeg',
                        headers={
                            'Content-Disposition': 'inline; filename="speech.mp3"'
                        }
                    )
            
            logger.warning(f"Google TTS error: {response.status_code}")
            return None
            
        except Exception as e:
            logger.error(f"Google TTS exception: {e}")
            return None
    
    def _gtts_fallback(self, text):
        """Fallback dùng gTTS (Google Translate TTS - miễn phí)"""
        try:
            from gtts import gTTS
            
            # Tạo audio
            tts = gTTS(text=text, lang='vi', slow=False)
            
            # Lưu vào buffer
            audio_buffer = BytesIO()
            tts.write_to_fp(audio_buffer)
            audio_buffer.seek(0)
            
            return HttpResponse(
                audio_buffer.read(),
                content_type='audio/mpeg',
                headers={
                    'Content-Disposition': 'inline; filename="speech.mp3"'
                }
            )
            
        except ImportError:
            logger.error("gTTS not installed. Run: pip install gTTS")
            return None
        except Exception as e:
            logger.error(f"gTTS error: {e}")
            return None
