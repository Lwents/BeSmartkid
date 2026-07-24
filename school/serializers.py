from rest_framework import serializers

from school.models import SchoolModel, ClassroomModel, MembershipModel, Enrollment, InvitationModel
from school.domains.school_domain import SchoolDomain
from school.domains.class_domain import ClassroomDomain
from school.domains.membership_domain import MembershipDomain
from school.domains.enrollment_domain import EnrollmentDomain
from school.domains.invitation_domain import InvitationDomain



class SchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolModel
        fields = ["id", "name", "code", "metadata"]
        read_only_fields = ["id"]

    def to_domain(self) -> SchoolDomain:
        return SchoolDomain.from_dict(self.validated_data)

    @staticmethod
    def from_domain(domain: SchoolDomain) -> dict:
        return domain.to_dict()


class ClassroomSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassroomModel
        fields = [
            "id", "school", "class_name", "grade", "teacher",
            "created_by", "created_on", "updated_on", "status"
        ]
        read_only_fields = ["id", "created_on", "updated_on"]

    def to_domain(self) -> ClassroomDomain:
        return ClassroomDomain.from_dict(self.validated_data)

    @staticmethod
    def from_domain(domain: ClassroomDomain) -> dict:
        return domain.to_dict()


class MembershipSerializer(serializers.ModelSerializer):
    class Meta:
        model = MembershipModel
        fields = ["classroom", "student", "role", "joined_on", "is_active"]
        read_only_fields = ["joined_on"]

    def to_domain(self) -> MembershipDomain:
        return MembershipDomain.from_dict(self.validated_data)

    @staticmethod
    def from_domain(domain: MembershipDomain) -> dict:
        return domain.to_dict()


class EnrollmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Enrollment
        fields = [
            "id", "classroom", "student", "role",
            "enrolled_at", "status"
        ]
        read_only_fields = ["id", "enrolled_at"]

    def to_domain(self) -> EnrollmentDomain:
        return EnrollmentDomain.from_dict(self.validated_data)

    @staticmethod
    def from_domain(domain: EnrollmentDomain) -> dict:
        return domain.to_dict()


class InvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvitationModel
        fields = [
            "id", "classroom", "invite_code", "email",
            "created_by", "created_on", "expires_on",
            "status", "usgaed_limit", "used_count"
        ]
        read_only_fields = ["id", "invite_code", "created_on", "used_count"]

    def to_domain(self) -> InvitationDomain:
        return InvitationDomain.from_dict(self.validated_data)

    @staticmethod
    def from_domain(domain: InvitationDomain) -> dict:
        return domain.to_dict()


# — UseCase: tạo lớp học —
class CreateClassroomSerializer(serializers.Serializer):
    school_id = serializers.UUIDField()
    class_name = serializers.CharField(max_length=100)
    grade = serializers.CharField(max_length=16, required=False, allow_null=True, allow_blank=True)
    teacher_id = serializers.IntegerField(required=False, allow_null=True)

    def to_domain(self) -> ClassroomDomain:
        data = {
            "id": None,
            "class_name": self.validated_data["class_name"],
            "description": None,
            "created_by": self.context.get("user_id"),
            "status": "active",
        }
        # optional fields
        data["grade"] = self.validated_data.get("grade")
        data["teacher"] = self.validated_data.get("teacher_id")
        return ClassroomDomain.from_dict(data)


# — UseCase: cập nhật lớp học (rename, đổi giáo viên, grade) —
class UpdateClassroomSerializer(serializers.Serializer):
    class_name = serializers.CharField(max_length=100, required=False)
    grade = serializers.CharField(max_length=16, required=False, allow_null=True, allow_blank=True)
    teacher_id = serializers.IntegerField(required=False, allow_null=True)
    status = serializers.ChoiceField(choices=ClassroomDomain.VALID_STATUSES, required=False)

    def apply_to_domain(self, domain: ClassroomDomain) -> ClassroomDomain:
        # domain: hiện tại của lớp học
        # Áp dụng các thay đổi nếu có
        if "class_name" in self.validated_data:
            domain.rename(self.validated_data["class_name"])
        if "status" in self.validated_data:
            new_status = self.validated_data["status"]
            # chuyển trạng thái
            if new_status == "archived":
                domain.archive()
            elif new_status == "deleted":
                domain.delete()
            elif new_status == "active":
                domain.activate()
        # teacher, grade là metadata phụ — domain có thể có setter
        if "grade" in self.validated_data:
            domain.grade = self.validated_data["grade"]
        if "teacher_id" in self.validated_data:
            domain.teacher = self.validated_data["teacher_id"]
        return domain


# — UseCase: mời học sinh vào lớp —
class InviteStudentSerializer(serializers.Serializer):
    classroom_id = serializers.UUIDField()
    email = serializers.EmailField()
    usage_limit = serializers.IntegerField(default=1)
    days_valid = serializers.IntegerField(default=7)

    def to_domain(self) -> InvitationDomain:
        data = {
            "id": None,
            "classroom_id": self.validated_data["classroom_id"],
            "invite_code": None,  # domain sẽ tạo code nội bộ
            "email": self.validated_data["email"],
            "created_by": self.context.get("user_id"),
            "expires_on": None,
            "status": InvitationDomain.STATUS_PENDING,
            "usage_limit": self.validated_data["usage_limit"],
            "used_count": 0,
        }
        # chúng ta có thể pass days_valid qua context để domain khởi tạo expires_on
        data["days_valid"] = self.validated_data.get("days_valid", 7)
        return InvitationDomain.from_dict(data)


# — UseCase: chấp nhận lời mời (join class qua mã) —
class AcceptInvitationSerializer(serializers.Serializer):
    invite_code = serializers.CharField()
    # student_id có thể lấy từ context / session, không truyền từ client

    def to_domain(self) -> InvitationDomain:
        # đây là domain representation của lời mời
        return InvitationDomain.from_dict(self.validated_data)


# — UseCase: liệt kê thành viên —
class ListMembersSerializer(serializers.Serializer):
    classroom_id = serializers.UUIDField()


# — UseCase: cập nhật vai trò thành viên —
class UpdateMemberRoleSerializer(serializers.Serializer):
    classroom_id = serializers.UUIDField()
    student_id = serializers.IntegerField()
    new_role = serializers.ChoiceField(choices=list(MembershipDomain.VALID_ROLES))

    def to_domain(self) -> MembershipDomain:
        d = {
            "classroom_id": self.validated_data["classroom_id"],
            "student_id": self.validated_data["student_id"],
            "role": self.validated_data["new_role"],
            "joined_on": None,
            "is_active": True,
        }
        return MembershipDomain.from_dict(d)


# — UseCase: học sinh rời lớp (drop) —
class DropEnrollmentSerializer(serializers.Serializer):
    classroom_id = serializers.UUIDField()
    student_id = serializers.IntegerField()

    def to_domain(self) -> EnrollmentDomain:
        enrollment_domain = {
            "id": None,
            "classroom_id": self.validated_data["classroom_id"],
            "student_id": self.validated_data["student_id"],
            "role": "student",
            "enrolled_at": None,
            "status": EnrollmentDomain.STATUS_DROPPED,
        }
        return EnrollmentDomain.from_dict(enrollment_domain)


# — UseCase: thu hồi lời mời —
class RevokeInvitationSerializer(serializers.Serializer):
    invite_code = serializers.CharField()

    def to_domain(self) -> InvitationDomain:
        return InvitationDomain.from_dict(self.validated_data)


