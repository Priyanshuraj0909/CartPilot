import { useEffect,useRef,useState,type ReactNode,type FormEvent } from 'react';
import { ApiError, request } from '../services/api';
import { Compass, ArrowUpRight, Eye, EyeOff, Package, Sparkles, ShieldCheck, TrendingUp } from 'lucide-react';
export function AccountGate({children}:{children:ReactNode}) {
 const enabled=import.meta.env.PROD || import.meta.env.VITE_REQUIRE_AUTH === "true";
 const [required,setRequired]=useState<boolean>(enabled),[signed,setSigned]=useState(false),[signup,setSignup]=useState(false),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const accountCheck=useRef<AbortController | null>(null);
 const [showPassword,setShowPassword]=useState(false);
 const [connectionFailed,setConnectionFailed]=useState(false),[checking,setChecking]=useState(false),[checkAttempt,setCheckAttempt]=useState(0);
 useEffect(()=>{
   let active=true;
   const controller=new AbortController();
   accountCheck.current=controller;
   async function checkAccount(){
     setChecking(true);
     setConnectionFailed(false);
     try {
       // Hosted authentication is already required; status is not a login prerequisite.
       if(!enabled){setRequired(false);}
       if(sessionStorage.getItem('cartpilot-token')){
         for(let attempt=0;attempt<3;attempt++){
           try {await request('/api/v1/auth/me',controller.signal);break;}
           catch(e){
             if(!active || !(e instanceof ApiError) || ![0,502,503,504].includes(e.status) || attempt===2)throw e;
           }
         }
         if(active){setSigned(true);setError('');}
       }
     } catch(e){
       if(!active || controller.signal.aborted)return;
       if(e instanceof ApiError && e.status===401){
         setRequired(true);setSigned(false);
       } else {
         // A network/storage failure does not invalidate an existing session.
         setRequired(true);setConnectionFailed(true);
         setError('Unable to connect to CartPilot. Try connecting again or sign in below.');
       }
     } finally {if(active)setChecking(false);}
   }
   void checkAccount();
   const expired=()=>{setRequired(true);setSigned(false);setError('Session expired. Sign in again.');};
   const openLogin=()=>setRequired(true);
   window.addEventListener('cartpilot-open-login',openLogin);
   window.addEventListener('cartpilot-session-expired',expired);
   return()=>{active=false;controller.abort();window.removeEventListener('cartpilot-session-expired',expired);window.removeEventListener('cartpilot-open-login',openLogin);};
 },[enabled,checkAttempt]);
 async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();accountCheck.current?.abort();setBusy(true);setError('');setConnectionFailed(false);const f=new FormData(e.currentTarget);try{const r=await request<{token:string}>(`/api/v1/auth/${signup?'signup':'login'}`,undefined,{email:f.get('email'),password:f.get('password'),...(signup?{name:f.get('name'),store_name:f.get('store_name')}:{})});sessionStorage.setItem('cartpilot-token',r.token);setSigned(true);}catch(e){setError(e instanceof Error?e.message:'Sign in failed.');}finally{setBusy(false);}}
 async function logout(){try{await request('/api/v1/auth/logout',undefined,{});sessionStorage.removeItem('cartpilot-token');setSigned(false);}catch(e){setError(e instanceof Error?e.message:'Logout failed.');}}
 if(!required||signed)return <>{!signed&&<div className="account-banner"><span>Merchant accounts unlock product editing, sales import and stock alerts.</span><button className="btn secondary" onClick={()=>setRequired(true)}>Sign in / Create account</button></div>}{signed&&<div className="card"><button className="btn secondary" onClick={logout}>Sign out</button>{error&&<p role="alert">{error}</p>}</div>}{children}</>;
 return <main className="auth-page">
   <section className="auth-story" aria-label="About CartPilot">
     <div className="auth-brand"><span className="auth-brand-mark"><Compass size={28}/></span><span>CartPilot<small>INTELLIGENT COMMERCE</small></span></div>
     <div className="auth-story-content"><span className="auth-eyebrow">YOUR STORE. A CLEARER DIRECTION.</span><h2>A little intelligence.<br/>A lot of possibility.</h2><p>Bring your products, sales and next best moves together in one merchant workspace.</p>
       <div className="auth-illustration" aria-hidden="true"><div className="auth-orbit"/><div className="auth-preview"><div className="auth-preview-heading"><span><Package size={18}/> Store overview</span><span className="auth-preview-dot"/></div><div className="auth-preview-title">See the bigger picture <TrendingUp size={22}/></div><div className="auth-bars">{[32,48,40,65,56,80,95].map((height,i)=><span key={i} style={{height:`${height}%`}}/>)}</div><div className="auth-preview-footer"><Sparkles size={16}/> Insights that guide your next move</div></div><div className="auth-floating"><ShieldCheck size={20}/><span>You stay in control<small>Review every recommendation</small></span></div></div>
       <div className="auth-story-note"><ShieldCheck size={18}/><span>Your store. Your decisions. CartPilot as your guide.</span></div>
     </div><span className="auth-story-footer">SENSE → DECIDE → RECOMMEND</span>
   </section>
   <section className="auth-form-panel" aria-labelledby="auth-title"><div className="auth-form-wrap"><span className="auth-eyebrow">MERCHANT WORKSPACE</span><h1 id="auth-title">{signup?'Start your next chapter.':'Welcome back.'}</h1><p className="auth-intro">{signup?'Create your account and give your store a home in CartPilot.':'Sign in to see your store clearly and plan your next move.'}</p>
     <form className="auth-form" onSubmit={submit} aria-busy={busy}>
       <fieldset disabled={busy}><legend className="sr-only">{signup?'Create merchant account':'Sign in to your account'}</legend>
       {signup&&<><div className="auth-field"><label htmlFor="auth-name">Your name</label><input id="auth-name" name="name" placeholder="e.g. Priyanshu Raj" autoComplete="name" required maxLength={255}/></div><div className="auth-field"><label htmlFor="auth-store">Store name</label><input id="auth-store" name="store_name" placeholder="e.g. The Everyday Store" autoComplete="organization" aria-describedby="auth-store-help" required maxLength={255}/><small id="auth-store-help">The name displayed in your merchant workspace.</small></div></>}
       <div className="auth-field"><label htmlFor="auth-email">Email</label><input id="auth-email" name="email" type="email" placeholder="you@example.com" autoComplete="email" required/></div>
       <div className="auth-field"><label htmlFor="auth-password">Password</label><div className="auth-password"><input id="auth-password" name="password" type={showPassword?'text':'password'} placeholder={signup?'Create a strong password':'Enter your password'} minLength={12} maxLength={128} aria-describedby="auth-password-help" autoComplete={signup?'new-password':'current-password'} required/><button type="button" aria-label={showPassword?'Hide password':'Show password'} aria-pressed={showPassword} onClick={()=>setShowPassword(!showPassword)}>{showPassword?<EyeOff size={19}/>:<Eye size={19}/>}</button></div><small id="auth-password-help">Use at least 12 characters.</small></div>
       {error&&<p className="auth-error" role="alert">{error}</p>}{connectionFailed&&<button className="btn secondary" type="button" disabled={checking} onClick={()=>setCheckAttempt(attempt=>attempt+1)}>Retry connection</button>}<button className="btn auth-submit" type="submit" disabled={busy}>{busy?'Please wait…':signup?'Create account':'Sign in'}<ArrowUpRight size={18}/></button>
       </fieldset>
     </form><p className="auth-switch">{signup?'Already have an account?':'New to CartPilot?'} <button type="button" disabled={busy} onClick={()=>{setSignup(!signup);setShowPassword(false);setError('');}}>{signup?'Sign in instead':'Create account'}</button></p><div className="auth-form-note"><ShieldCheck size={17}/><span>A dedicated workspace for your store.</span></div>
   </div><p className="auth-copyright">CartPilot · Built for thoughtful commerce</p></section>
 </main>;
}
