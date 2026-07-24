"""
Game API Views
- Student: List games, play game, submit score
- Teacher: Create, edit, delete games
- FE mapping: gameService (student) & teacherGameService (teacher)
"""
import os
import requests

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from django.db.models import Avg, Count, Max

from gamification.models import Game, GameSession
from student_api.permissions import IsStudent
from teacher_api.permissions import IsTeacher


# ============ STUDENT APIs ============

class StudentGameListView(APIView):
    """
    GET /api/student/games/
    List all published games for students
    """
    permission_classes = [IsAuthenticated, IsStudent]
    
    def get(self, request):
        games = Game.objects.filter(is_published=True)
        
        # Filter by type
        game_type = request.query_params.get('type')
        if game_type:
            games = games.filter(game_type=game_type)
        
        # Filter by subject
        subject = request.query_params.get('subject')
        if subject:
            games = games.filter(subject=subject)
        
        # Filter by grade
        grade = request.query_params.get('grade')
        if grade:
            games = games.filter(grade_level=int(grade))
        
        # Get user's best scores
        user_sessions = GameSession.objects.filter(
            player=request.user,
            completed=True
        ).values('game_id').annotate(
            best_score=Max('score'),
            play_count=Count('id')
        )
        user_scores = {str(s['game_id']): s for s in user_sessions}
        
        result = []
        for game in games:
            user_data = user_scores.get(str(game.id), {})
            result.append({
                'id': str(game.id),
                'title': game.title,
                'description': game.description,
                'game_type': game.game_type,
                'game_type_display': game.get_game_type_display(),
                'difficulty': game.difficulty,
                'difficulty_display': game.get_difficulty_display(),
                'subject': game.subject,
                'grade_level': game.grade_level,
                'question_count': len(game.questions),
                'play_count': game.play_count,
                'user_best_score': user_data.get('best_score'),
                'user_play_count': user_data.get('play_count', 0),
            })
        
        # Group by type
        grouped = {}
        for g in result:
            t = g['game_type']
            if t not in grouped:
                grouped[t] = {
                    'type': t,
                    'type_display': g['game_type_display'],
                    'games': []
                }
            grouped[t]['games'].append(g)
        
        return Response({
            'games': result,
            'grouped': list(grouped.values()),
            'total': len(result),
        })


class StudentGameDetailView(APIView):
    """
    GET /api/student/games/{id}/
    Get game details and questions for playing
    """
    permission_classes = [IsAuthenticated, IsStudent]
    
    def get(self, request, game_id):
        try:
            game = Game.objects.get(id=game_id, is_published=True)
        except Game.DoesNotExist:
            return Response({'detail': 'Game not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Get user's history
        user_sessions = GameSession.objects.filter(
            game=game,
            player=request.user,
            completed=True
        ).order_by('-score')[:5]
        
        return Response({
            'id': str(game.id),
            'title': game.title,
            'description': game.description,
            'game_type': game.game_type,
            'game_type_display': game.get_game_type_display(),
            'difficulty': game.difficulty,
            'questions': game.questions,
            'settings': game.settings,
            'question_count': len(game.questions),
            'user_history': [
                {
                    'score': s.score,
                    'max_score': s.max_score,
                    'time_spent': s.time_spent,
                    'completed_at': s.completed_at,
                }
                for s in user_sessions
            ],
        })


class StudentGameSessionView(APIView):
    """
    POST /api/student/games/{id}/start/
    Start a new game session
    
    POST /api/student/games/{id}/submit/
    Submit game results
    """
    permission_classes = [IsAuthenticated, IsStudent]
    
    def post(self, request, game_id, action):
        try:
            game = Game.objects.get(id=game_id, is_published=True)
        except Game.DoesNotExist:
            return Response({'detail': 'Game not found'}, status=status.HTTP_404_NOT_FOUND)
        
        if action == 'start':
            # Create new session
            session = GameSession.objects.create(
                game=game,
                player=request.user,
                max_score=len(game.questions) * 10,  # 10 points per question
            )
            
            # Increment play count
            game.play_count += 1
            game.save(update_fields=['play_count'])
            
            return Response({
                'session_id': str(session.id),
                'game_id': str(game.id),
                'questions': game.questions,
                'max_score': session.max_score,
            })
        
        elif action == 'submit':
            # Get or create session
            session_id = request.data.get('session_id')
            if session_id:
                try:
                    session = GameSession.objects.get(
                        id=session_id,
                        player=request.user,
                        completed=False
                    )
                except GameSession.DoesNotExist:
                    session = GameSession.objects.create(
                        game=game,
                        player=request.user,
                        max_score=len(game.questions) * 10,
                    )
            else:
                session = GameSession.objects.create(
                    game=game,
                    player=request.user,
                    max_score=len(game.questions) * 10,
                )
            
            # Update session
            session.score = request.data.get('score', 0)
            session.time_spent = request.data.get('time_spent', 0)
            session.answers = request.data.get('answers', [])
            session.completed = True
            # Đảm bảo completed_at được set đúng timezone để tính streak chính xác
            session.completed_at = timezone.now()
            session.save()
            
            # Calculate rank
            better_scores = GameSession.objects.filter(
                game=game,
                completed=True,
                score__gt=session.score
            ).count()
            total_players = GameSession.objects.filter(
                game=game,
                completed=True
            ).values('player').distinct().count()
            
            return Response({
                'session_id': str(session.id),
                'score': session.score,
                'max_score': session.max_score,
                'time_spent': session.time_spent,
                'percentage': round((session.score / session.max_score) * 100) if session.max_score > 0 else 0,
                'rank': better_scores + 1,
                'total_players': total_players,
            })
        
        return Response({'detail': 'Invalid action'}, status=status.HTTP_400_BAD_REQUEST)


class StudentGameLeaderboardView(APIView):
    """
    GET /api/student/games/{id}/leaderboard/
    Get game leaderboard
    """
    permission_classes = [IsAuthenticated, IsStudent]
    
    def get(self, request, game_id):
        try:
            game = Game.objects.get(id=game_id)
        except Game.DoesNotExist:
            return Response({'detail': 'Game not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Get top scores (best score per player)
        from django.db.models import OuterRef, Subquery
        
        best_sessions = GameSession.objects.filter(
            game=game,
            completed=True
        ).order_by('player', '-score').distinct('player')
        
        # Fallback: simple query
        top_scores = GameSession.objects.filter(
            game=game,
            completed=True
        ).select_related('player').order_by('-score')[:20]
        
        # Remove duplicates (keep best per player)
        seen_players = set()
        leaderboard = []
        for s in top_scores:
            if s.player_id not in seen_players:
                seen_players.add(s.player_id)
                leaderboard.append({
                    'rank': len(leaderboard) + 1,
                    'player_name': s.player.get_full_name() or s.player.email.split('@')[0],
                    'score': s.score,
                    'time_spent': s.time_spent,
                    'completed_at': s.completed_at,
                    'is_current_user': s.player_id == request.user.id,
                })
            if len(leaderboard) >= 10:
                break
        
        return Response({
            'game_id': str(game.id),
            'game_title': game.title,
            'leaderboard': leaderboard,
        })


# ============ TEACHER APIs ============

class TeacherGameListView(APIView):
    """
    GET /api/teacher/games/
    List teacher's games
    
    POST /api/teacher/games/
    Create new game
    """
    permission_classes = [IsAuthenticated, IsTeacher]
    
    def get(self, request):
        games = Game.objects.filter(created_by=request.user)
        
        result = []
        for game in games:
            sessions = GameSession.objects.filter(game=game, completed=True)
            result.append({
                'id': str(game.id),
                'title': game.title,
                'description': game.description,
                'game_type': game.game_type,
                'game_type_display': game.get_game_type_display(),
                'difficulty': game.difficulty,
                'subject': game.subject,
                'grade_level': game.grade_level,
                'question_count': len(game.questions),
                'is_published': game.is_published,
                'play_count': game.play_count,
                'avg_score': sessions.aggregate(avg=Avg('score'))['avg'] or 0,
                'created_at': game.created_at,
                'updated_at': game.updated_at,
            })
        
        return Response({
            'games': result,
            'total': len(result),
        })
    
    def post(self, request):
        data = request.data
        
        game = Game.objects.create(
            title=data.get('title', 'Trò chơi mới'),
            description=data.get('description', ''),
            game_type=data.get('game_type', 'quiz'),
            difficulty=data.get('difficulty', 'easy'),
            questions=data.get('questions', []),
            settings=data.get('settings', {}),
            subject=data.get('subject', ''),
            grade_level=data.get('grade_level'),
            is_published=data.get('is_published', False),
            created_by=request.user,
        )
        
        return Response({
            'id': str(game.id),
            'title': game.title,
            'message': 'Game created successfully',
        }, status=status.HTTP_201_CREATED)


class TeacherGameDetailView(APIView):
    """
    GET /api/teacher/games/{id}/
    Get game details
    
    PUT /api/teacher/games/{id}/
    Update game
    
    DELETE /api/teacher/games/{id}/
    Delete game
    """
    permission_classes = [IsAuthenticated, IsTeacher]
    
    def get(self, request, game_id):
        try:
            game = Game.objects.get(id=game_id, created_by=request.user)
        except Game.DoesNotExist:
            return Response({'detail': 'Game not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Get statistics
        sessions = GameSession.objects.filter(game=game, completed=True)
        
        return Response({
            'id': str(game.id),
            'title': game.title,
            'description': game.description,
            'game_type': game.game_type,
            'difficulty': game.difficulty,
            'questions': game.questions,
            'settings': game.settings,
            'subject': game.subject,
            'grade_level': game.grade_level,
            'is_published': game.is_published,
            'play_count': game.play_count,
            'stats': {
                'total_plays': sessions.count(),
                'unique_players': sessions.values('player').distinct().count(),
                'avg_score': sessions.aggregate(avg=Avg('score'))['avg'] or 0,
                'avg_time': sessions.aggregate(avg=Avg('time_spent'))['avg'] or 0,
            },
            'created_at': game.created_at,
            'updated_at': game.updated_at,
        })
    
    def put(self, request, game_id):
        try:
            game = Game.objects.get(id=game_id, created_by=request.user)
        except Game.DoesNotExist:
            return Response({'detail': 'Game not found'}, status=status.HTTP_404_NOT_FOUND)
        
        data = request.data
        
        if 'title' in data:
            game.title = data['title']
        if 'description' in data:
            game.description = data['description']
        if 'game_type' in data:
            game.game_type = data['game_type']
        if 'difficulty' in data:
            game.difficulty = data['difficulty']
        if 'questions' in data:
            game.questions = data['questions']
        if 'settings' in data:
            game.settings = data['settings']
        if 'subject' in data:
            game.subject = data['subject']
        if 'grade_level' in data:
            game.grade_level = data['grade_level']
        if 'is_published' in data:
            game.is_published = data['is_published']
        
        game.save()
        
        return Response({
            'id': str(game.id),
            'title': game.title,
            'message': 'Game updated successfully',
        })
    
    def delete(self, request, game_id):
        try:
            game = Game.objects.get(id=game_id, created_by=request.user)
        except Game.DoesNotExist:
            return Response({'detail': 'Game not found'}, status=status.HTTP_404_NOT_FOUND)
        
        game.delete()
        
        return Response({'message': 'Game deleted successfully'})


class TeacherGameStatsView(APIView):
    """
    GET /api/teacher/games/{id}/stats/
    Get detailed game statistics
    """
    permission_classes = [IsAuthenticated, IsTeacher]
    
    def get(self, request, game_id):
        try:
            game = Game.objects.get(id=game_id, created_by=request.user)
        except Game.DoesNotExist:
            return Response({'detail': 'Game not found'}, status=status.HTTP_404_NOT_FOUND)
        
        sessions = GameSession.objects.filter(game=game, completed=True).select_related('player')
        
        # Recent plays
        recent = sessions.order_by('-completed_at')[:20]
        
        # Score distribution
        score_ranges = {
            '0-20': 0,
            '21-40': 0,
            '41-60': 0,
            '61-80': 0,
            '81-100': 0,
        }
        for s in sessions:
            pct = (s.score / s.max_score * 100) if s.max_score > 0 else 0
            if pct <= 20:
                score_ranges['0-20'] += 1
            elif pct <= 40:
                score_ranges['21-40'] += 1
            elif pct <= 60:
                score_ranges['41-60'] += 1
            elif pct <= 80:
                score_ranges['61-80'] += 1
            else:
                score_ranges['81-100'] += 1
        
        return Response({
            'game_id': str(game.id),
            'game_title': game.title,
            'total_plays': sessions.count(),
            'unique_players': sessions.values('player').distinct().count(),
            'avg_score': sessions.aggregate(avg=Avg('score'))['avg'] or 0,
            'avg_time': sessions.aggregate(avg=Avg('time_spent'))['avg'] or 0,
            'score_distribution': score_ranges,
            'recent_plays': [
                {
                    'player_name': s.player.get_full_name() or s.player.email.split('@')[0],
                    'score': s.score,
                    'max_score': s.max_score,
                    'time_spent': s.time_spent,
                    'completed_at': s.completed_at,
                }
                for s in recent
            ],
        })


class TeacherGameAIGenerateView(APIView):
    """
    POST /api/teacher/games/ai-generate/
    Generate game questions using AI
    """
    permission_classes = [IsAuthenticated, IsTeacher]
    
    def post(self, request):
        data = request.data
        game_type = data.get('game_type', 'quiz')
        title = data.get('title', '')
        subject = data.get('subject', '')
        grade_level = data.get('grade_level', 1)
        count = min(int(data.get('count', 5)), 15)
        hint = data.get('hint', '')
        
        # Build prompt based on game type
        if game_type == 'quiz':
            prompt = self._build_quiz_prompt(title, subject, grade_level, count, hint)
        elif game_type == 'word_match':
            prompt = self._build_word_match_prompt(title, subject, grade_level, count, hint)
        else:
            prompt = self._build_quiz_prompt(title, subject, grade_level, count, hint)
        
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            return Response({"detail": "AI chưa được cấu hình"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        model = os.getenv("OPENROUTER_MODEL") or os.getenv("DEEPSEEK_MODEL") or "openai/gpt-4o"
        ai_response = self._call_openrouter_api(api_key, model, prompt)
        
        if ai_response.get("error"):
            return Response({"detail": ai_response["error"]}, status=status.HTTP_502_BAD_GATEWAY)
        
        return Response({
            "text": ai_response.get("text", ""),
            "model": ai_response.get("model", model),
            "game_type": game_type,
        })
    
    def _build_quiz_prompt(self, title, subject, grade_level, count, hint):
        return f"""Bạn là trợ lý tạo trò chơi giáo dục cho học sinh tiểu học lớp {grade_level}.

TẠO {count} CÂU HỎI TRẮC NGHIỆM cho trò chơi "{title or 'Trắc nghiệm vui'}".
Môn học: {subject or 'Tổng hợp'}
Yêu cầu thêm: {hint or 'Không có'}

QUY TẮC:
1. Câu hỏi phù hợp với học sinh tiểu học (6-11 tuổi)
2. Ngôn ngữ đơn giản, dễ hiểu
3. Mỗi câu có 4 đáp án, chỉ 1 đáp án đúng
4. Câu hỏi thú vị, hấp dẫn

Trả về JSON thuần (KHÔNG có markdown):
{{
  "questions": [
    {{"id": 1, "question": "Câu hỏi?", "options": ["A", "B", "C", "D"], "correct": 0}},
    {{"id": 2, "question": "Câu hỏi?", "options": ["A", "B", "C", "D"], "correct": 1}}
  ]
}}

correct là index của đáp án đúng (0-3)."""

    def _build_word_match_prompt(self, title, subject, grade_level, count, hint):
        return f"""Bạn là trợ lý tạo trò chơi ghép từ cho học sinh tiểu học lớp {grade_level}.

TẠO {count} CẶP TỪ GHÉP cho trò chơi "{title or 'Ghép từ vui'}".
Môn học: {subject or 'Tiếng Anh'}
Yêu cầu thêm: {hint or 'Không có'}

QUY TẮC:
1. Từ vựng phù hợp với học sinh tiểu học
2. Cặp từ có nghĩa liên quan (VD: từ vựng - nghĩa, Anh - Việt)
3. Đơn giản, dễ nhớ

Trả về JSON thuần (KHÔNG có markdown):
{{
  "questions": [
    {{"left": "Apple", "right": "Quả táo"}},
    {{"left": "Dog", "right": "Con chó"}}
  ]
}}"""

    def _call_openrouter_api(self, api_key, model, prompt):
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 2048,
                },
                timeout=60,
            )
            if resp.status_code == 200:
                data = resp.json()
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if text and text.strip():
                    return {"text": text.strip(), "model": model}
            return {"error": f"OpenRouter error {resp.status_code}"}
        except Exception as e:
            return {"error": str(e)}
