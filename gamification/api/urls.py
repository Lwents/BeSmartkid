from django.urls import path
from . import views

# Student URLs - to be included in student_api/urls.py
student_urlpatterns = [
    path('games/', views.StudentGameListView.as_view(), name='student-game-list'),
    path('games/<uuid:game_id>/', views.StudentGameDetailView.as_view(), name='student-game-detail'),
    path('games/<uuid:game_id>/<str:action>/', views.StudentGameSessionView.as_view(), name='student-game-session'),
    path('games/<uuid:game_id>/leaderboard/', views.StudentGameLeaderboardView.as_view(), name='student-game-leaderboard'),
]

# Teacher URLs - to be included in teacher_api/urls.py
teacher_urlpatterns = [
    path('games/', views.TeacherGameListView.as_view(), name='teacher-game-list'),
    path('games/<uuid:game_id>/', views.TeacherGameDetailView.as_view(), name='teacher-game-detail'),
    path('games/<uuid:game_id>/stats/', views.TeacherGameStatsView.as_view(), name='teacher-game-stats'),
]
