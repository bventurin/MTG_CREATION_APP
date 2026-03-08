"""Custom security headers middleware."""


class SecurityHeadersMiddleware:
    """Add OWASP recommended security headers to every response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

       
        response["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )

        # Prevent Spectre-style side-channel attacks
        response["Cross-Origin-Embedder-Policy"] = "unsafe-none"  # 'require-corp' breaks CDN fonts
        response["Cross-Origin-Resource-Policy"] = "same-origin"

        # Restrict browser feature access
        response["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), fullscreen=(self)"
        )

        # Already set by Django's SecurityMiddleware, but ensure static files get it too
        response.setdefault("X-Content-Type-Options", "nosniff")

        return response
