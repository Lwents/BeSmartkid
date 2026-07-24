"""
Video Transcription Service
Ưu tiên phụ đề YouTube, không gọi Gemini API.
Hỗ trợ: Upload file video, YouTube URL
"""
import os
import logging
import tempfile
import subprocess
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class VideoTranscriber:
    """Service tạo transcript từ video (ưu tiên phụ đề YouTube)"""
    
    def __init__(self):
        pass
    
    def transcribe_video(self, video_path: str = None, video_url: str = None) -> Optional[str]:
        """
        Tạo transcript từ video file hoặc YouTube URL
        
        Args:
            video_path: Đường dẫn file video local (upload)
            video_url: YouTube URL
            
        Returns:
            Transcript text hoặc None nếu lỗi
        """
        try:
            # Nếu là YouTube URL, lấy phụ đề có sẵn trước
            if video_url and ('youtube' in video_url.lower() or 'youtu.be' in video_url.lower()):
                # Ưu tiên 1: Lấy phụ đề có sẵn từ YouTube (nhanh, miễn phí)
                subtitle = self._get_youtube_subtitle(video_url)
                if subtitle:
                    logger.info("Got subtitle from YouTube")
                    return subtitle

                logger.warning("No YouTube subtitle available; AI transcription disabled")
                return None
            
            # Nếu là URL trực tiếp (không phải YouTube)
            elif video_url:
                logger.warning("Direct video transcription disabled; no AI provider configured")
                return None
            
            # Nếu là file video upload
            elif video_path:
                logger.warning("Local video transcription disabled; no AI provider configured")
                return None
            
            logger.error("No video source provided")
            return None
            
        except Exception as e:
            logger.error(f"Error transcribing video: {e}")
            return None
    
    def _get_youtube_subtitle(self, youtube_url: str) -> Optional[str]:
        """Lấy phụ đề có sẵn từ YouTube (auto-generated hoặc manual)"""
        try:
            temp_dir = tempfile.mkdtemp()
            output_template = os.path.join(temp_dir, 'subtitle')
            
            # Lấy phụ đề tiếng Việt, nếu không có thì lấy auto-generated
            cmd = [
                'yt-dlp',
                '--skip-download',  # Không download video
                '--write-sub',      # Lấy phụ đề manual
                '--write-auto-sub', # Lấy phụ đề auto-generated
                '--sub-lang', 'vi,en',  # Ưu tiên tiếng Việt, sau đó English
                '--sub-format', 'vtt/srt/best',
                '--convert-subs', 'srt',
                '-o', output_template,
                '--no-playlist',
                youtube_url
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                logger.warning(f"yt-dlp subtitle error: {result.stderr}")
            
            # Tìm file phụ đề đã download
            subtitle_text = None
            for filename in os.listdir(temp_dir):
                if filename.endswith('.srt') or filename.endswith('.vtt'):
                    filepath = os.path.join(temp_dir, filename)
                    with open(filepath, 'r', encoding='utf-8') as f:
                        raw_subtitle = f.read()
                    # Parse và clean subtitle
                    subtitle_text = self._parse_subtitle(raw_subtitle)
                    break
            
            # Cleanup temp dir
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            return subtitle_text
            
        except subprocess.TimeoutExpired:
            logger.error("YouTube subtitle download timeout")
            return None
        except Exception as e:
            logger.error(f"Error getting YouTube subtitle: {e}")
            return None
    
    def _parse_subtitle(self, raw_subtitle: str) -> str:
        """Parse file SRT/VTT thành text thuần"""
        import re
        
        lines = raw_subtitle.split('\n')
        text_lines = []
        
        for line in lines:
            line = line.strip()
            
            # Bỏ qua số thứ tự
            if line.isdigit():
                continue
            
            # Bỏ qua timestamp (00:00:00,000 --> 00:00:00,000)
            if re.match(r'^\d{2}:\d{2}:\d{2}[,\.]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[,\.]\d{3}', line):
                continue
            
            # Bỏ qua header VTT
            if line.startswith('WEBVTT') or line.startswith('Kind:') or line.startswith('Language:'):
                continue
            
            # Bỏ qua các tag HTML/VTT
            line = re.sub(r'<[^>]+>', '', line)
            
            # Bỏ qua dòng trống
            if not line:
                continue
            
            # Tránh lặp lại dòng giống nhau liên tiếp
            if text_lines and line == text_lines[-1]:
                continue
            
            text_lines.append(line)
        
        return ' '.join(text_lines)
    
    def _download_youtube_video(self, youtube_url: str) -> Optional[str]:
        """Download video từ YouTube bằng yt-dlp"""
        try:
            temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
            temp_video_path = temp_video.name
            temp_video.close()
            
            # Sử dụng yt-dlp để download video
            cmd = [
                'yt-dlp',
                '-f', 'worst[ext=mp4]',  # Lấy chất lượng thấp nhất để giảm dung lượng
                '-o', temp_video_path,
                '--no-playlist',
                '--max-filesize', '20M',  # Giới hạn 20MB
                youtube_url
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                logger.error(f"yt-dlp error: {result.stderr}")
                return None
            
            if os.path.exists(temp_video_path) and os.path.getsize(temp_video_path) > 0:
                return temp_video_path
            
            return None
            
        except subprocess.TimeoutExpired:
            logger.error("YouTube download timeout")
            return None
        except Exception as e:
            logger.error(f"Error downloading YouTube video: {e}")
            return None
    
    def _download_direct_video(self, url: str) -> Optional[str]:
        """Download video từ URL trực tiếp"""
        try:
            temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
            
            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()
            
            for chunk in response.iter_content(chunk_size=8192):
                temp_video.write(chunk)
            temp_video.close()
            
            if os.path.getsize(temp_video.name) > 0:
                return temp_video.name
            return None
            
        except Exception as e:
            logger.error(f"Error downloading direct URL: {e}")
            return None
    

# Singleton instance
video_transcriber = VideoTranscriber()
