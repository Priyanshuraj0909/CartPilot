"""Account lifecycle and server-bound authorization. Tokens are never stored raw."""
import asyncio
import json
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, delete, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_database_session
from app.core.config import settings
from app.models.account import Account, AccountSession
from app.models.merchant import Merchant
from app.models.product import Product
from app.services.auth_limits import limit_auth_attempts

router = APIRouter(prefix='/auth', tags=['Accounts'])

def auth_required() -> bool:
    return settings.ENVIRONMENT == 'production' or settings.REQUIRE_AUTH

class Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(max_length=255)
    password: str = Field(min_length=12, max_length=128)
    @field_validator('email')
    @classmethod
    def email_format(cls, value: str) -> str:
        value = value.strip().lower()
        if value.count('@') != 1 or '.' not in value.split('@')[-1] or any(c.isspace() for c in value):
            raise ValueError('Enter a valid email address.')
        return value

class Signup(Credentials):
    name: str = Field(min_length=1, max_length=255)
    store_name: str = Field(min_length=1, max_length=255)
    @field_validator('name','store_name')
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip(): raise ValueError('This field cannot be blank.')
        return value.strip()

class EmailRecovery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    store_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=12, max_length=128)
    new_email: str = Field(max_length=255)

    @field_validator('store_name')
    @classmethod
    def normalize_store_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('Enter your store name.')
        return value

    @field_validator('new_email')
    @classmethod
    def normalize_new_email(cls, value: str) -> str:
        return Credentials.email_format(value)

class Identity(BaseModel):
    id: int
    merchant_id: int
    email: str

class LoginResponse(BaseModel):
    token: str
    expires_at: datetime
    user: Identity


def hash_password(password: str, salt: str) -> str:
    return hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()

async def issue(session: AsyncSession, account: Account) -> LoginResponse:
    token = secrets.token_urlsafe(48)
    expires = datetime.now(timezone.utc) + timedelta(hours=8)
    session.add(AccountSession(token_hash=hashlib.sha256(token.encode()).hexdigest(),account_id=account.id,expires_at=expires))
    await session.commit()
    return LoginResponse(token=token,expires_at=expires,user=Identity(id=account.id,merchant_id=account.merchant_id,email=account.email))

async def current_account(request: Request, session: AsyncSession = Depends(get_database_session)) -> Account:
    header = request.headers.get('authorization','')
    if not header.startswith('Bearer ') or len(header) > 256:
        raise HTTPException(401,'Sign in to continue.', headers={'WWW-Authenticate':'Bearer'})
    digest = hashlib.sha256(header[7:].encode()).hexdigest()
    record = await session.get(AccountSession,digest)
    if record is None or record.expires_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc):
        raise HTTPException(401,'Session expired. Sign in again.')
    account = await session.get(Account,record.account_id)
    if account is None:
        raise HTTPException(401,'Sign in to continue.')
    request.state.account = account
    return account

async def business_access(request: Request, session: AsyncSession = Depends(get_database_session)) -> None:
    if not auth_required() and not request.headers.get("authorization"):
        return
    account = await current_account(request,session)
    try:
        body = await request.json() if request.method in {'POST','PUT','PATCH'} else {}
    except json.JSONDecodeError:
        raise HTTPException(422,'Invalid JSON body.')
    if not isinstance(body,dict):
        raise HTTPException(422,'Expected an object.')
    scopes = [v for v in [request.query_params.get('merchant_id'),body.get('merchant_id')] if v is not None]
    if any(str(v) != str(account.merchant_id) for v in scopes):
        raise HTTPException(403,'Access to this store is denied.')
    product_id = body.get('product_id')
    if isinstance(product_id,int) and not isinstance(product_id,bool):
        product = await session.get(Product,product_id)
        if product and product.merchant_id != account.merchant_id:
            raise HTTPException(403,'Access to this product is denied.')

@router.get('/status')
async def status() -> dict:
    return {'required':auth_required()}

@router.post('/signup',response_model=LoginResponse,status_code=201,dependencies=[Depends(limit_auth_attempts)])
async def signup(body: Signup, session: AsyncSession = Depends(get_database_session)):
    salt=secrets.token_hex(16)
    password_hash = await asyncio.to_thread(hash_password,body.password,salt)
    merchant=Merchant(name=body.name.strip(),store_name=body.store_name.strip(),email=body.email)
    session.add(merchant)
    try:
        await session.flush()
        account=Account(merchant_id=merchant.id,email=body.email,password_hash=salt+':'+password_hash)
        session.add(account)
        await session.flush()
        return await issue(session,account)
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409,'Unable to register this email.')

@router.post('/login',response_model=LoginResponse,dependencies=[Depends(limit_auth_attempts)])
async def login(body: Credentials, session: AsyncSession = Depends(get_database_session)):
    account=await session.scalar(select(Account).where(Account.email==body.email))
    salt,expected = account.password_hash.split(':') if account else ('00'*16,'00'*64)
    actual=await asyncio.to_thread(hash_password,body.password,salt)
    if account is None or not hmac.compare_digest(actual,expected):
        raise HTTPException(401,'Email or password is incorrect.')
    return await issue(session,account)

@router.post('/recover-email',dependencies=[Depends(limit_auth_attempts)])
async def recover_email(body: EmailRecovery, session: AsyncSession = Depends(get_database_session)):
    """Change a forgotten login email after proving account ownership with its password."""
    candidates = (await session.execute(
        select(Account, Merchant)
        .join(Merchant, Merchant.id == Account.merchant_id)
        .where(func.lower(Merchant.store_name) == body.store_name.lower())
        .limit(3)
        .with_for_update()
    )).all()

    verified: tuple[Account, Merchant] | None = None
    for account, merchant in candidates:
        salt, expected = account.password_hash.split(':', 1)
        actual = await asyncio.to_thread(hash_password, body.password, salt)
        if hmac.compare_digest(actual, expected):
            if verified is not None:
                # Duplicate store names plus identical passwords are ambiguous.
                raise HTTPException(401, 'Store name or password could not be verified.')
            verified = (account, merchant)

    if verified is None or len(candidates) > 2:
        # Perform comparable password work when the store name does not identify an account.
        if not candidates:
            await asyncio.to_thread(hash_password, body.password, '00' * 16)
        raise HTTPException(401, 'Store name or password could not be verified.')

    account, merchant = verified
    if body.new_email == account.email:
        raise HTTPException(409, 'That email is already the login email for this store.')

    try:
        account.email = body.new_email
        merchant.email = body.new_email
        # Recovery invalidates sessions only when the identity update succeeds.
        await session.execute(delete(AccountSession).where(AccountSession.account_id == account.id))
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, 'That email is already in use.') from None
    return {'email_changed': True, 'message': 'Login email updated. Sign in with the new email.'}

@router.get('/me',response_model=Identity)
async def me(account: Account = Depends(current_account)):
    return Identity(id=account.id,merchant_id=account.merchant_id,email=account.email)

@router.post('/logout')
async def logout(request: Request, account: Account = Depends(current_account), session: AsyncSession = Depends(get_database_session)):
    digest=hashlib.sha256(request.headers['authorization'][7:].encode()).hexdigest()
    await session.execute(delete(AccountSession).where(AccountSession.token_hash==digest))
    await session.commit()
    return {'logged_out':True}
