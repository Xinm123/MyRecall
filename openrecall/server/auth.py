"""Authentication placeholder for MyRecall API v1.

Phase 0: Always passes (no-op decorator).
Phase 5: Will enforce API key or JWT authentication.
"""

import functools


def require_auth(f):
    """Require authentication on an API endpoint.

    Phase 0: Always passes through (placeholder).
    Phase 5: Will check Authorization header for API key / JWT.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        # TODO Phase 5: Check Authorization header
        # token = request.headers.get("Authorization")
        # if not token or not validate_token(token):
        #     return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated
