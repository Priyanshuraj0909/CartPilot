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
 global.fetch=vi.fn().mockResolvedValueOnce({ok:true,json:async()=>({required:true})}).mockResolvedValueOnce({ok:true,json:async()=>({token:'opaque-test-token'})}).mockResolvedValueOnce({ok:true,json:async()=>({logged_out:true})});
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
 expect(screen.queryByText('Private workspace')).not.toBeInTheDocument();
});
