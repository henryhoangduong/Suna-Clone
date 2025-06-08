from typing import Optional

import jwt
from fastapi import HTTPException, Request
from jwt.exceptions import PyJWTError


async def get_current_user_id_from_jwt(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="No valid authentication credentials found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = auth_header.split(" ")[1]
    try:

        payload = jwt.decode(token, options={"verify_signature": False})

        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(
                status_code=401,
                detail="Invalid token payload",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user_id

    except PyJWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_account_id_from_thread(client, thread_id: str) -> str:
    try:
        response = (
            await client.table("threads")
            .select("account_id")
            .eq("thread_id", thread_id)
            .execute()
        )
        if not response.data or len(response.data) == 0:
            raise HTTPException(status_code=404, detail="Thread not found")

        account_id = response.data[0].get("account_id")

        if not account_id:
            raise HTTPException(
                status_code=500, detail="Thread has no associated account"
            )

        return account_id
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error retrieving thread information: {str(e)}"
        )
