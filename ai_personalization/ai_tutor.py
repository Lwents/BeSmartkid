# ai_personalization/ai_tutor.py
"""
AI Tutor Engine - Trợ lý học tập thông minh cho trẻ cấp 1
Tích hợp OpenRouter để:
- Giải thích bài học đơn giản
- Gợi ý khi trẻ gặp khó khăn (không cho đáp án)
- Động viên, khen ngợi
- Điều chỉnh ngôn ngữ phù hợp lứa tuổi
"""
import os
import json
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

# System prompts cho AI Tutor
TUTOR_SYSTEM_PROMPT = """Bạn là trợ lý học tập AI của SunnyEdu - nền tảng học tập thông minh cho học sinh Việt Nam.

NGUYÊN TẮC QUAN TRỌNG:
1. Luôn dùng ngôn ngữ đơn giản, dễ hiểu
2. Thêm emoji để tạo sự vui vẻ 🌟 ✨ 🎉
3. KHÔNG BAO GIỜ cho đáp án trực tiếp - chỉ gợi ý từng bước
4. Động viên và khen ngợi khi học sinh cố gắng
5. Nếu học sinh sai, nhẹ nhàng hướng dẫn cách nghĩ đúng
6. Trả lời đủ ý, rõ ràng (có thể 6-8 câu nếu cần), vẫn giữ văn phong đơn giản
7. Dùng ví dụ gần gũi với cuộc sống hàng ngày

PHONG CÁCH:
- Xưng hô: "bạn" hoặc "em" với học sinh
- Tuyệt đối không tự xưng "Mặt Trời"/"mặt trời" hay bất kỳ biệt danh nào; chỉ xưng "mình", "tớ" hoặc "AI"
- Giọng điệu: Vui vẻ, ấm áp, khích lệ
- Khi học sinh đúng: Khen ngợi nhiệt tình
- Khi học sinh sai: "Gần đúng rồi! Để mình gợi ý nhé..."
"""

HINT_SYSTEM_PROMPT = """Bạn là trợ lý học tập AI của SunnyEdu. Nhiệm vụ: Đưa ra GỢI Ý để học sinh tự tìm đáp án.

QUY TẮC GỢI Ý:
1. KHÔNG BAO GIỜ nói đáp án trực tiếp
2. Gợi ý theo từng bước nhỏ (scaffolding)
3. Dùng câu hỏi dẫn dắt: "Bạn thử nghĩ xem...", "Nếu... thì sao?"
4. Cho ví dụ tương tự đơn giản hơn
5. Nhắc lại kiến thức cần dùng

VÍ DỤ:
- Câu hỏi: "5 + 7 = ?"
- Gợi ý tốt: "Bạn đếm thêm 7 từ số 5 nhé! 5... rồi thêm 1 là 6, thêm 1 nữa là 7..."
- Gợi ý xấu: "Đáp án là 12" (KHÔNG ĐƯỢC!)
"""


class AITutorEngine:
    """
    AI Tutor Engine sử dụng OpenRouter
    """
    
    def __init__(self):
        self.openrouter_api_key = os.environ.get('OPENROUTER_API_KEY') or os.environ.get('DEEPSEEK_API_KEY')
        self.openrouter_model = (
            os.environ.get('OPENROUTER_MODEL')
            or os.environ.get('DEEPSEEK_MODEL')
            or 'openai/gpt-4o'
        )
        self.default_provider = 'openrouter'
        
        # Log API keys status on init
        logger.info(
            "AI Tutor initialized - OpenRouter: %s, Model: %s",
            'YES' if self.openrouter_api_key else 'NO',
            self.openrouter_model,
        )
        
    def _call_openrouter(self, messages: list) -> str:
        """Call OpenRouter API"""
        import requests
        
        logger.info(
            "Calling OpenRouter API with key: %s..., model: %s",
            self.openrouter_api_key[:10] if self.openrouter_api_key else 'NONE',
            self.openrouter_model,
        )
        
        if not self.openrouter_api_key:
            raise Exception("OPENROUTER_API_KEY not configured")
        
        url = "https://openrouter.ai/api/v1/chat/completions"
        model = self.openrouter_model
        
        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://sunnyedu.local",
            "X-Title": "SunnyEdu AI Tutor",
        }
        
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 800,
            "temperature": 0.7,
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code != 200:
            logger.error(f"OpenRouter API error: {response.status_code} - {response.text}")
            raise Exception(f"OpenRouter API error: {response.status_code}")
        
        data = response.json()
        
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            logger.error(f"OpenRouter response parsing error: {e}")
            raise Exception("Failed to parse OpenRouter response")
    
    def chat(
        self,
        user_message: str,
        context: Dict[str, Any] = None,
        conversation_history: List[Dict] = None,
        student_grade: int = 1,
        provider: str = None
    ) -> Dict[str, Any]:
        """
        Chat với AI Tutor
        
        Args:
            user_message: Tin nhắn từ học sinh
            context: Ngữ cảnh (bài học hiện tại, câu hỏi đang làm, etc.)
            conversation_history: Lịch sử hội thoại
            student_grade: Lớp của học sinh (1-5)
            provider: 'openrouter'
        
        Returns:
            Dict với response và metadata
        """
        provider = 'openrouter'
        
        # Build context-aware system prompt
        system_prompt = self._build_system_prompt(context, student_grade)
        
        # Build messages
        messages = self._build_messages(
            system_prompt, 
            user_message, 
            conversation_history or []
        )
        
        try:
            response = self._call_openrouter(messages)
            
            return {
                'success': True,
                'message': response,
                'provider': provider,
                'tokens_used': 0
            }
            
        except Exception as e:
            logger.error(f"AI Tutor error: {str(e)}")
            return {
                'success': False,
                'message': self._get_fallback_response(user_message),
                'error': str(e),
                'provider': 'fallback'
            }
    
    def get_hint(
        self,
        question_text: str,
        question_type: str,
        choices: List[str] = None,
        student_answer: str = None,
        correct_answer: str = None,
        hint_level: int = 1,
        student_grade: int = 1
    ) -> Dict[str, Any]:
        """
        Lấy gợi ý cho câu hỏi (không cho đáp án)
        
        Args:
            question_text: Nội dung câu hỏi
            question_type: Loại câu hỏi (multiple_choice, fill_blank, etc.)
            choices: Các lựa chọn (nếu có)
            student_answer: Câu trả lời của học sinh (nếu đã trả lời sai)
            correct_answer: Đáp án đúng (để AI biết hướng gợi ý, KHÔNG tiết lộ)
            hint_level: Mức độ gợi ý (1=nhẹ, 2=trung bình, 3=chi tiết)
            student_grade: Lớp của học sinh
        
        Returns:
            Dict với hint và metadata
        """
        # Build hint prompt
        hint_prompt = self._build_hint_prompt(
            question_text, question_type, choices,
            student_answer, correct_answer, hint_level, student_grade
        )
        
        messages = [
            {"role": "system", "content": HINT_SYSTEM_PROMPT},
            {"role": "user", "content": hint_prompt}
        ]
        
        try:
            response = self._call_openrouter(messages)
            
            return {
                'success': True,
                'hint': response,
                'hint_level': hint_level,
                'can_get_more_hints': hint_level < 3
            }
            
        except Exception as e:
            logger.error(f"AI Hint error: {str(e)}")
            return {
                'success': False,
                'hint': self._get_fallback_hint(hint_level),
                'error': str(e)
            }
    
    def explain_concept(
        self,
        concept: str,
        subject: str,
        student_grade: int = 1,
        use_examples: bool = True
    ) -> Dict[str, Any]:
        """
        Giải thích khái niệm cho trẻ
        
        Args:
            concept: Khái niệm cần giải thích
            subject: Môn học (math, vietnamese, english, science)
            student_grade: Lớp của học sinh
            use_examples: Có dùng ví dụ không
        """
        prompt = f"""Giải thích khái niệm "{concept}" trong môn {subject} cho học sinh lớp {student_grade}.

Yêu cầu:
- Dùng ngôn ngữ đơn giản, phù hợp trẻ {5 + student_grade} tuổi
- {"Cho 1-2 ví dụ gần gũi" if use_examples else "Không cần ví dụ"}
- Tối đa 4-5 câu
- Thêm emoji cho vui 🌟
"""
        
        messages = [
            {"role": "system", "content": TUTOR_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = self._call_openrouter(messages)
            
            return {
                'success': True,
                'explanation': response,
                'concept': concept,
                'subject': subject
            }
        except Exception as e:
            logger.error(f"AI Explain error: {str(e)}")
            return {
                'success': False,
                'explanation': f"AI đang bận một chút! Bạn hỏi lại sau nhé! 🌟",
                'error': str(e)
            }
    
    def encourage(
        self,
        situation: str,
        student_name: str = "con",
        score: float = None
    ) -> str:
        """
        Tạo lời động viên cho trẻ
        
        Args:
            situation: 'correct', 'incorrect', 'streak', 'completed', 'struggling'
            student_name: Tên học sinh
            score: Điểm số (nếu có)
        """
        encouragements = {
            'correct': [
                f"Tuyệt vời {student_name}! 🎉 Con giỏi quá!",
                f"Đúng rồi! ⭐ {student_name} thật thông minh!",
                f"Xuất sắc! 🌟 Cứ tiếp tục như vậy nhé!",
                f"Wow! {student_name} làm đúng rồi! 🎊",
            ],
            'incorrect': [
                f"Gần đúng rồi {student_name}! 💪 Thử lại nhé!",
                f"Không sao! Sai là để học mà! 🌈 Cố lên!",
                f"Mình tin {student_name} làm được! Thử lần nữa nào! ✨",
            ],
            'streak': [
                f"🔥 {student_name} đang có streak tuyệt vời!",
                f"Wow! Chuỗi ngày học liên tục! 🔥 Giỏi quá!",
            ],
            'completed': [
                f"🏆 {student_name} đã hoàn thành bài học! Tuyệt vời!",
                f"Chúc mừng {student_name}! 🎉 Bài học xong rồi!",
            ],
            'struggling': [
                f"Từ từ thôi {student_name}! 🌟 Mình ở đây giúp bạn!",
                f"Bài này hơi khó nhỉ? 🤔 Để mình gợi ý nhé!",
            ]
        }
        
        import random
        messages = encouragements.get(situation, encouragements['correct'])
        return random.choice(messages)
    
    def _build_system_prompt(self, context: Dict, student_grade: int) -> str:
        """Build context-aware system prompt"""
        prompt = TUTOR_SYSTEM_PROMPT
        
        if context:
            prompt += f"\n\nNGỮ CẢNH HIỆN TẠI:\n"
            if context.get('lesson_title'):
                prompt += f"- Bài học: {context['lesson_title']}\n"
            if context.get('subject'):
                prompt += f"- Môn: {context['subject']}\n"
            if context.get('current_question'):
                prompt += f"- Câu hỏi đang làm: {context['current_question']}\n"
        
        prompt += f"\n- Học sinh lớp: {student_grade}\n"
        prompt += f"- Độ tuổi ước tính: {5 + student_grade} tuổi\n"
        
        return prompt
    
    def _build_messages(
        self, 
        system_prompt: str, 
        user_message: str, 
        history: List[Dict]
    ) -> List[Dict]:
        """Build message list for API call"""
        messages = [{"role": "system", "content": system_prompt}]
        
        # Add conversation history (last 10 messages)
        for msg in history[-10:]:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })
        
        # Add current message
        messages.append({"role": "user", "content": user_message})
        
        return messages
    
    def _build_hint_prompt(
        self,
        question_text: str,
        question_type: str,
        choices: List[str],
        student_answer: str,
        correct_answer: str,
        hint_level: int,
        student_grade: int
    ) -> str:
        """Build prompt for hint generation"""
        prompt = f"""Câu hỏi ({question_type}): {question_text}
"""
        if choices:
            prompt += f"Các lựa chọn: {', '.join(choices)}\n"
        
        if student_answer:
            prompt += f"Học sinh đã trả lời: {student_answer} (SAI)\n"
        
        prompt += f"""
Mức gợi ý: {hint_level}/3 (1=nhẹ, 3=chi tiết)
Học sinh lớp: {student_grade}

Hãy đưa ra gợi ý mức {hint_level} để học sinh tự tìm đáp án.
NHỚ: KHÔNG được nói đáp án "{correct_answer}" trực tiếp!
"""
        return prompt
    
    def _get_fallback_response(self, user_message: str) -> str:
        """Fallback response when AI is unavailable"""
        return "AI đang bận một chút! 🌟 Bạn thử hỏi lại sau nhé, hoặc nhấn nút Gợi ý để được giúp đỡ!"
    
    def _get_fallback_hint(self, hint_level: int) -> str:
        """Fallback hint when AI is unavailable"""
        hints = {
            1: "💡 Gợi ý: Con đọc lại đề bài thật kỹ nhé!",
            2: "💡 Gợi ý: Con thử nghĩ xem bài này liên quan đến kiến thức gì đã học?",
            3: "💡 Gợi ý: Hãy chia bài toán thành từng bước nhỏ và giải từng bước một nhé!"
        }
        return hints.get(hint_level, hints[1])
    
    def analyze_weaknesses(
        self,
        student_performance: Dict[str, Any],
        student_grade: int = 1
    ) -> Dict[str, Any]:
        """
        Phân tích điểm yếu của học sinh dựa trên kết quả học tập
        
        Args:
            student_performance: {
                'subjects': [{'name': 'Toán', 'score': 70, 'wrong_topics': ['Phép cộng', 'Phép trừ']}],
                'recent_exercises': [{'topic': 'Phép cộng', 'correct': False, 'time_spent': 120}],
                'streak': 3,
                'total_completed': 50
            }
            student_grade: Lớp của học sinh
        """
        prompt = f"""Phân tích kết quả học tập của học sinh lớp {student_grade}:

Dữ liệu:
{json.dumps(student_performance, ensure_ascii=False, indent=2)}

Hãy phân tích và trả về JSON với format:
{{
    "weaknesses": [
        {{"topic": "Tên chủ đề yếu", "subject": "Môn học", "severity": "high/medium/low", "suggestion": "Gợi ý cải thiện ngắn gọn"}}
    ],
    "strengths": ["Điểm mạnh 1", "Điểm mạnh 2"],
    "overall_message": "Nhận xét tổng quan cho phụ huynh (2-3 câu)",
    "encouragement": "Lời động viên cho học sinh (1-2 câu, có emoji)"
}}

CHỈ trả về JSON, không có text khác."""

        messages = [
            {"role": "system", "content": "Bạn là chuyên gia phân tích giáo dục tiểu học. Trả lời bằng JSON."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = self._call_openrouter(messages)
            # Parse JSON từ response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return {
                    'success': True,
                    'analysis': json.loads(json_match.group())
                }
            return {'success': False, 'error': 'Invalid JSON response'}
        except Exception as e:
            logger.error(f"Analyze weaknesses error: {e}")
            return {
                'success': False,
                'analysis': {
                    'weaknesses': [],
                    'strengths': ['Chăm chỉ học tập'],
                    'overall_message': 'Cần thu thập thêm dữ liệu để phân tích chính xác.',
                    'encouragement': 'Con đang làm tốt lắm! Cố gắng lên nhé! 🌟'
                }
            }
    
    def generate_practice_exercises(
        self,
        weaknesses: List[Dict],
        student_grade: int = 1,
        num_exercises: int = 5,
        wrong_questions: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        Tạo bài luyện tập dựa trên điểm yếu và câu hỏi sai cụ thể
        
        Args:
            weaknesses: Danh sách điểm yếu từ analyze_weaknesses
            student_grade: Lớp học sinh
            num_exercises: Số bài tập cần tạo
            wrong_questions: Danh sách câu hỏi học sinh làm sai (tùy chọn)
        """
        if not weaknesses:
            return {'success': False, 'exercises': [], 'error': 'No weaknesses provided'}
        
        topics = [w.get('topic', '') for w in weaknesses[:3]]  # Top 3 điểm yếu
        
        # Nếu có wrong_questions, tạo bài tập dựa trên câu sai
        if wrong_questions and len(wrong_questions) > 0:
            wrong_questions_text = ""
            for i, wq in enumerate(wrong_questions[:10], 1):  # Lấy tối đa 10 câu sai
                wrong_questions_text += f"\n{i}. Câu hỏi: {wq.get('question_text', '')}\n"
                wrong_questions_text += f"   Học sinh trả lời: {wq.get('student_answer', '')}\n"
                wrong_questions_text += f"   Đáp án đúng: {wq.get('correct_answer', '')}\n"
            
            prompt = f"""Bạn là giáo viên tiểu học. Học sinh lớp {student_grade} đã làm sai các câu hỏi sau:

{wrong_questions_text}

YÊU CẦU:
1. Phân tích những câu sai này để hiểu học sinh đang gặp khó khăn ở đâu
2. Tạo {num_exercises} câu hỏi TRẮC NGHIỆM MỚI (không trùng với câu hỏi trên) để giúp học sinh cải thiện điểm yếu
3. Các câu hỏi mới phải:
   - Cùng chủ đề/nội dung với câu sai
   - Độ khó tương đương hoặc dễ hơn một chút
   - Giúp học sinh hiểu rõ hơn về phần kiến thức này
   - Mỗi câu có 4 đáp án A, B, C, D
   - Câu hỏi ngắn gọn, dễ hiểu cho học sinh lớp {student_grade}
   - Có giải thích ngắn cho đáp án đúng

Trả về JSON array:
[
    {{
        "question": "Câu hỏi mới",
        "topic": "Chủ đề",
        "choices": ["A. ...", "B. ...", "C. ...", "D. ..."],
        "correct_answer": "A",
        "explanation": "Giải thích ngắn tại sao đáp án này đúng",
        "difficulty": "easy/medium/hard",
        "related_wrong_question": "Câu hỏi liên quan đến câu sai số X"
    }}
]

CHỈ trả về JSON array, không có text khác."""
        else:
            # Tạo bài tập từ topics chung
            prompt = (
                f"""Tạo {num_exercises} câu hỏi trắc nghiệm cho học sinh lớp {student_grade} về các chủ đề: {', '.join(topics)}

Yêu cầu:
- Mỗi câu có 4 đáp án A, B, C, D
- Độ khó phù hợp lớp {student_grade}
- Câu hỏi ngắn gọn, dễ hiểu
- Có giải thích ngắn cho đáp án đúng

Trả về JSON array:
[
    {{
        "question": "Câu hỏi",
        "topic": "Chủ đề",
        "choices": ["A. ...", "B. ...", "C. ...", "D. ..."],
        "correct_answer": "A",
        "explanation": "Giải thích ngắn",
        "difficulty": "easy/medium/hard"
    }}
]

CHỈ trả về JSON array, không có text khác."""
            )

        messages = [
            {"role": "system", "content": f"Bạn là giáo viên tiểu học tạo bài tập cho học sinh lớp {student_grade}. Trả lời bằng JSON."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = self._call_openrouter(messages)
            # Parse JSON từ response
            import re
            json_match = re.search(r'\[[\s\S]*\]', response)
            if json_match:
                exercises = json.loads(json_match.group())
                return {
                    'success': True,
                    'exercises': exercises,
                    'topics': topics
                }
            return {'success': False, 'exercises': [], 'error': 'Invalid JSON response'}
        except Exception as e:
            logger.error(f"Generate exercises error: {e}")
            return {
                'success': False,
                'exercises': [],
                'error': str(e)
            }
    
    def generate_daily_report(
        self,
        student_name: str,
        performance_today: Dict[str, Any],
        weaknesses: List[Dict],
        student_grade: int = 1
    ) -> Dict[str, Any]:
        """
        Tạo báo cáo hàng ngày cho phụ huynh
        """
        prompt = f"""Tạo báo cáo học tập ngắn gọn cho phụ huynh về học sinh {student_name} (lớp {student_grade}):

Kết quả hôm nay:
- Số bài hoàn thành: {performance_today.get('completed', 0)}
- Điểm trung bình: {performance_today.get('avg_score', 0)}%
- Thời gian học: {performance_today.get('time_spent', 0)} phút

Điểm cần cải thiện:
{json.dumps(weaknesses, ensure_ascii=False)}

Trả về JSON:
{{
    "title": "Tiêu đề thông báo ngắn",
    "summary": "Tóm tắt 1-2 câu cho phụ huynh",
    "details": "Chi tiết hơn về tiến độ",
    "suggestions": ["Gợi ý 1 cho phụ huynh", "Gợi ý 2"],
    "student_message": "Tin nhắn động viên cho học sinh (có emoji)"
}}"""

        messages = [
            {"role": "system", "content": "Bạn là trợ lý giáo dục, viết báo cáo cho phụ huynh học sinh tiểu học."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = self._call_openrouter(messages)
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return {
                    'success': True,
                    'report': json.loads(json_match.group())
                }
            return {'success': False, 'error': 'Invalid JSON response'}
        except Exception as e:
            logger.error(f"Generate report error: {e}")
            return {
                'success': False,
                'report': {
                    'title': f'Báo cáo học tập của {student_name}',
                    'summary': 'Hôm nay con đã cố gắng học tập.',
                    'details': 'Cần thu thập thêm dữ liệu.',
                    'suggestions': ['Khuyến khích con học đều đặn mỗi ngày'],
                    'student_message': 'Con làm tốt lắm! Cố gắng lên nhé! 🌟'
                }
            }
    
    def generate_improvement_suggestion(
        self,
        wrong_answers: List[Dict],
        score_percent: float,
        student_grade: int = 1
    ) -> Dict[str, Any]:
        """
        Tạo gợi ý cải thiện cụ thể dựa trên các câu trả lời sai
        
        Args:
            wrong_answers: Danh sách câu sai [{question, student_answer, correct_answer}]
            score_percent: Phần trăm điểm đạt được
            student_grade: Lớp học sinh
        """
        if not wrong_answers:
            return {'success': False, 'suggestion': ''}
        
        # Tạo mô tả các câu sai
        wrong_desc = ""
        for i, w in enumerate(wrong_answers[:3], 1):
            wrong_desc += f"{i}. Câu hỏi: {w.get('question', '')[:100]}\n"
            wrong_desc += f"   Con trả lời: {w.get('student_answer', '')}\n"
            wrong_desc += f"   Đáp án đúng: {w.get('correct_answer', '')}\n\n"
        
        prompt = f"""Học sinh lớp {student_grade} vừa làm bài tập và đạt {score_percent:.0f}%.

Các câu con làm sai:
{wrong_desc}

Hãy viết MỘT tin nhắn ngắn gọn (2-3 câu) để:
1. Động viên con (không chê bai)
2. Gợi ý cách cải thiện cụ thể cho những lỗi trên
3. Khuyến khích con ôn lại

Dùng ngôn ngữ thân thiện, có emoji, phù hợp trẻ {5 + student_grade} tuổi.
CHỈ trả về tin nhắn, không có gì khác."""

        messages = [
            {"role": "system", "content": "Bạn là trợ lý học tập AI của SunnyEdu - thân thiện với học sinh Việt Nam."},
            {"role": "user", "content": prompt}
        ]
        
        try:
            response = self._call_openrouter(messages)
            
            # Làm sạch response
            suggestion = response.strip()
            # Giới hạn độ dài
            if len(suggestion) > 300:
                suggestion = suggestion[:297] + "..."
            
            return {
                'success': True,
                'suggestion': suggestion,
                'score_percent': score_percent,
                'wrong_count': len(wrong_answers)
            }
        except Exception as e:
            logger.error(f"Generate improvement suggestion error: {e}")
            # Fallback message
            fallback = f"Bạn đạt {score_percent:.0f}% rồi! 🌟 Có vài câu chưa đúng, ôn lại nhé. Mình tin bạn sẽ làm tốt hơn! 💪"
            return {
                'success': True,
                'suggestion': fallback,
                'score_percent': score_percent,
                'wrong_count': len(wrong_answers)
            }


# Singleton instance
ai_tutor = AITutorEngine()
