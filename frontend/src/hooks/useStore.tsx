import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { Analysis, Catalog, HealthStatus, Merchant, SavedRecommendation } from "../types";
import { api } from "../services/api";
function useStoreState() {
  const [merchants, setMerchants] = useState<Merchant[]>([]);
  const [merchantId, setMerchantId] = useState<number | null>(null);
  const [health, setHealth] = useState<HealthStatus>({ status: "loading" });
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [saved, setSaved] = useState<SavedRecommendation[]>([]);
  const [analyses, setAnalyses] = useState<Analysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [savedError, setSavedError] = useState("");
  const [savedLoading, setSavedLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const [moreLoading, setMoreLoading] = useState(false);
  const loadedMerchant = useRef<number | null>(null);
  const idRef = useRef(merchantId); idRef.current = merchantId;
  const pageController = useRef<AbortController>();
  useEffect(() => {
    const controller = new AbortController();
    api.getHealth(controller.signal).then(data => { if (!controller.signal.aborted) setHealth(data); }).catch(() => { if (!controller.signal.aborted) setHealth({ status: "error" }); });
    api.getMerchants(controller.signal).then(data => { if (controller.signal.aborted) return; setMerchants(data); setMerchantId(id => id ?? data[0]?.id ?? null); if (!data.length) { setLoading(false); setSavedLoading(false); setError("No merchants found. Seed the backend store to begin."); } })
      .catch(error => { if (!controller.signal.aborted) { setError(error.message); setLoading(false); setSavedLoading(false); } });
    return () => controller.abort();
  }, [revision]);
  useEffect(() => {
    if (!merchantId) return;
    const controller = new AbortController();
    pageController.current?.abort();
    if (loadedMerchant.current !== merchantId) { setCatalog(null); setSaved([]); }
    loadedMerchant.current = merchantId;
    setError(""); setSavedError(""); setLoading(true); setSavedLoading(true); setMoreLoading(false);
    api.getProducts(merchantId, controller.signal).then(data => { if (!controller.signal.aborted) setCatalog(data); })
      .catch(error => { if (!controller.signal.aborted) setError(error.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    api.getRecommendations(merchantId, controller.signal).then(data => { if (!controller.signal.aborted) setSaved(data); })
      .catch(error => { if (!controller.signal.aborted) setSavedError(error.message); })
      .finally(() => { if (!controller.signal.aborted) setSavedLoading(false); });
    return () => { controller.abort(); pageController.current?.abort(); };
  }, [merchantId, revision]);
  useEffect(() => setAnalyses([]), [merchantId]);
  async function loadMore() {
    if (!merchantId || !catalog || moreLoading) return;
    const controller = new AbortController(); pageController.current = controller; setMoreLoading(true);
    try {
      const next = await api.getProducts(merchantId, controller.signal, catalog.products.length);
      if (!controller.signal.aborted) setCatalog(current => current ? { ...next, products: [...current.products, ...next.products],
        available_units: current.available_units + next.available_units, low_stock_products: current.low_stock_products + next.low_stock_products,
        potential_stockouts: current.potential_stockouts + next.potential_stockouts } : next);
    } catch (error) { if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "Unable to load products."); }
    finally { setMoreLoading(false); }
  }
  function addAnalysis(analysis: Analysis) { if (analysis.merchant_id === idRef.current) setAnalyses(current => {
    const equivalent = (item: Analysis) => {
      if (item.kind !== analysis.kind || item.merchant_id !== analysis.merchant_id) return false;
      const { created_at: _oldTime, ...oldData } = item.data as unknown as Record<string, unknown>;
      const { created_at: _newTime, ...newData } = analysis.data as unknown as Record<string, unknown>;
      return JSON.stringify(oldData) === JSON.stringify(newData);
    };
    return [analysis, ...current.filter(item => !equivalent(item))].slice(0, 100);
  }); }
  function selectMerchant(id: number) { setCatalog(null); setSaved([]); setAnalyses([]); setMerchantId(id); }
  return { merchants, merchantId, setMerchantId: selectMerchant, health, catalog, saved, analyses, loading, error, savedError, savedLoading,
    refresh: () => setRevision(value => value + 1), addAnalysis, loadMore, moreLoading };
}
type StoreState = ReturnType<typeof useStoreState>;
const StoreContext = createContext<StoreState | null>(null);
export function StoreProvider({ children }: { children: ReactNode }) { const store = useStoreState(); return <StoreContext.Provider value={store}>{children}</StoreContext.Provider>; }
export function useStore() { const store = useContext(StoreContext); if (!store) throw new Error("StoreProvider is required"); return store; }
