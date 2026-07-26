"""Dịch thông báo lỗi sang tiếng Việt trước khi trả về cho ứng dụng.

Vì sao cần: nhiều view trả thẳng chuỗi tiếng Anh ("Old password is incorrect"),
và một số thông báo của thư viện không có bản dịch. Học sinh tiểu học và phụ huynh
đọc không hiểu, nên toàn bộ lỗi đi ra ngoài đều được đổi sang tiếng Việt ở một chỗ
duy nhất thay vì sửa rải rác trong từng view.
"""
import re

# Khớp chính xác (không phân biệt hoa thường, bỏ dấu chấm cuối).
TU_DIEN = {
    # --- Tài khoản, đăng nhập, mật khẩu ---
    "old password is incorrect": "Mật khẩu hiện tại không đúng",
    "old password is required": "Vui lòng nhập mật khẩu hiện tại",
    "oldpassword and newpassword are required":
        "Vui lòng nhập mật khẩu hiện tại và mật khẩu mới",
    "password is required": "Vui lòng nhập mật khẩu",
    "password must be at least 8 characters": "Mật khẩu phải có ít nhất 8 ký tự",
    "new password must be at least 8 characters": "Mật khẩu mới phải có ít nhất 8 ký tự",
    "new password must be different from old password":
        "Mật khẩu mới phải khác mật khẩu hiện tại",
    "password has been reset successfully": "Đã đặt lại mật khẩu thành công",
    "password has been reset with the new password": "Đã đặt lại mật khẩu thành công",
    "no active account found with the given credentials":
        "Email hoặc mật khẩu không đúng",
    "invalid or expired token": "Mã xác thực không đúng hoặc đã hết hạn",
    "reset token is required": "Vui lòng nhập mã đặt lại mật khẩu",
    "authentication required": "Bạn cần đăng nhập để tiếp tục",
    "authorization header must contain two space-delimited values":
        "Phiên đăng nhập không hợp lệ, vui lòng đăng nhập lại",
    "token contained no recognizable user identification":
        "Phiên đăng nhập không hợp lệ, vui lòng đăng nhập lại",
    "user not found or inactive": "Tài khoản không tồn tại hoặc đã bị khóa",
    "this account is inactive": "Tài khoản đã bị khóa",
    "account is locked": "Tài khoản đang tạm bị khóa, vui lòng thử lại sau",
    "too many failed login attempts":
        "Bạn đã nhập sai quá nhiều lần, vui lòng thử lại sau",
    "email already exists": "Email này đã được dùng cho tài khoản khác",
    "email already taken": "Email này đã được dùng cho tài khoản khác",
    "phone already taken": "Số điện thoại này đã được dùng cho tài khoản khác",
    "username already taken": "Tên đăng nhập này đã có người dùng",
    "email is required": "Vui lòng nhập email",
    "valid email is required": "Email không đúng định dạng",
    "username is required": "Vui lòng nhập tên đăng nhập",
    "username or email is required": "Vui lòng nhập tên đăng nhập hoặc email",
    "the email must be set": "Vui lòng nhập email",
    "if the email exists, a reset link has been sent":
        "Nếu email tồn tại, chúng tôi đã gửi hướng dẫn đặt lại mật khẩu",
    "user not found": "Không tìm thấy người dùng",
    "profile not found": "Không tìm thấy hồ sơ",
    "profile already exists": "Hồ sơ đã tồn tại",
    "profile already exists for this user": "Người dùng này đã có hồ sơ",
    "date of birth cannot be in the future": "Ngày sinh không thể ở tương lai",
    "cannot delete the last admin user":
        "Không thể xóa tài khoản quản trị cuối cùng",
    "cannot delete profile with active subscription":
        "Không thể xóa hồ sơ khi còn gói cước đang hiệu lực",
    "redirect url is not allowed": "Địa chỉ chuyển tiếp không được phép",

    # --- Quyền truy cập ---
    "permission denied": "Bạn không có quyền thực hiện việc này",
    "you do not have permission to perform this action":
        "Bạn không có quyền thực hiện việc này",
    "not allowed to submit answer for this attempt":
        "Bạn không được phép nộp bài cho lượt làm này",
    "you can only regenerate your own learning paths":
        "Bạn chỉ có thể tạo lại lộ trình học của chính mình",

    # --- Khóa học, chương, bài học ---
    "course not found": "Không tìm thấy khóa học",
    "course id required": "Thiếu mã khóa học",
    "course title is required": "Vui lòng nhập tên khóa học",
    "course title required": "Vui lòng nhập tên khóa học",
    "course title cannot be empty": "Tên khóa học không được để trống",
    "module not found": "Không tìm thấy chương",
    "module not found in course": "Chương này không thuộc khóa học",
    "module id required": "Thiếu mã chương",
    "module title required": "Vui lòng nhập tên chương",
    "module title cannot be empty": "Tên chương không được để trống",
    "module positions required": "Thiếu thứ tự các chương",
    "lesson not found": "Không tìm thấy bài học",
    "lesson not found in module": "Bài học này không thuộc chương",
    "lesson id required": "Thiếu mã bài học",
    "lesson title required": "Vui lòng nhập tên bài học",
    "lesson title cannot be empty": "Tên bài học không được để trống",
    "lesson positions required": "Thiếu thứ tự các bài học",
    "no lessons in this course": "Khóa học này chưa có bài học",
    "no published lessons in this course":
        "Khóa học này chưa có bài học nào được xuất bản",
    "cannot publish an empty lesson version": "Không thể xuất bản bài học trống",
    "could not publish": "Không thể xuất bản",
    "cannot enroll in unpublished course":
        "Không thể ghi danh vào khóa học chưa xuất bản",
    "this course is not available yet": "Khóa học này chưa mở",
    "you are not enrolled in this course": "Bạn chưa ghi danh khóa học này",
    "student is not enrolled in this course": "Học sinh chưa ghi danh khóa học này",
    "student is not enrolled in any of your courses":
        "Học sinh chưa ghi danh khóa học nào của bạn",
    "student not found": "Không tìm thấy học sinh",
    "owner does not exist": "Không tìm thấy chủ sở hữu",
    "owner id required": "Thiếu mã chủ sở hữu",
    "subject title required": "Vui lòng nhập tên môn học",
    "subject title cannot be empty": "Tên môn học không được để trống",
    "subject slug required and cannot contain spaces":
        "Đường dẫn môn học là bắt buộc và không được chứa dấu cách",
    "subject slug cannot be empty or contain spaces":
        "Đường dẫn môn học không được để trống hoặc chứa dấu cách",
    "slug must be at least 2 chars and contain no spaces":
        "Đường dẫn phải có ít nhất 2 ký tự và không chứa dấu cách",

    # --- Bài tập, bài kiểm tra ---
    "exercise not found": "Không tìm thấy bài tập",
    "exam not found": "Không tìm thấy bài kiểm tra",
    "attempt not found": "Không tìm thấy lượt làm bài",
    "attempt or answer not found": "Không tìm thấy lượt làm bài hoặc câu trả lời",
    "attempt already finished": "Lượt làm bài này đã kết thúc",
    "answer not found for grading": "Không tìm thấy câu trả lời để chấm điểm",
    "cannot add answer to an attempt that is not in progress":
        "Không thể trả lời vì lượt làm bài đã kết thúc",
    "exercise has closed. the deadline has passed":
        "Bài tập đã đóng vì hết thời hạn làm bài",
    "exercise is not published yet": "Bài tập chưa được xuất bản",
    "exercise should contain at least one question":
        "Bài tập cần có ít nhất một câu hỏi",
    "quiz must contain at least one question":
        "Bài kiểm tra cần có ít nhất một câu hỏi",
    "exercise title is required": "Vui lòng nhập tên bài tập",
    "no exercises to publish or close": "Không có bài tập nào để xuất bản hoặc đóng",
    "answer doesn't match accepted responses": "Câu trả lời chưa đúng",
    "text is required": "Vui lòng nhập nội dung",
    "text block must contain non-empty 'text'": "Khối văn bản không được để trống",
    "text block too long": "Nội dung văn bản quá dài",

    # --- Thông báo, hỏi đáp, khác ---
    "notification not found": "Không tìm thấy thông báo",
    "transaction not found": "Không tìm thấy giao dịch",
    "subscription plan not found": "Không tìm thấy gói cước",
    "learning path not found": "Không tìm thấy lộ trình học",
    "log not found": "Không tìm thấy bản ghi",
    "file not found": "Không tìm thấy tệp",
    "not found": "Không tìm thấy dữ liệu",
    "not found or cannot update": "Không tìm thấy hoặc không thể cập nhật",
    "reaction feature not available. please run migrations":
        "Tính năng bày tỏ cảm xúc chưa sẵn sàng",
    "enroll feature not implemented": "Tính năng ghi danh chưa hoàn thiện",
    "unenroll feature not implemented": "Tính năng hủy ghi danh chưa hoàn thiện",
    "invalid report type": "Loại báo cáo không hợp lệ",
    "invalid action": "Hành động không hợp lệ",
    "an unexpected error occurred": "Đã xảy ra lỗi, vui lòng thử lại",
    "internal server error": "Hệ thống đang gặp sự cố, vui lòng thử lại sau",
}

# Tên model trong thông báo "No X matches the given query." của Django.
TEN_MODEL = {
    "course": "khóa học", "lesson": "bài học", "module": "chương",
    "exercise": "bài tập", "question": "câu hỏi", "choice": "phương án",
    "exerciseattempt": "lượt làm bài", "enrollment": "lượt ghi danh",
    "notification": "thông báo", "usermodel": "người dùng", "user": "người dùng",
    "profile": "hồ sơ", "subject": "môn học", "lessonquestion": "câu hỏi bài học",
    "lessonprogress": "tiến độ bài học", "teacherfeedback": "nhận xét",
}


def _khong_tim_thay(m):
    ten = TEN_MODEL.get(m.group(1).replace(" ", "").lower())
    return f"Không tìm thấy {ten}" if ten else "Không tìm thấy dữ liệu yêu cầu"


# Tên trường trong các thông báo "<field> is required" rải khắp backend.
TEN_TRUONG = {
    "course_id": "mã khóa học", "lesson_id": "mã bài học",
    "module_id": "mã chương", "exercise_id": "mã bài tập",
    "question_id": "mã câu hỏi", "attempt_id": "mã lượt làm bài",
    "user_id": "mã người dùng", "student_id": "mã học sinh",
    "classroom_id": "mã lớp học", "invite_code": "mã mời",
    "email": "email", "username": "tên đăng nhập", "password": "mật khẩu",
    "old_password": "mật khẩu hiện tại", "oldpassword": "mật khẩu hiện tại",
    "new_password": "mật khẩu mới", "newpassword": "mật khẩu mới",
    "message": "nội dung tin nhắn", "text": "nội dung", "content": "nội dung",
    "title": "tiêu đề", "score": "điểm", "token": "mã xác thực",
    "phone": "số điện thoại", "role": "vai trò", "grade": "lớp",
}


def _thieu_truong(m):
    """Ghép câu "Vui lòng nhập ..." từ một hoặc nhiều tên trường."""
    tho = re.split(r"\s*(?:,|and|&)\s*", m.group(1))
    ten = [TEN_TRUONG.get(t.strip(), t.strip()) for t in tho if t.strip()]
    if not ten:
        return "Thiếu thông tin bắt buộc"
    return "Vui lòng nhập " + " và ".join(ten)


# Thông báo có tham số → dùng biểu thức chính quy.
QUY_TAC = [
    (r"^no ([a-z ]+) matches the given query\.?$", _khong_tim_thay),
    # "lesson_id is required", "oldPassword and newPassword are required"
    (r"^([a-z_]+(?:\s*(?:,|and|&)\s*[a-z_]+)*)\s+(?:is|are)\s+required\.?$",
     _thieu_truong),
    (r"^ensure this field has no more than (\d+) characters?\.?$",
     r"Nội dung này không được dài hơn \1 ký tự"),
    (r"^ensure this field has at least (\d+) characters?\.?$",
     r"Nội dung này phải có ít nhất \1 ký tự"),
    (r"^ensure this value is less than or equal to (\d+)\.?$",
     r"Giá trị phải nhỏ hơn hoặc bằng \1"),
    (r"^ensure this value is greater than or equal to (\d+)\.?$",
     r"Giá trị phải lớn hơn hoặc bằng \1"),
    (r"^this field is required\.?$", "Vui lòng nhập thông tin này"),
    (r"^this field may not be blank\.?$", "Vui lòng nhập thông tin này"),
    (r"^this field may not be null\.?$", "Vui lòng nhập thông tin này"),
    (r"^enter a valid email address\.?$", "Email không đúng định dạng"),
    (r"^a valid integer is required\.?$", "Vui lòng nhập một số nguyên"),
    (r"^a valid number is required\.?$", "Vui lòng nhập một số"),
    (r"^\"?.+\"? is not a valid choice\.?$", "Giá trị chọn không hợp lệ"),
    (r"^role must be one of.*$",
     "Vai trò phải là học sinh, giáo viên hoặc quản trị"),
    (r"^(score|weight) must be between 0 and 1\.?$",
     "Giá trị phải nằm trong khoảng 0 đến 1"),
    (r"^authentication credentials were not provided\.?$",
     "Bạn cần đăng nhập để tiếp tục"),
    (r"^given token not valid for any token type\.?$",
     "Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại"),
    (r"^token is invalid or expired\.?$",
     "Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại"),
]


def dich(text):
    """Đổi một câu tiếng Anh sang tiếng Việt; không khớp thì trả lại nguyên văn."""
    if not isinstance(text, str) or not text.strip():
        return text
    khoa = text.strip().rstrip(".").lower()
    if khoa in TU_DIEN:
        return TU_DIEN[khoa]
    thap = text.strip().lower()
    for mau, thay in QUY_TAC:
        khop = re.match(mau, thap)
        if khop:
            # thay có thể là chuỗi thế chỗ, hoặc hàm nhận match (vd tra tên model)
            return thay(khop) if callable(thay) else re.sub(mau, thay, thap)
    return text


def dich_payload(data):
    """Dịch đệ quy mọi chuỗi trong phần thân lỗi (dict / list / str)."""
    if isinstance(data, str):
        return dich(data)
    if isinstance(data, dict):
        return {k: dich_payload(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [dich_payload(v) for v in data]
    return data
