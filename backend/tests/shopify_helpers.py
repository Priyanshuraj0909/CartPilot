"""Synthetic Shopify GraphQL responses, routed through the real HTTP client."""
import copy
import json
from datetime import datetime, timedelta, timezone
import httpx
from app.core.config import Settings
from app.integrations.shopify.client import ShopifyClient
from app.integrations.shopify.queries import REQUIRED_SCOPES


def connection(nodes, more=False, cursor=None):
    return {'nodes':nodes,'pageInfo':{'hasNextPage':more,'endCursor':cursor}}


def variant(number=1, sku=None, price='100.00'):
    now=datetime.now(timezone.utc).isoformat()
    return {'id':f'gid://shopify/ProductVariant/{number}','title':['Small','Medium','Large'][(number-1)%3],
        'sku':sku,'price':price,'inventoryItem':{'id':f'gid://shopify/InventoryItem/{number}'},
        'product':{'id':'gid://shopify/Product/10','title':'Cotton Shirt','description':'A cotton shirt for everyday wear.',
                   'productType':'Clothing','status':'ACTIVE','createdAt':now,'updatedAt':now}}


def level(number, available=10, reserved=2, unavailable=1, active=True):
    return {'id':f'gid://shopify/InventoryLevel/{number}', 'isActive':True,
        'location':{'id':f'gid://shopify/Location/{number}','isActive':active},
        'quantities':[{'name':name,'quantity':qty} for name,qty in
            [('on_hand',available+reserved+unavailable),('available',available),('committed',reserved),('reserved',0)]]}


def inventory(number=1, cost='40.00', levels=None):
    return {'id':f'gid://shopify/InventoryItem/{number}','tracked':True,
        'unitCost':{'amount':cost,'currencyCode':'USD'} if cost is not None else None,
        'inventoryLevels':connection(levels if levels is not None else [level(1),level(2,15),level(3,100,active=False)])}


def line(number=1, variant_number=1, quantity=3):
    return {'id':f'gid://shopify/LineItem/{number}','quantity':quantity,'currentQuantity':quantity,
        'variant':{'id':f'gid://shopify/ProductVariant/{variant_number}'},
        'discountedUnitPriceAfterAllDiscountsSet':{'shopMoney':{'amount':'100.00','currencyCode':'USD'}}}


def order(number=1):
    return {'id':f'gid://shopify/Order/{number}','name':f'#{number}',
        'createdAt':(datetime.now(timezone.utc)-timedelta(days=1)).isoformat(),'cancelledAt':None,
        'displayFinancialStatus':'PAID','displayFulfillmentStatus':'UNFULFILLED',
        'currentTotalPriceSet':{'shopMoney':{'amount':'300.00','currencyCode':'USD'}},
        'lineItems':connection([line()])}


class ShopifyFixture:
    def __init__(self, merchant_id=1):
        self.config=Settings(_env_file=None,SHOPIFY_STORE_DOMAIN='fixture-store.myshopify.com',
            SHOPIFY_ACCESS_TOKEN='fixture-credential',SHOPIFY_MERCHANT_ID=merchant_id,SHOPIFY_MAX_RETRIES=2)
        self.variants=[variant(1,'SHIRT'),variant(2,'SHIRT'),variant(3)]
        self.orders=[order()]
        self.inventory_failure=False
        self.cost='40.00'
        self.calls=[]
        self.delays=[]
    async def sleep(self, delay): self.delays.append(delay)
    def handler(self, request):
        body=json.loads(request.content);query=body['query'];variables=body['variables'];self.calls.append(body)
        assert request.url.host==self.config.SHOPIFY_STORE_DOMAIN and request.url.scheme=='https'
        assert query.startswith('query ') and 'mutation' not in query.lower()
        if 'query CartPilotShop ' in query:
            data={'shop':{'name':'Fixture Store','myshopifyDomain':self.config.SHOPIFY_STORE_DOMAIN,'currencyCode':'USD'},
                'currentAppInstallation':{'accessScopes':[{'handle':s} for s in REQUIRED_SCOPES]}}
        elif 'query CartPilotVariants' in query:
            second=variables.get('cursor')=='variants-next'
            data={'productVariants':connection(copy.deepcopy(self.variants[1:] if second else self.variants[:1]),not second,'variants-next' if not second else None)}
        elif 'query CartPilotInventory' in query:
            if self.inventory_failure: return httpx.Response(503)
            number=int(variables['id'].rsplit('/',1)[1]);item=inventory(number,self.cost)
            second=variables.get('cursor')=='locations-next'
            levels=item['inventoryLevels']['nodes'];item['inventoryLevels']=connection(levels[1:] if second else levels[:1],not second,'locations-next' if not second else None)
            data={'inventoryItem':item}
        elif 'query CartPilotOrders' in query:
            data={'orders':connection(copy.deepcopy(self.orders))}
        else: raise AssertionError('Unexpected read')
        return httpx.Response(200,json={'data':data},headers={'X-Shopify-API-Version':self.config.SHOPIFY_API_VERSION})
    def client(self):
        return ShopifyClient(self.config,transport=httpx.MockTransport(self.handler),sleep=self.sleep)
