"""Workspace identity used only by tests.

The API and the frontend never import this module. Production accounts come
from Atlas; these values exist so tokens in tests have a complete, stable shape.
"""

ACCOUNT = {
    "id": "64b7f0c2e1a2b3c4d5e6f7a8",
    "email": "researcher@example.com",
    "name": "Test Researcher",
}
