class ResetPasswordDomain:
    """Value object for resetting password via token."""

    def __init__(self, email: str, reset_token: str, new_password: str):
        self.email = email
        self.reset_token = reset_token
        self.new_password = new_password
        self.validate()

    def validate(self):
        if not self.email or "@" not in self.email:
            raise ValueError("Invalid email.")
        if not self.reset_token:
            raise ValueError("Reset token is required.")
        if not self.new_password or len(self.new_password) < 8:
            raise ValueError("Password must be at least 8 characters.")
