"""
Admin API — platform owner only.
Endpoints for managing organizations and their initial superadmin users.
"""
import logging
import traceback
from app.services.email_service import send_org_creation_email
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from passlib.context import CryptContext
from jose import jwt, JWTError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import get_settings
from app.database import get_db
from app.models.organization import Organization, PlatformUser
from app.models.user import User, Team
from app.schemas.user import OrgCreate, OrgResponse, PlatformUserResponse, TokenResponse, IndividualUserCreate, IndividualUserResponse

router = APIRouter(prefix="/api/admin", tags=["admin"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
settings = get_settings()
bearer_scheme = HTTPBearer()
logger = logging.getLogger("serverdeck.admin")


async def require_platform_owner(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> PlatformUser:
    """Dependency that ensures the caller is the platform owner."""
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if not payload.get("is_platform_owner"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Platform owner access required")

    user_id = payload.get("sub")
    result = await db.execute(select(PlatformUser).where(PlatformUser.id == user_id))
    platform_user = result.scalar_one_or_none()
    if not platform_user or not platform_user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Platform owner account not found")

    return platform_user


# ── Setup ────────────────────────────────────────────────────────────────────

@router.post("/setup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def setup_platform_owner(
    name: str,
    email: str,
    password: str,
    db: AsyncSession = Depends(get_db),
):
    """One-time endpoint to create the platform owner account.
    Returns 409 if a platform owner already exists.
    """
    existing = await db.execute(select(PlatformUser))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Platform owner already exists")

    platform_user = PlatformUser(
        name=name,
        email=email,
        password_hash=pwd_context.hash(password),
    )
    db.add(platform_user)
    await db.commit()
    await db.refresh(platform_user)

    from app.api.auth import create_platform_owner_token
    token = create_platform_owner_token(platform_user)
    return TokenResponse(
        access_token=token,
        user=PlatformUserResponse(id=platform_user.id, name=platform_user.name, email=platform_user.email),
        is_platform_owner=True,
    )


# ── Organizations ─────────────────────────────────────────────────────────────

@router.get("/organizations", response_model=list[OrgResponse])
async def list_organizations(
    _: PlatformUser = Depends(require_platform_owner),
    db: AsyncSession = Depends(get_db),
):
    """List all provisioned organizations."""
    result = await db.execute(select(Organization).order_by(Organization.created_at.desc()))
    return result.scalars().all()


@router.post("/organizations", response_model=OrgResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    background_tasks: BackgroundTasks,
    data: OrgCreate,
    _: PlatformUser = Depends(require_platform_owner),
    db: AsyncSession = Depends(get_db),
):
    """Create a new organization and provision its superadmin user."""
    from app.services.tenant import create_tenant_schema, run_tenant_migrations

    org_key = data.org_key.strip().lower().replace(" ", "_")
    schema_name = f"tenant_{org_key}"
    domain = data.domain.strip().lower()

    # Validate uniqueness
    existing_org = await db.execute(select(Organization).where(Organization.org_key == org_key))
    if existing_org.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Organization key already exists")

    existing_domain = await db.execute(select(Organization).where(Organization.domain == domain))
    if existing_domain.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Domain already registered")

    # Create organization record
    org = Organization(
        name=data.name,
        domain=domain,
        org_key=org_key,
        schema_name=schema_name,
    )
    db.add(org)
    await db.commit()

    # Provision schema + run migrations
    try:
        await create_tenant_schema(schema_name, db)
        run_tenant_migrations(schema_name)
    except Exception as e:
        await db.execute(text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE"))
        await db.delete(org)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize schema: {str(e)}"
        )

    # Create the org superadmin user inside the tenant schema
    await db.execute(text(f"SET search_path TO {schema_name}, public"))

    team = Team(name=f"{data.name} Team")
    db.add(team)
    await db.flush()

    admin_user = User(
        email=data.admin_email,
        password_hash=pwd_context.hash(data.admin_password),
        name=data.admin_name,
        team_id=team.id,
        role="owner",
    )
    db.add(admin_user)
    await db.commit()
    background_tasks.add_task(send_org_creation_email, data.admin_email, data.name, data.admin_name)
    await db.refresh(org)
    return org


@router.delete("/organizations/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(
    org_id: str,
    _: PlatformUser = Depends(require_platform_owner),
    db: AsyncSession = Depends(get_db),
):
    """Delete an organization and drop its schema entirely."""
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")

    # Drop the tenant schema
    await db.execute(text(f"DROP SCHEMA IF EXISTS {org.schema_name} CASCADE"))
    await db.delete(org)
    await db.commit()


# ── Individual Users ──────────────────────────────────────────────────────────

@router.get("/users", response_model=list[IndividualUserResponse])
async def list_individual_users(
    _: PlatformUser = Depends(require_platform_owner),
    db: AsyncSession = Depends(get_db),
):
    """List all individual (personal email) users from the shared tenant_individual schema."""
    from app.services.tenant import INDIVIDUAL_SCHEMA, ensure_individual_schema_exists

    logger.info("[admin/users] Listing individual users")
    try:
        await ensure_individual_schema_exists(db)
        logger.info(f"[admin/users] Schema ready: {INDIVIDUAL_SCHEMA}, setting search_path")
        await db.execute(text(f"SET search_path TO {INDIVIDUAL_SCHEMA}, public"))
        result = await db.execute(select(User).order_by(User.created_at.desc()))
        users = result.scalars().all()
        logger.info(f"[admin/users] Found {len(users)} individual user(s)")
        return users
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[admin/users] Unexpected error listing users: {exc}\n{traceback.format_exc()}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("/users", response_model=IndividualUserResponse, status_code=status.HTTP_201_CREATED)
async def create_individual_user(
    data: IndividualUserCreate,
    _: PlatformUser = Depends(require_platform_owner),
    db: AsyncSession = Depends(get_db),
):
    """Create a new individual user in the shared tenant_individual schema."""
    from app.services.tenant import INDIVIDUAL_SCHEMA, ensure_individual_schema_exists, is_personal_email

    logger.info(f"[admin/users] Creating individual user: email={data.email}, name={data.name}")

    # Step 1 — validate email domain
    is_personal = is_personal_email(data.email)
    logger.info(f"[admin/users] is_personal_email('{data.email}') = {is_personal}")
    if not is_personal:
        logger.warning(f"[admin/users] Rejected non-personal email: {data.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use the Organizations section to onboard users with business email domains."
        )

    try:
        # Step 2 — ensure individual schema exists
        logger.info(f"[admin/users] Ensuring schema exists: {INDIVIDUAL_SCHEMA}")
        await ensure_individual_schema_exists(db)
        logger.info(f"[admin/users] Schema ready, setting search_path to {INDIVIDUAL_SCHEMA}")
        await db.execute(text(f"SET search_path TO {INDIVIDUAL_SCHEMA}, public"))

        # Step 3 — check for duplicate email
        logger.info(f"[admin/users] Checking for existing user with email: {data.email}")
        existing = await db.execute(select(User).where(User.email == data.email))
        if existing.scalar_one_or_none():
            logger.warning(f"[admin/users] Email already registered: {data.email}")
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

        # Step 4 — create Team
        logger.info(f"[admin/users] Creating team for user: {data.name}")
        team = Team(name=f"{data.name}'s Team")
        db.add(team)
        await db.flush()
        logger.info(f"[admin/users] Team created with id={team.id}")

        # Step 5 — create User
        logger.info(f"[admin/users] Creating user record")
        user = User(
            email=data.email,
            password_hash=pwd_context.hash(data.password),
            name=data.name,
            team_id=team.id,
            role="owner",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info(f"[admin/users] Individual user created successfully: id={user.id}, email={user.email}")
        return user

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[admin/users] Unexpected error creating user: {exc}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server error: {str(exc)}"
        )


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_individual_user(
    user_id: str,
    _: PlatformUser = Depends(require_platform_owner),
    db: AsyncSession = Depends(get_db),
):
    """Delete an individual user and their associated Team (and all cascaded data)."""
    from app.services.tenant import INDIVIDUAL_SCHEMA

    logger.info(f"[admin/users] Deleting individual user: id={user_id}")
    try:
        await db.execute(text(f"SET search_path TO {INDIVIDUAL_SCHEMA}, public"))
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            logger.warning(f"[admin/users] User not found for deletion: id={user_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        logger.info(f"[admin/users] Found user email={user.email}, team_id={user.team_id}. Deleting team...")
        # Delete the user's Team — cascades to servers, folders, audit logs, etc.
        team_result = await db.execute(select(Team).where(Team.id == user.team_id))
        team = team_result.scalar_one_or_none()
        if team:
            await db.delete(team)
            logger.info(f"[admin/users] Team {team.id} deleted (cascades user + data)")
        else:
            logger.warning(f"[admin/users] No team found for user {user_id}, deleting user directly")
            await db.delete(user)

        await db.commit()
        logger.info(f"[admin/users] User {user_id} successfully deleted")

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[admin/users] Unexpected error deleting user {user_id}: {exc}\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Server error: {str(exc)}"
        )
