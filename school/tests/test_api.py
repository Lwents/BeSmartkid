# school/tests/test_api.py
import uuid
from datetime import timedelta
from django.urls import reverse
from django.utils import timezone
import pytest
from rest_framework import status

from school.models import SchoolModel, ClassroomModel, MembershipModel, Enrollment, InvitationModel



@pytest.mark.django_db
def test_school_crud_flow(api_client, user_factory):
    user = user_factory(username="api_school_admin")
    api_client.force_authenticate(user=user)

    # CREATE
    url = reverse("school-list-create")
    payload = {"name": "API School", "code": "API-1", "metadata": {"city": "HCM"}}
    resp = api_client.post(url, payload, format="json")
    assert resp.status_code == status.HTTP_201_CREATED
    school_id = resp.data["id"]

    # GET detail
    url_detail = reverse("school-detail", kwargs={"pk": school_id})
    resp2 = api_client.get(url_detail)
    assert resp2.status_code == status.HTTP_200_OK
    assert resp2.data["name"] == "API School"

    # UPDATE
    payload_update = {"name": "API School Updated", "code": "API-1"}
    resp3 = api_client.put(url_detail, payload_update, format="json")
    assert resp3.status_code == status.HTTP_200_OK
    assert resp3.data["name"] == "API School Updated"

    # DELETE (archive)
    resp4 = api_client.delete(url_detail)
    assert resp4.status_code in (status.HTTP_204_NO_CONTENT, status.HTTP_200_OK)
    s = SchoolModel.objects.get(pk=school_id)
    # soft delete may set metadata.deleted True
    assert "deleted" in s.metadata or hasattr(s, "is_active") is False


@pytest.mark.django_db
def test_classroom_api_flow(api_client, user_factory, school_factory):
    teacher = user_factory(username="api_teacher")
    api_client.force_authenticate(user=teacher)
    school = school_factory(name="SchoolForClass")

    # create classroom
    url = reverse("classroom-list-create", kwargs={"school_id": school.id})
    payload = {"class_name": "APIC1", "grade": "2", "teacher": teacher.id}
    resp = api_client.post(url, payload, format="json")
    assert resp.status_code == status.HTTP_201_CREATED
    class_id = resp.data["id"]

    # get classroom
    url_detail = reverse("classroom-detail", kwargs={"pk": class_id})
    resp2 = api_client.get(url_detail)
    assert resp2.status_code == status.HTTP_200_OK
    assert resp2.data["class_name"] == "APIC1"

    # update
    payload_upd = {"class_name": "APIC1-new"}
    resp3 = api_client.put(url_detail, payload_upd, format="json")
    assert resp3.status_code == status.HTTP_200_OK
    assert resp3.data["class_name"] == "APIC1-new"

    # archive
    resp4 = api_client.delete(url_detail)
    assert resp4.status_code in (status.HTTP_204_NO_CONTENT, status.HTTP_200_OK)
    cls = ClassroomModel.objects.get(pk=class_id)
    assert cls.status == "archived"


@pytest.mark.django_db
def test_membership_api_flow(api_client, user_factory, classroom_factory):
    teacher = user_factory(username="mem_teacher")
    student = user_factory(username="mem_student")
    classroom = classroom_factory(teacher=teacher, created_by=teacher.id)
    api_client.force_authenticate(user=teacher)

    # add member
    url = reverse("membership-list-create", kwargs={"classroom_id": classroom.id})
    resp = api_client.post(url, {"student": student.id, "role": "student"}, format="json")
    assert resp.status_code == status.HTTP_201_CREATED
    assert MembershipModel.objects.filter(classroom_id=classroom.id, student_id=student.id).exists()

    # list members
    resp2 = api_client.get(url)
    assert resp2.status_code == status.HTTP_200_OK
    assert any(m["student_id"] == str(student.id) or m.get("student") == student.id for m in resp2.data)

    # update member role
    url_detail = reverse("membership-detail", kwargs={"classroom_id": classroom.id, "user_id": student.id})
    resp3 = api_client.put(url_detail, {"role": "instructor"}, format="json")
    assert resp3.status_code in (status.HTTP_200_OK, status.HTTP_204_NO_CONTENT)
    m = MembershipModel.objects.get(classroom_id=classroom.id, student_id=student.id)
    assert m.role == "instructor"

    # remove member
    resp4 = api_client.delete(url_detail)
    assert resp4.status_code in (status.HTTP_204_NO_CONTENT, status.HTTP_200_OK)
    assert not MembershipModel.objects.filter(classroom_id=classroom.id, student_id=student.id).exists()


@pytest.mark.django_db
def test_enrollment_api_flow(api_client, user_factory, classroom_factory):
    teacher = user_factory(username="en_teacher")
    student = user_factory(username="en_student")
    classroom = classroom_factory(teacher=teacher, created_by=teacher.id)
    api_client.force_authenticate(user=teacher)

    # enroll student
    url = reverse("enrollment-list-create", kwargs={"classroom_id": classroom.id})
    resp = api_client.post(url, {"student": student.id, "role": "student"}, format="json")
    assert resp.status_code == status.HTTP_201_CREATED
    # list enrollments
    resp2 = api_client.get(url)
    assert resp2.status_code == status.HTTP_200_OK
    assert any(e.get("student_id") == str(student.id) or e.get("student") == student.id for e in resp2.data)

    # drop enrollment
    en = Enrollment.objects.filter(classroom_id=classroom.id, student_id=student.id).first()
    assert en is not None
    url_drop = reverse("enrollment-detail", kwargs={"pk": en.id})
    # authenticate as student and drop
    api_client.force_authenticate(user=student)
    resp3 = api_client.delete(url_drop)
    assert resp3.status_code in (status.HTTP_204_NO_CONTENT, status.HTTP_200_OK)
    en.refresh_from_db()
    assert en.status == "dropped"


@pytest.mark.django_db
def test_invitation_api_flow(api_client, user_factory, classroom_factory):
    teacher = user_factory(username="inv_teacher")
    student = user_factory(username="inv_student")
    classroom = classroom_factory(teacher=teacher, created_by=teacher.id)
    api_client.force_authenticate(user=teacher)

    # create invitation
    url = reverse("invitation-list-create", kwargs={"classroom_id": classroom.id})
    resp = api_client.post(url, {"email": student.email, "usage_limit": 1, "days_valid": 7}, format="json")
    assert resp.status_code == status.HTTP_201_CREATED
    invite_id = resp.data.get("id") or resp.data.get("invite_code")

    # list invitations
    resp2 = api_client.get(url)
    assert resp2.status_code == status.HTTP_200_OK
    assert any(inv.get("email") == student.email or inv.get("email") == str(student.email) for inv in resp2.data)

    # accept invitation (as student)
    # find the created invite model in DB (invite_code available)
    inv_row = InvitationModel.objects.filter(classroom_id=classroom.id, email=student.email).first()
    assert inv_row is not None
    url_accept = reverse("invitation-accept", kwargs={"pk": inv_row.id})
    api_client.force_authenticate(user=student)
    resp3 = api_client.post(url_accept, {}, format="json")
    assert resp3.status_code in (status.HTTP_200_OK, status.HTTP_201_CREATED)
    # enrollment must exist
    assert Enrollment.objects.filter(classroom_id=classroom.id, student_id=student.id).exists()

    # revoke invitation (teacher)
    api_client.force_authenticate(user=teacher)
    inv_row2 = InvitationModel.objects.create(
        classroom=classroom,
        invite_code=str(uuid.uuid4()),
        email="someone@example.com",
        created_by=teacher.id,
        created_on=timezone.now(),
        expires_on=timezone.now() + timedelta(days=7),
        status="pending",
        usgaed_limit=1,
        used_count=0,
    )
    url_revoke = reverse("invitation-revoke", kwargs={"pk": inv_row2.id})
    resp4 = api_client.post(url_revoke, {}, format="json")
    assert resp4.status_code in (status.HTTP_204_NO_CONTENT, status.HTTP_200_OK)
    inv_row2.refresh_from_db()
    assert inv_row2.status == "expired"
