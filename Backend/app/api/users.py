import secrets
import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.hash import bcrypt

from app.database import get_db
from app.middleware.auth import get_current_user, require_admin, require_owner
from app.models.user import User, UserInvite
from app.schemas.user import UserInviteCreate, UserAcceptInvite, UserManagementResponse, UserDirectCreate

router = APIRouter(prefix="/api/users", tags=["users"])

@router.get("/", response_model=list[UserManagementResponse])
async def list_users(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(User).where(User.team_id == admin.team_id).order_by(User.created_at.desc())
    )
    return result.scalars().all()

@router.post("/invite", status_code=status.HTTP_201_CREATED)
async def invite_user(
    data: UserInviteCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    # Check if user already exists
    existing_user = await db.execute(select(User).where(User.email == data.email))
    if existing_user.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")

    # Create invite
    token = secrets.token_urlsafe(32)
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)
    
    invite = UserInvite(
        email=data.email,
        role=data.role,
        team_id=admin.team_id,
        token=token,
        expires_at=expires_at
    )
    db.add(invite)
    await db.commit()

    # Log the invite link (in a real app, this would send an email)
    invite_url = f"/invite?token={token}"
    print(f"INVITATION CREATED: {data.email} ({data.role}) -> {invite_url}")

    return {"message": "Invitation sent", "token": token}

@router.get("/invite-details/{token}")
async def get_invite_details(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserInvite).where(UserInvite.token == token))
    invite = result.scalar_one_or_none()
    
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    
    if invite.expires_at < datetime.datetime.now(datetime.timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation expired")
        
    return {
        "email": invite.email,
        "role": invite.role
    }

@router.post("/accept-invite")
async def accept_invite(
    data: UserAcceptInvite,
    db: AsyncSession = Depends(get_db),
):
    # Verify invite
    result = await db.execute(select(UserInvite).where(UserInvite.token == data.token))
    invite = result.scalar_one_or_none()
    
    if not invite:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")
    
    if invite.expires_at < datetime.datetime.now(datetime.timezone.utc):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation expired")

    # Create user
    user = User(
        name=data.name,
        email=invite.email,
        password_hash=bcrypt.hash(data.password),
        team_id=invite.team_id,
        role=invite.role,
        is_active=True
    )
    db.add(user)
    
    # Delete invite
    await db.delete(invite)
    await db.commit()
    
    return {"message": "Account created successfully"}

@router.post("/direct", status_code=status.HTTP_201_CREATED)
async def create_user_direct(
    data: UserDirectCreate,
    owner: User = Depends(require_owner),
    db: AsyncSession = Depends(get_db),
):
    # Check if user already exists
    existing_user = await db.execute(select(User).where(User.email == data.email))
    if existing_user.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already exists")

    # Create user directly
    user = User(
        name=data.name,
        email=data.email,
        password_hash=bcrypt.hash(data.password),
        team_id=owner.team_id,
        role=data.role,
        is_active=True
    )
    db.add(user)
    await db.commit()
    
    return {"message": "User created successfully", "id": str(user.id)}

@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if str(admin.id) == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account")
        
    result = await db.execute(
        select(User).where(User.id == user_id, User.team_id == admin.team_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
    await db.delete(user)
    await db.commit()
