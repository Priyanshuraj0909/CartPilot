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
 expect(await screen.findByText('Recorded sales revenue: ₹40.00')).toBeInTheDocument();
 expect(screen.getByRole('link',{name:'Download sample CSV'})).toHaveAttribute('download');
});
it('loads current stock notifications on page entry',async()=>{
 vi.mocked(request).mockResolvedValue({notifications:[{product:'Mouse',message:'Low stock.'}]});
 render(<StoreManagement mode="notifications"/>);
 expect(await screen.findByText('Mouse')).toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Refresh alerts'})).toBeInTheDocument();
});

it('finds editable products by name, SKU and category and can clear search',()=>{
 render(<StoreManagement/>);
 const search=screen.getByRole('searchbox',{name:'Find a product to edit'});
 for(const value of [' mouse ', 'm-1', 'ELECTRONICS']){
  fireEvent.change(search,{target:{value}});
  expect(screen.getByRole('option',{name:'Mouse'})).toBeInTheDocument();
 }
 fireEvent.change(search,{target:{value:'not-found'}});
 expect(screen.queryByRole('option',{name:'Mouse'})).not.toBeInTheDocument();
 expect(screen.getByText('0 matching products')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Clear product search'}));
 expect(search).toHaveValue('');
 expect(screen.getByRole('option',{name:'Mouse'})).toBeInTheDocument();
});
