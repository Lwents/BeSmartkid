from .dashboard_view import StudentDashboardView
from .courses_view import (
    StudentMyCoursesView,
    StudentCourseCatalogView,
    StudentCourseDetailView,
    StudentCoursePlayerView,
    StudentLearningPathView,
    StudentLearningPathManageView,
)
from .exams_view import (
    StudentExamsListView,
    StudentExamDetailView,
    StudentExamStartView,
    StudentExamSubmitView,
    StudentExamResultView,
    StudentExamRankingView,
    StudentCertificatesView,
)
from .account_view import (
    StudentProfileView,
    StudentChangePasswordView,
    StudentParentViewView,
)
from .lesson_question_view import (
    StudentLessonQuestionView,
    StudentLessonQuestionReplyView,
    StudentLessonQuestionReactionView,
    StudentLessonQuestionQuestionReactionView,
    StudentLessonQuestionReportView,
    StudentLessonQuestionAIAnswerView,
)

__all__ = [
    'StudentDashboardView',
    'StudentMyCoursesView',
    'StudentCourseCatalogView',
    'StudentCourseDetailView',
    'StudentCoursePlayerView',
    'StudentLearningPathView',
    'StudentLearningPathManageView',
    'StudentLessonQuestionView',
    'StudentLessonQuestionReplyView',
    'StudentLessonQuestionReactionView',
    'StudentLessonQuestionQuestionReactionView',
    'StudentLessonQuestionReportView',
    'StudentLessonQuestionAIAnswerView',
    'StudentExamsListView',
    'StudentExamDetailView',
    'StudentExamStartView',
    'StudentExamSubmitView',
    'StudentExamResultView',
    'StudentExamRankingView',
    'StudentCertificatesView',
    'StudentProfileView',
    'StudentChangePasswordView',
    'StudentParentViewView',
]
