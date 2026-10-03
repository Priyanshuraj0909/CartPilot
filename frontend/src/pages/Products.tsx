import { StoreManagement } from "../components/StoreManagement";
import { useStore } from "../hooks/useStore";
import { ErrorAlert, Loading, PageTitle, EmptyState } from "../components/common";
import { ProductTable } from "../components/ProductTable";
export function Products({ onDetails }: { onDetails: (id: number) => void }) {
  const store = useStore();
  return <><PageTitle title="Products" description="Explore price, demand, and inventory signals for every product." /><StoreManagement />{store.loading && <Loading />}{store.error && <ErrorAlert message={store.error} retry={store.refresh} />}{store.catalog && <>{!store.catalog.products.length ? <EmptyState>No products found. Seed your store to begin analysis.</EmptyState> : <ProductTable products={store.catalog.products} onDetails={onDetails} />}{store.catalog.has_more && <button className="btn secondary" disabled={store.moreLoading} onClick={store.loadMore}>{store.moreLoading ? "Loading…" : "Load more products"}</button>}</>}</>;
}
