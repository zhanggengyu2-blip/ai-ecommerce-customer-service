from fastapi import APIRouter
import time
from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models import User, Message
from app.core.security import decode_token
from app.services.conversations import message_view, checked_conversation
from app.services.accounts import visible_account_ids, customer_account_ids

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/conversations/{conversation_id}")
async def websocket_messages(websocket: WebSocket, conversation_id: int):
    await websocket.accept()
    try:
        auth = await websocket.receive_json()
        claims = decode_token(auth.get("token", ""))
        with SessionLocal() as db:
            identity = db.get(User,int(claims['sub']))
            if (not identity or not identity.active or identity.tenant_id != 1
                    or claims['kind'] == 'staff' and identity.kind != 'STAFF'
                    or claims['kind'] == 'customer' and identity.kind not in ('CUSTOMER','GUEST')
                    or claims['kind'] not in ('staff','customer')):
                raise HTTPException(403,'Forbidden')
            c = checked_conversation(db, conversation_id, claims["tenant_id"])
            if claims["kind"] == "customer" and (c.user_id != int(claims["sub"])
                    or c.account_id not in customer_account_ids(db, identity)):
                raise HTTPException(403, "Forbidden")
            if claims["kind"] == "staff":
                staff = db.get(User, int(claims["sub"]))
                if (not staff or not staff.active or staff.tenant_id != c.tenant_id
                        or staff.role not in ("SUPER_ADMIN", "ADMIN", "CUSTOMER_SERVICE")
                        or c.account_id not in visible_account_ids(db, staff)):
                    raise HTTPException(403, "Forbidden")
        after_id = max(0, int(auth.get("after_id", 0)))
        while True:
            if time.time() >= claims["exp"]:
                await websocket.close(code=1008)
                return
            with SessionLocal() as db:
                identity = db.get(User,int(claims['sub']))
                if not identity or not identity.active:
                    await websocket.close(code=1008)
                    return
                if claims['kind'] == 'customer':
                    c = checked_conversation(db, conversation_id, claims['tenant_id'])
                    if c.account_id not in customer_account_ids(db, identity):
                        await websocket.close(code=1008)
                        return
                if claims["kind"] == "staff":
                    staff = db.get(User, int(claims["sub"]))
                    c = checked_conversation(db, conversation_id, claims['tenant_id'])
                    if not staff or not staff.active or c.account_id not in visible_account_ids(db, staff):
                        await websocket.close(code=1008)
                        return
                rows = db.scalars(select(Message).where(Message.conversation_id == conversation_id,
                                  Message.id > after_id).order_by(Message.id).limit(100)).all()
                for row in rows:
                    await websocket.send_json(message_view(row))
                    after_id = row.id
            import asyncio
            try:
                event = await asyncio.wait_for(websocket.receive(), timeout=1)
                if event["type"] == "websocket.disconnect":
                    return
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        return
    except (HTTPException, ValueError, KeyError):
        await websocket.close(code=1008)
