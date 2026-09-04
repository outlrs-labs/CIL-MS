import {vi} from 'vitest';
vi.mock('./client',()=>({supabase:null,configured:false,previewAvailable:true,api:vi.fn()}));
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import App from './App';

test('shows secure setup state when Supabase is not configured',async()=>{
 render(<App/>);
 expect(await screen.findByRole('heading',{name:'Sign in to your workspace'})).toBeInTheDocument();
 expect(screen.getByText('Connect your Supabase project')).toBeInTheDocument();
 expect(screen.getByRole('button',{name:/sign in securely/i})).toBeDisabled();
});

test('read-only preview exposes the requested hierarchy without enabling writes',async()=>{
 render(<App/>);
 const preview=await screen.findByRole('button',{name:/read-only interface preview/i});
 fireEvent.click(preview);
 expect(await screen.findByRole('heading',{name:'Dashboard'})).toBeInTheDocument();
 expect(screen.getByText('One group. Clear responsibilities.')).toBeInTheDocument();
 expect(screen.getAllByText('CMPDI').length).toBeGreaterThan(0);
 expect(screen.getByText('7 operating subsidiaries')).toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Vault'})).toBeInTheDocument();
 expect(screen.getByText(/Read-only design preview/)).toBeInTheDocument();
 expect(screen.getAllByRole('heading',{level:1})).toHaveLength(1);
 expect(screen.getByRole('button',{name:'Dashboard'})).toHaveAttribute('aria-current','page');
});

test('settings separates overview, profile and security into focused views',async()=>{
 render(<App/>);
 fireEvent.click(await screen.findByRole('button',{name:/read-only interface preview/i}));
 fireEvent.click(await screen.findByRole('button',{name:'Settings'}));
 expect(screen.getByRole('heading',{name:'Account'})).toBeInTheDocument();
 expect(screen.getByRole('heading',{name:'Workspace'})).toBeInTheDocument();
 expect(screen.getByRole('button',{name:/Your profile CIL Administrator/})).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:'Login & security'}));
 expect(await screen.findByRole('heading',{name:'Password management'})).toBeInTheDocument();
 expect(screen.queryByRole('heading',{name:'Account'})).not.toBeInTheDocument();
});
