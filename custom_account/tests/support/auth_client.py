from dataclasses import dataclass
from rest_framework.test import APIClient



@dataclass
class AuthClient:
    client: APIClient
    user: any
    access_token: str
    refresh_token: str

    def get(self, path: str, **kwargs):
        return self.client.get(path, **kwargs)

    def post(self, path: str, data=None, **kwargs):
        return self.client.post(path, data, **kwargs)

    def patch(self, path: str, data=None, **kwargs):
        return self.client.patch(path, data, **kwargs)

    def delete(self, path: str, **kwargs):
        return self.client.delete(path, **kwargs)