import pytest
from django.contrib.auth.tokens import PasswordResetTokenGenerator


@pytest.mark.django_db
def test_password_reset_page_completes_flow(client, user_factory):
    user = user_factory(email="reset-page@example.com")
    token = PasswordResetTokenGenerator().make_token(user)
    url = f"/auth/reset-password?email={user.email}&token={token}"

    response = client.get(url)
    assert response.status_code == 200
    assert "Tạo mật khẩu mới" in response.content.decode()

    response = client.post(
        "/auth/reset-password",
        {
            "email": user.email,
            "token": token,
            "new_password": "UpdatedPass42",
            "confirm_password": "UpdatedPass42",
        },
    )
    assert response.status_code == 200
    assert "Đổi mật khẩu thành công" in response.content.decode()

    user.refresh_from_db()
    assert user.check_password("UpdatedPass42")

    response = client.get(url)
    assert response.status_code == 400
    assert "Liên kết không còn hiệu lực" in response.content.decode()


@pytest.mark.django_db
def test_password_reset_page_rejects_invalid_or_mismatched_data(client, user_factory):
    user = user_factory(email="reset-errors@example.com")
    token = PasswordResetTokenGenerator().make_token(user)

    response = client.get(
        f"/auth/reset-password?email={user.email}&token=invalid-token"
    )
    assert response.status_code == 400

    response = client.post(
        "/auth/reset-password",
        {
            "email": user.email,
            "token": token,
            "new_password": "UpdatedPass42",
            "confirm_password": "DifferentPass42",
        },
    )
    assert response.status_code == 400
    assert "Hai mật khẩu chưa giống nhau" in response.content.decode()
