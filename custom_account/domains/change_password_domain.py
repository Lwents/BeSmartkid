class ChangePasswordDomain:
    """Value object for password change attempt."""

    def __init__(self, user_id: int, old_password: str, new_password: str):
        self.user_id = user_id
        self.old_password = old_password
        self.new_password = new_password
        self.validate()

    def validate(self):
        if not self.old_password:
            raise ValueError("Old password is required.")
        if not self.new_password or len(self.new_password) < 8:
            raise ValueError("New password must be at least 8 characters.")
        if self.old_password == self.new_password:
            raise ValueError("New password must be different from old password.")

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "old_password": self.old_password,
            "new_password": self.new_password,
        }
