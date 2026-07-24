class RegisterDomain:
    """Value object for user registration input."""

    def __init__(self, username: str, email: str, password: str, role: str = "student"):
        self.username = username
        self.email = email
        self.password = password
        self.role = role
        self.validate()

    def validate(self):
        if not self.username:
            raise ValueError("Username is required.")
        if not self.email or "@" not in self.email:
            raise ValueError("Valid email is required.")
        if not self.password or len(self.password) < 8:
            raise ValueError("Password must be at least 8 characters.")
        if self.role not in ["student", "parent", "instructor", "admin"]:
            raise ValueError("Invalid role.")

    def to_dict(self):
        return {
            "username": self.username,
            "email": self.email,
            "password": self.password,
            "role": self.role,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RegisterDomain":
        return cls(
            username=data["username"],
            email=data["email"],
            password=data["password"],
            role=data.get("role", "student"),
        )
