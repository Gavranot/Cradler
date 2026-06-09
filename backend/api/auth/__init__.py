"""
Authentication API router
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from core.database.connection import get_db
from core.database.models import User
from core.security import get_password_hash, verify_password, create_access_token
from api.auth.schemas import UserRegister, UserLogin, UserWithToken, UserResponse
from api.auth.dependencies import get_current_user

router = APIRouter()


@router.post("/register", response_model=UserWithToken, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserRegister, db: AsyncSession = Depends(get_db)):
    """
    Register a new user

    Args:
        user_data: User registration data (email, password)
        db: Database session

    Returns:
        User object with access token

    Raises:
        HTTPException: If email already exists
    """
    # Check if user with email already exists
    result = await db.execute(select(User).where(User.email == user_data.email))
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Create new user
    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        id=uuid.uuid4(),
        email=user_data.email,
        password_hash=hashed_password,
        role="user"  # Default role
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # Create access token
    access_token = create_access_token(data={"sub": str(new_user.id)})

    return UserWithToken(
        user=UserResponse.model_validate(new_user),
        access_token=access_token,
        token_type="bearer"
    )


@router.post("/login", response_model=UserWithToken)
async def login(credentials: UserLogin, db: AsyncSession = Depends(get_db)):
    """
    User login

    Args:
        credentials: Login credentials (email, password)
        db: Database session

    Returns:
        User object with access token

    Raises:
        HTTPException: If credentials are invalid
    """
    # Get user by email
    result = await db.execute(select(User).where(User.email == credentials.email))
    user = result.scalar_one_or_none()

    # Verify user exists and password is correct
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token
    access_token = create_access_token(data={"sub": str(user.id)})

    return UserWithToken(
        user=UserResponse.model_validate(user),
        access_token=access_token,
        token_type="bearer"
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """
    Get current user information

    Args:
        current_user: The authenticated user

    Returns:
        Current user details
    """
    return UserResponse.model_validate(current_user)


@router.post("/logout")
async def logout():
    """
    User logout (stateless - client should discard token)

    Note: With JWT tokens, logout is handled client-side by discarding the token.
    For production, consider implementing token blacklisting if needed.
    """
    return {"message": "Successfully logged out. Please discard your access token."}
