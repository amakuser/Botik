from fastapi import HTTPException, Request, status

SESSION_TOKEN_HEADER = "x-botik-session-token"
SESSION_TOKEN_QUERY = "session_token"


def extract_session_token(request: Request) -> str | None:
    return request.headers.get(SESSION_TOKEN_HEADER) or request.query_params.get(SESSION_TOKEN_QUERY)


async def require_session_token(request: Request) -> None:
    expected = request.app.state.settings.session_token
    supplied = extract_session_token(request)
    if supplied != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing session token.",
        )
