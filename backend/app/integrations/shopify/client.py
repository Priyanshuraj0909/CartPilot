"""Bounded asynchronous reads from one validated Shopify Admin GraphQL endpoint."""
import asyncio
import logging
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
        if not config.SHOPIFY_STORE_DOMAIN or not config.SHOPIFY_ACCESS_TOKEN.get_secret_value() or not config.SHOPIFY_MERCHANT_ID:
            raise ShopifyError('not_configured','Set Shopify domain, Admin API token and merchant binding in the backend environment.',503)
        # Revalidate even if test/runtime configuration was assigned after Settings initialization.
        self.domain=Settings.valid_shop_domain(config.SHOPIFY_STORE_DOMAIN)
        self.config=config;self.transport=transport;self.sleep=sleep
        self.url=f'https://{self.domain}/admin/api/{config.SHOPIFY_API_VERSION}/graphql.json'

    async def read(self, query: Query, variables: dict | None=None) -> dict:
        if not isinstance(query,Query):
            raise ShopifyError('invalid_query','Only fixed read-only Shopify queries are allowed.',422)
        headers={'X-Shopify-Access-Token':self.config.SHOPIFY_ACCESS_TOKEN.get_secret_value()}
        async with httpx.AsyncClient(timeout=self.config.SHOPIFY_TIMEOUT_SECONDS,follow_redirects=False,transport=self.transport) as http:
            for attempt in range(self.config.SHOPIFY_MAX_RETRIES+1):
                retry=False;delay=min(2**attempt,30)
                try:
                    response=await http.post(self.url,headers=headers,json={'query':QUERIES[query],'variables':variables or {}})
                except (httpx.TimeoutException,httpx.NetworkError):
                    if attempt==self.config.SHOPIFY_MAX_RETRIES:
                        raise ShopifyError('network','Shopify is unavailable or timed out. Local/demo data remains available.') from None
                    retry=True
                if not retry:
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
                            except (TypeError, ValueError): delay=min(2**attempt,30)
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
                                except (TypeError,ValueError): delay=min(2**attempt,30)
                                if not 0<=delay<=60: raise ShopifyError('throttled','Shopify query budget is unavailable; retry later.',503)
                            elif codes=={'ACCESS_DENIED'}:
                                # Never echo Shopify error strings, query variables or tokens.
                                raise ShopifyError('access_denied','Shopify read permission is unavailable for the requested data.',403)
                            else: raise ShopifyError('graphql','Shopify could not complete a read query. Check API fields and permissions.')
                        else:
                            data=body.get('data')
                            if not isinstance(data,dict): raise ShopifyError('malformed','Shopify response is missing data.')
                            return data
                if attempt==self.config.SHOPIFY_MAX_RETRIES:
                    raise ShopifyError('throttled' if not retry else 'retry_exhausted','Shopify retry limit reached; retry synchronization later.',503)
                logger.info('shopify_read_retry attempt=%s',attempt+1)
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
