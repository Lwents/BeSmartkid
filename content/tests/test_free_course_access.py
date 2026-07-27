import pytest

from content.models import Course, Enrollment, Subject
from custom_account.models import UserModel


@pytest.mark.django_db
def test_student_enrolls_in_published_course_without_purchase(api_client):
    student = UserModel.objects.create_user(
        username='studentfree',
        email='studentfree@example.com',
        password='password123',
        role='student',
    )
    api_client.force_authenticate(student)
    subject = Subject.objects.create(title='Toán', slug='toan-free-course')
    course = Course.objects.create(
        subject=subject,
        title='Khóa học miễn phí',
        grade='1',
        published=True,
    )

    response = api_client.post(f'/api/content/courses/{course.id}/enroll/')
    detail = api_client.get(f'/api/content/courses/{course.id}/')

    assert response.status_code == 200
    assert Enrollment.objects.filter(course=course, student=student).exists()
    assert detail.status_code == 200
    assert 'price' not in detail.data
    assert 'price' not in {field.name for field in Course._meta.fields}


@pytest.mark.django_db
def test_course_price_and_removed_purchase_routes_are_rejected(api_client):
    teacher = UserModel.objects.create_user(
        username='teacherfree',
        email='teacherfree@example.com',
        password='password123',
        role='instructor',
    )
    api_client.force_authenticate(teacher)

    create_response = api_client.post(
        '/api/content/courses/',
        {'title': 'Khóa học miễn phí', 'price': 100000},
        format='json',
    )

    assert create_response.status_code == 400
    assert 'không bán khóa học' in str(create_response.data).lower()
    assert api_client.get('/api/payments/').status_code == 404
    assert api_client.get('/api/student/payments/history/').status_code == 404
    assert api_client.get('/api/admin/transactions/').status_code == 404
    assert api_client.get('/api/admin/reports/revenue/').status_code == 404
