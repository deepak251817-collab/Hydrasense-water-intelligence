from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import get_password_hash, verify_password, create_access_token
from app.models.user import User, UserRole
from app.models.device import ProductDevice
from app.schemas.auth import (
    DeviceNumberLoginRequest,
    UserRegisterRequest,
    UserLoginRequest,
    TokenResponse,
)
from app.schemas.user import UserResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Shared, database-backed limits (PostgreSQL counters, configurable via
# RATE_LIMIT_* settings) so brute-force attempts are throttled per client.
login_rate_limit = rate_limit(
    "auth:login", "RATE_LIMIT_LOGIN_MAX", "RATE_LIMIT_LOGIN_WINDOW_SECONDS"
)
register_rate_limit = rate_limit(
    "auth:register", "RATE_LIMIT_REGISTER_MAX", "RATE_LIMIT_REGISTER_WINDOW_SECONDS"
)
# Device-number login shares the login throttle settings so a stolen or
# guessed printed number cannot be brute-forced either (grep-safe separate
# bucket key; same configurable limits as "auth:login").
device_login_rate_limit = rate_limit(
    "auth:device-login", "RATE_LIMIT_LOGIN_MAX", "RATE_LIMIT_LOGIN_WINDOW_SECONDS"
)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(register_rate_limit)],
)
def register(request: UserRegisterRequest, db: Session = Depends(get_db)):
    # Check for duplicate email (emails are stored lower-cased)
    existing_user = db.query(User).filter(
        func.lower(User.email) == request.email.strip().lower()
    ).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered"
        )

    # Public registration is for product users only. Never let a request
    # choose the AUTHORITY role.
    if request.role != UserRole.PRODUCT_USER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public registration is only available for product users"
        )

    # Product registration verification if product_code supplied. The row is
    # locked so two concurrent registrations cannot claim the same device.
    device = None
    if request.product_code:
        code = request.product_code.strip().upper()
        device = (
            db.query(ProductDevice)
            .filter(func.upper(ProductDevice.product_code) == code)
            .with_for_update()
            .first()
        )
        if not device:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid product code: Product does not exist"
            )
        if device.owner_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Product code has already been registered and bound to an account"
            )

    # Create new user
    new_user = User(
        email=request.email.strip().lower(),
        password_hash=get_password_hash(request.password),
        full_name=request.full_name.strip(),
        role=UserRole.PRODUCT_USER,
        is_active=True
    )
    db.add(new_user)
    db.flush()  # Flush to populate new_user.id

    # If product device exists, bind it to new user
    if device:
        device.owner_id = new_user.id
        device.status = "ACTIVE"
        device.activated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(new_user)
    return new_user


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(login_rate_limit)],
)
def login(request: UserLoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        func.lower(User.email) == request.email.strip().lower()
    ).first()
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account"
        )

    token = create_access_token(
        subject=user.id,
        role=user.role.value,
        email=user.email
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        role=user.role,
        user=UserResponse.model_validate(user)
    )


@router.post(
    "/device-login",
    response_model=TokenResponse,
    dependencies=[Depends(device_login_rate_limit)],
)
def device_login(request: DeviceNumberLoginRequest, db: Session = Depends(get_db)):
    """Personal-user login with the unique number printed on the device.

    The device number identifies the *device*; the token is issued to the
    account the device is bound to. An unregistered or unbound number never
    creates an account or reveals whether a different number exists: the
    response is a generic 400/404 without device details. Rate limiting applies
    per client, shared with the e-mail login budget.
    """

    number = request.device_number.strip().upper()
    if not number:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Device number is required",
        )

    device = (
        db.query(ProductDevice)
        .filter(func.upper(ProductDevice.device_number) == number)
        .first()
    )

    # Same generic message for unknown numbers and unbound devices so the
    # endpoint cannot be used to enumerate printed numbers.
    if device is None or device.owner_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid device number or device not yet linked to an account. "
            "Create an account and activate this device number first.",
        )

    user = device.owner
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Device account is inactive",
        )

    token = create_access_token(
        subject=user.id,
        role=user.role.value,
        email=user.email,
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        role=user.role,
        user=UserResponse.model_validate(user),
    )
