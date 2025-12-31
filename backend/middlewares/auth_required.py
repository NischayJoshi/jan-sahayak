from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi import Depends, HTTPException
from controllers.auth import decode_access_token

security = HTTPBearer()

async def auth_required(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = decode_access_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail="Invalid token")

        id = payload.get("id")
        username = payload.get("username")
        role = payload.get("role")
        if not id or not username:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        return {"id": id, "username": username, "role": role}

    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


async def organizer_required(user = Depends(auth_required)):
    if user.get("role") != "organizer":
        raise HTTPException(status_code=403, detail="Access denied. Organizer only.")
    return user

async def get_user(user = Depends(auth_required)):
    return user
