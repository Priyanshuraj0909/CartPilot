"""Bounded asynchronous reads from one validated Shopify Admin GraphQL endpoint."""
import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from collections.abc import AsyncIterator, Awaitable, Callable
import httpx
from app.core.config import Settings
from app.integrations.shopify.queries import Query, QUERIES, REQUIRED_SCOPES

logger=logging.getLogger(__name__)

class ShopifyError(Exception):
    def __init__(self, code: str, message: str, status_code: int=502):
        super().__init__(message);self.code=code;self.status_code=status_code

class ShopifyClient:
    def __init__(self, config: Settings, transport: httpx.AsyncBaseTransport | None=None,
                 sleep: Callable[[float], Awaitable[None]]=asyncio.sleep):
        if not config.SHOPIFY_STORE_DOMAIN or not config.shopify_auth_configured or not config.SHOPIFY_MERCHANT_ID:
            raise ShopifyError('not_configured','Set Shopify domain, token or complete client credentials, and merchant binding in the backend environment.',503)
        # Revalidate even if test/runtime configuration was assigned after Settings initialization.
        self.domain=Settings.valid_shop_domain(config.SHOPIFY_STORE_DOMAIN)
        self.config=config;self.transport=transport;self.sleep=sleep
        self.url=f'https://{self.domain}/admin/api/{config.SHOPIFY_API_VERSION}/graphql.json'
        self.token_url=f'https://{self.domain}/admin/oauth/access_token'
        self._client_credentials=bool(config.SHOPIFY_CLIENT_ID.strip() and config.SHOPIFY_CLIENT_SECRET.get_secret_value())
        self._access_token=None if self._client_credentials else config.SHOPIFY_ACCESS_TOKEN.get_secret_value()
        self._token_expires_at=0.0
        self._token_lock=asyncio.Lock()

    async def _get_access_token(self, force_refresh: bool=False) -> str:
        if not self._client_credentials:
            return self.config.SHOPIFY_ACCESS_TOKEN.get_secret_value()
        if not force_refresh and self._access_token and self._token_expires_at > time.monotonic()+60:
            return self._access_token
        async with self._token_lock:
            if not force_refresh and self._access_token and self._token_expires_at > time.monotonic()+60:
                return self._access_token
            try:
                async with httpx.AsyncClient(timeout=self.config.SHOPIFY_TIMEOUT_SECONDS, follow_redirects=False,
                                             transport=self.transport) as http:
                    response=await http.post(self.token_url,data={
                        'grant_type':'client_credentials',
                        'client_id':self.config.SHOPIFY_CLIENT_ID,
                        'client_secret':self.config.SHOPIFY_CLIENT_SECRET.get_secret_value(),
                    })
            except (httpx.TimeoutException,httpx.NetworkError):
                raise ShopifyError('token_network','Could not reach Shopify to refresh app authentication.') from None
            if response.status_code==429 or response.status_code>=500:
                raise ShopifyError('token_unavailable','Shopify app authentication is temporarily unavailable; retry synchronization later.',503)
            if response.status_code!=200:
                raise ShopifyError('token_authentication','Shopify rejected the app credentials. Check the Client ID, rotated Client Secret, and that the app and store belong to the same Shopify organization.',401)
            try:
                body=response.json()
                token=body['access_token'];scopes={scope.strip() for scope in body['scope'].split(',')};lifetime=body['expires_in']
                if not isinstance(token,str) or not token.strip() or type(lifetime) is not int or lifetime<=60 or not REQUIRED_SCOPES<=scopes:
                    raise ValueError()
            except (KeyError,TypeError,ValueError,AttributeError):
                raise ShopifyError('token_response','Shopify returned an invalid token response or required read scopes are missing.',502) from None
            self._access_token=token
            self._token_expires_at=time.monotonic()+lifetime
            return token

    async def read(self, query: Query, variables: dict | None=None) -> dict:
        if not isinstance(query,Query):
            raise ShopifyError('invalid_query','Only fixed read-only Shopify queries are allowed.',422)
        async with httpx.AsyncClient(timeout=self.config.SHOPIFY_TIMEOUT_SECONDS,follow_redirects=False,transport=self.transport) as http:
            refreshed=False
            retries=0
            while True:
                retry=False;delay=min(2**retries,30)
                try:
                    token=await self._get_access_token()
                    response=await http.post(self.url,headers={'X-Shopify-Access-Token':token},json={'query':QUERIES[query],'variables':variables or {}})
                except (httpx.TimeoutException,httpx.NetworkError):
                    if retries>=self.config.SHOPIFY_MAX_RETRIES:
                        raise ShopifyError('network','Shopify is unavailable or timed out. Local/demo data remains available.') from None
                    retry=True
                if not retry:
                    if response.status_code==401 and self._client_credentials and not refreshed:
                        if self._access_token==token:
                            self._access_token=None;self._token_expires_at=0.0
                        refreshed=True
                        continue
                    if response.status_code in (401,403):
                        raise ShopifyError('authentication','Shopify connection failed. Check store domain, Admin API token and read permissions.',401)
                    if response.status_code==429 or response.status_code>=500:
                        retry=True
                        retry_after=response.headers.get('Retry-After')
                        try:
                            if retry_after: delay=float(retry_after)
                        except ValueError:
                            try:
                                delay=max(0,(parsedate_to_datetime(retry_after)-datetime.now(timezone.utc)).total_seconds())
                            except (TypeError, ValueError): delay=min(2**retries,30)
                        if not 0<=delay<=60:
                            raise ShopifyError('throttled','Shopify requested a long retry delay. Retry synchronization later.',503)
                    elif response.status_code!=200:
                        raise ShopifyError('http','Shopify rejected the read request. Check the configured API version and store.',502)
                    else:
                        actual_version=response.headers.get('X-Shopify-API-Version')
                        if actual_version and actual_version!=self.config.SHOPIFY_API_VERSION:
                            raise ShopifyError('version','Shopify served a different API version; review the supported version before syncing.',502)
                        try: body=response.json()
                        except ValueError:
                            raise ShopifyError('malformed','Shopify returned an unreadable response.') from None
                        if not isinstance(body,dict): raise ShopifyError('malformed','Shopify returned an invalid response structure.')
                        errors=body.get('errors',[])
                        if errors:
                            if not isinstance(errors,list) or not all(isinstance(e,dict) for e in errors):
                                raise ShopifyError('malformed','Shopify returned invalid GraphQL errors.')
                            if any(not isinstance(e.get('extensions',{}),dict) for e in errors):
                                raise ShopifyError('malformed','Shopify returned invalid error metadata.')
                            codes={str(e.get('extensions',{}).get('code')) for e in errors}
                            if codes=={'THROTTLED'}:
                                retry=True
                                metadata=body.get('extensions',{})
                                if not isinstance(metadata,dict) or not isinstance(metadata.get('cost',{}),dict):
                                    raise ShopifyError('malformed','Shopify returned invalid throttle metadata.')
                                throttle=metadata.get('cost',{}).get('throttleStatus',{})
                                if not isinstance(throttle,dict): raise ShopifyError('malformed','Shopify returned invalid throttle metadata.')
                                try:
                                    cost=float(body.get('extensions',{}).get('cost',{}).get('requestedQueryCost',1))
                                    restore=float(throttle.get('restoreRate',1));available=float(throttle.get('currentlyAvailable',0))
                                    delay=max(1,(cost-available)/restore) if restore>0 else 60
                                except (TypeError,ValueError): delay=min(2**retries,30)
                                if not 0<=delay<=60: raise ShopifyError('throttled','Shopify query budget is unavailable; retry later.',503)
                            elif codes=={'ACCESS_DENIED'}:
                                # Never echo Shopify error strings, query variables or tokens.
                                raise ShopifyError('access_denied','Shopify read permission is unavailable for the requested data.',403)
                            else: raise ShopifyError('graphql','Shopify could not complete a read query. Check API fields and permissions.')
                        else:
                            data=body.get('data')
                            if not isinstance(data,dict): raise ShopifyError('malformed','Shopify response is missing data.')
                            return data
                if retries>=self.config.SHOPIFY_MAX_RETRIES:
                    raise ShopifyError('throttled' if not retry else 'retry_exhausted','Shopify retry limit reached; retry synchronization later.',503)
                retries+=1
                logger.info('shopify_read_retry attempt=%s',retries)
                await self.sleep(delay)
        raise ShopifyError('retry_exhausted','Shopify retry limit reached.',503)

    async def pages(self, query: Query, path: tuple[str,...], variables: dict | None=None) -> AsyncIterator[list[dict]]:
        cursor=None;seen=set()
        for _ in range(self.config.SHOPIFY_MAX_PAGES):
            data=await self.read(query,{**(variables or {}),'cursor':cursor})
            try:
                connection=data
                for key in path: connection=connection[key]
                nodes=connection['nodes'];info=connection['pageInfo']
                if not isinstance(nodes,list) or not all(isinstance(n,dict) for n in nodes) or type(info['hasNextPage']) is not bool:
                    raise ValueError()
                next_cursor=info.get('endCursor')
            except (KeyError,TypeError,ValueError):
                raise ShopifyError('malformed','Shopify returned an invalid paginated connection.') from None
            yield nodes
            if not info['hasNextPage']: return
            if not isinstance(next_cursor,str) or not next_cursor or next_cursor in seen:
                raise ShopifyError('pagination','Shopify pagination cursor did not advance.')
            seen.add(next_cursor);cursor=next_cursor
        raise ShopifyError('page_limit','Shopify pagination limit reached; synchronization is incomplete.')

    async def connection(self) -> dict:
        data=await self.read(Query.SHOP)
        try:
            shop=data['shop'];scopes={s['handle'] for s in data['currentAppInstallation']['accessScopes']}
            if shop['myshopifyDomain']!=self.domain: raise ValueError()
            if not REQUIRED_SCOPES<=scopes: raise ShopifyError('access_denied','Grant read_products, read_inventory and read_orders for this integration.',403)
            currency=shop['currencyCode']
            if not isinstance(currency,str) or len(currency)!=3: raise ValueError()
            return {'name':shop['name'],'domain':self.domain,'currency':currency}
        except (KeyError,TypeError,ValueError):
            raise ShopifyError('malformed','Shopify shop identity response is invalid.') from None

    async def variants(self) -> AsyncIterator[list[dict]]:
        async for page in self.pages(Query.VARIANTS,('productVariants',)): yield page

    async def inventory(self, item_id: str) -> dict:
        async def collect(query):
            snapshot=None;levels=[];cursor=None;seen=set()
            for _ in range(self.config.SHOPIFY_MAX_PAGES):
                data=await self.read(query,{'id':item_id,'cursor':cursor})
                try:
                    item=data['inventoryItem'];connection=item['inventoryLevels'];info=connection['pageInfo']
                    if item['id']!=item_id or not isinstance(connection['nodes'],list) or type(info['hasNextPage']) is not bool: raise ValueError()
                    if snapshot is None: snapshot={**item,'inventoryLevels':[]}
                    levels.extend(connection['nodes'])
                    if not info['hasNextPage']:
                        snapshot['inventoryLevels']=levels;return snapshot
                    cursor=info['endCursor']
                    if not isinstance(cursor,str) or not cursor or cursor in seen: raise ValueError()
                    seen.add(cursor)
                except (KeyError,TypeError,ValueError): raise ShopifyError('malformed','Shopify inventory response is invalid.') from None
            raise ShopifyError('page_limit','Shopify inventory location limit reached; inventory is incomplete.')
        if self.config.SHOPIFY_READ_COSTS:
            try: return await collect(Query.INVENTORY)
            except ShopifyError as exc:
                if exc.code!='access_denied': raise
                # Retry without optional unitCost: never infer cost from selling price.
        result=await collect(Query.INVENTORY_NO_COST);result['unitCost']=None
        return result

    async def orders(self) -> AsyncIterator[list[dict]]:
        cutoff=(datetime.now(timezone.utc)-timedelta(days=59)).strftime('%Y-%m-%dT%H:%M:%SZ')
        async for page in self.pages(Query.ORDERS,('orders',),{'filter':f'created_at:>={cutoff}'}):
            for order in page:
                try:
                    connection=order['lineItems'];info=connection['pageInfo']
                    if not isinstance(connection['nodes'],list): raise ValueError()
                    lines=list(connection['nodes'])
                    if type(info['hasNextPage']) is not bool: raise ValueError()
                    cursor=info.get('endCursor');seen=set()
                    page_count=1
                    while info['hasNextPage']:
                        if page_count>=self.config.SHOPIFY_MAX_PAGES:
                            raise ShopifyError('page_limit','Shopify order line limit reached; order is incomplete.')
                        if not isinstance(cursor,str) or not cursor or cursor in seen: raise ValueError()
                        seen.add(cursor)
                        data=await self.read(Query.ORDER_LINES,{'id':order['id'],'cursor':cursor})
                        if data['order']['id']!=order['id']: raise ValueError()
                        connection=data['order']['lineItems'];info=connection['pageInfo']
                        if not isinstance(connection['nodes'],list) or type(info['hasNextPage']) is not bool: raise ValueError()
                        lines.extend(connection['nodes']);cursor=info.get('endCursor');page_count+=1
                    order['lineItems']=lines
                except (KeyError,TypeError,ValueError): raise ShopifyError('malformed','Shopify order lines are invalid.') from None
            yield page
