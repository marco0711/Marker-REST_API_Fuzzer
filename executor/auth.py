class AuthHandler:
    """
    Lightweight handler for providing authentication headers to requests.
    Initialized with token or auth type info determined by the parser.
    """
    def __init__(self, auth_type=None, token=None, header=None):
        self.auth_type = auth_type
        self.token = token
        self.header = header or {}

    def has_auth(self) -> bool:
        """
        Returns True if any auth header is available to use.
        """
        return bool(self.header)

    def get_auth_header(self) -> dict:
        """
        Returns the current auth header to use in requests.
        """
        return self.header
