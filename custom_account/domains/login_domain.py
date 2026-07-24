# class LoginDomain:
#     """Value object representing a login attempt.
    
#     Attributes:
#         username_or_email: str. The username or email of the user.
#         password: str. The plain-text password entered by the user.
#     """

#     def __init__(self, username_or_email: str, raw_password: str):
#         self.username_or_email = username_or_email
#         self.raw_password = raw_password
#         self.validate()

#     def validate(self) -> None:
#         if not self.username_or_email:
#             raise ValueError("Username or email is required.")
#         if not self.raw_password:
#             raise ValueError("Password is required.")
        
#     def to_dict(self) -> dict: # used internally in service layer, not for API response
#         return {
#             "username_or_email": self.username_or_email,
#             "raw_password": self.raw_password,
#         }
    
#     @classmethod
#     def from_dict(cls, data: dict) -> "LoginDomain": 
#         return cls(
#             username_or_email = data["username_or_email"],
#             raw_password = data["raw_password"],
#         )