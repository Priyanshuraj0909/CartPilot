import { render,screen,fireEvent,waitFor } from '@testing-library/react';
import { AccountGate } from '../src/components/AccountGate';
import { StoreManagement } from '../src/components/StoreManagement';
import { StoreProvider } from '../src/hooks/useStore';
import { vi,it,expect,afterEach } from 'vitest';
afterEach(()=>{vi.unstubAllEnvs();sessionStorage.clear();});
it('labels signup fields and lets merchants reveal their password',async()=>{
 vi.stubEnv('VITE_REQUIRE_AUTH','true');
 global.fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>({required:true})});
 render(<AccountGate><p>Private workspace</p></AccountGate>);
 fireEvent.click(await screen.findByRole('button',{name:'Create account'}));
 const store=screen.getByLabelText('Store name');
 fireEvent.change(store,{target:{value:'My merchant store'}});
 expect(store).toHaveValue('My merchant store');
 expect(store).toHaveAttribute('aria-describedby','auth-store-help');
 const password=screen.getByLabelText('Password');
 expect(password).toHaveAttribute('type','password');
 fireEvent.click(screen.getByRole('button',{name:'Show password'}));
 expect(password).toHaveAttribute('type','text');
 fireEvent.click(screen.getByRole('button',{name:'Hide password'}));
 expect(password).toHaveAttribute('type','password');
 expect(screen.getByRole('heading',{name:'Start your next chapter.'})).toBeInTheDocument();
});
it('signs in and revokes the session on logout',async()=>{
 vi.stubEnv('VITE_REQUIRE_AUTH','true');
 global.fetch=vi.fn().mockResolvedValueOnce({ok:true,json:async()=>({token:'opaque-test-token'})}).mockResolvedValueOnce({ok:true,json:async()=>({logged_out:true})});
 render(<AccountGate><p>Private workspace</p></AccountGate>);
 fireEvent.change(await screen.findByLabelText('Email'),{target:{value:'owner@example.test'}});
 fireEvent.change(screen.getByLabelText('Password'),{target:{value:'correct horse battery staple'}});
 fireEvent.click(screen.getByRole('button',{name:'Sign in'}));
 expect(await screen.findByText('Private workspace')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Sign out'}));
 await waitFor(()=>expect(sessionStorage.getItem('cartpilot-token')).toBeNull());
 expect(await screen.findByRole('button',{name:'Sign in'})).toBeInTheDocument();
});
it('shows a visible account entry point without exposing anonymous edit controls',async()=>{
 global.fetch=vi.fn().mockResolvedValue({ok:true,json:async()=>[]});
 render(<StoreProvider><StoreManagement/></StoreProvider>);
 await waitFor(()=>expect(global.fetch).toHaveBeenCalledTimes(2));
 expect(screen.getByText('Manage your store')).toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Sign in / Create account'})).toBeInTheDocument();
 expect(screen.queryByRole('button',{name:'Add product'})).not.toBeInTheDocument();
});

it('shows the sign-in form immediately even when the status API hangs',()=>{
 vi.stubEnv('PROD',true);
 global.fetch=vi.fn().mockImplementation(()=>new Promise(()=>{}));
 render(<AccountGate><p>Private workspace</p></AccountGate>);
 expect(screen.getByRole('heading',{name:'Welcome back.'})).toBeVisible();
 expect(screen.getByLabelText('Email')).toBeVisible();
 expect(screen.queryByText('Checking account access…')).not.toBeInTheDocument();
 expect(global.fetch).not.toHaveBeenCalled();
 expect(screen.queryByText('Private workspace')).not.toBeInTheDocument();
});

it('recovers a saved session after a transient backend failure',async()=>{
 vi.stubEnv('VITE_REQUIRE_AUTH','true');sessionStorage.setItem('cartpilot-token','saved-token');
 global.fetch=vi.fn().mockRejectedValueOnce(new TypeError('Network error')).mockResolvedValueOnce({ok:true,json:async()=>({id:1})});
 render(<AccountGate><p>Private workspace</p></AccountGate>);
 expect(await screen.findByText('Private workspace')).toBeVisible();
 expect(sessionStorage.getItem('cartpilot-token')).toBe('saved-token');
 expect(global.fetch).toHaveBeenCalledTimes(2);
});
it('bounds retries, preserves the session and allows manual recovery',async()=>{
 vi.stubEnv('VITE_REQUIRE_AUTH','true');sessionStorage.setItem('cartpilot-token','saved-token');
 const fetch=vi.fn().mockResolvedValue({ok:false,status:503});global.fetch=fetch;
 render(<AccountGate><p>Private workspace</p></AccountGate>);
 expect(await screen.findByRole('button',{name:'Retry connection'})).toBeEnabled();
 expect(fetch).toHaveBeenCalledTimes(3);
 expect(sessionStorage.getItem('cartpilot-token')).toBe('saved-token');
 expect(screen.queryByText('Private workspace')).not.toBeInTheDocument();
 fetch.mockResolvedValue({ok:true,json:async()=>({id:1})});
 fireEvent.click(screen.getByRole('button',{name:'Retry connection'}));
 expect(await screen.findByText('Private workspace')).toBeVisible();
 expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
it('rejects an expired session without retrying invalid credentials',async()=>{
 vi.stubEnv('VITE_REQUIRE_AUTH','true');sessionStorage.setItem('cartpilot-token','expired-token');
 global.fetch=vi.fn().mockResolvedValue({ok:false,status:401});
 render(<AccountGate><p>Private workspace</p></AccountGate>);
 await waitFor(()=>expect(sessionStorage.getItem('cartpilot-token')).toBeNull());
 expect(global.fetch).toHaveBeenCalledTimes(1);
 expect(screen.queryByText('Private workspace')).not.toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Sign in'})).toBeEnabled();
});
it('unlocks sign in after failure so the merchant can retry',async()=>{
 vi.stubEnv('VITE_REQUIRE_AUTH','true');
 global.fetch=vi.fn().mockRejectedValueOnce(new TypeError('Network error')).mockResolvedValueOnce({ok:true,json:async()=>({token:'new-token'})});
 render(<AccountGate><p>Private workspace</p></AccountGate>);
 fireEvent.change(screen.getByLabelText('Email'),{target:{value:'owner@example.test'}});
 fireEvent.change(screen.getByLabelText('Password'),{target:{value:'correct horse battery staple'}});
 fireEvent.click(screen.getByRole('button',{name:'Sign in'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('Unable to reach');
 expect(screen.getByRole('button',{name:'Sign in'})).toBeEnabled();
 fireEvent.click(screen.getByRole('button',{name:'Sign in'}));
 expect(await screen.findByText('Private workspace')).toBeVisible();
 expect(global.fetch).toHaveBeenCalledTimes(2);
});
