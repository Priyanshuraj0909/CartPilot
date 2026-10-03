import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { vi, it, expect, beforeEach, afterEach } from 'vitest';
import { StoreManagement } from '../src/components/StoreManagement';
import { request } from '../src/services/api';
const refresh=vi.fn();
vi.mock('../src/hooks/useStore',()=>({useStore:()=>({catalog:{products:[{id:7,name:'Mouse',sku:'M-1',category:'Electronics',source:'local',selling_price:'20.00',cost_price:'10.00',inventory:{quantity:5}}]},refresh})}));
vi.mock('../src/services/api',()=>({request:vi.fn()}));
beforeEach(()=>{sessionStorage.setItem('cartpilot-token','test');vi.mocked(request).mockReset();refresh.mockClear();});
afterEach(()=>sessionStorage.clear());
it('submits an added product through the visible form',async()=>{
 vi.mocked(request).mockResolvedValue({id:8});render(<StoreManagement/>);
 fireEvent.change(screen.getByLabelText('SKU'),{target:{value:'NEW'}});
 fireEvent.change(screen.getByLabelText('Product name'),{target:{value:'Speaker'}});
 fireEvent.change(screen.getByLabelText('Category'),{target:{value:'Electronics'}});
 fireEvent.change(screen.getByLabelText('Selling price'),{target:{value:'25'}});
 fireEvent.click(screen.getByRole('button',{name:'Add product'}));
 await waitFor(()=>expect(request).toHaveBeenCalledWith('/api/v1/products',undefined,expect.objectContaining({sku:'NEW',name:'Speaker',selling_price:'25'}),'POST'));
 expect(await screen.findByRole('status')).toHaveTextContent('Product added');
});
it('shows sales summary without needing a hidden button',async()=>{
 vi.mocked(request).mockResolvedValue({total_revenue:'40.00',products:[{id:7,name:'Mouse',units:2,revenue:'40.00'}]});
 render(<StoreManagement mode="sales"/>);
 expect(await screen.findByText('Recorded sales revenue: 40.00')).toBeInTheDocument();
 expect(screen.getByRole('link',{name:'Download sample CSV'})).toHaveAttribute('download');
});
it('loads current stock notifications on page entry',async()=>{
 vi.mocked(request).mockResolvedValue({notifications:[{product:'Mouse',message:'Low stock.'}]});
 render(<StoreManagement mode="notifications"/>);
 expect(await screen.findByText('Mouse')).toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Refresh alerts'})).toBeInTheDocument();
});
