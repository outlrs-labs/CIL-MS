import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,vi} from 'vitest';
import {VaultWorkspace} from './VaultWorkspace';

const listing={path:'',entries:[{name:'ECL',path:'ECL',kind:'folder',bytes:null,modified:1}],total:1,next_offset:null,recursive:false,truncated:false,filter_options:{entities:['ECL','BCCL','CMPDI'],reports:{ECL:[{id:'production_offtake',name:'Production and off-take report'}],BCCL:[{id:'financial',name:'Financial report'}],CMPDI:[{id:'annual',name:'Annual report'}]}}};

function mockVault(response:unknown=listing){
 const fetchMock=vi.fn().mockResolvedValue({ok:true,json:async()=>response});
 vi.stubGlobal('fetch',fetchMock);
 return fetchMock;
}

afterEach(()=>vi.unstubAllGlobals());

test('administrator filters in subsidiary then report order',async()=>{
 const fetchMock=mockVault();
 render(<VaultWorkspace token="token" entityCode="CIL" canFilterSubsidiary/>);
 await screen.findByText('ECL');
 fireEvent.click(screen.getByRole('button',{name:/Filter/}));
 expect(screen.getByRole('combobox',{name:'Subsidiary'})).toBeInTheDocument();
 expect(screen.getByRole('combobox',{name:'Report'})).toBeDisabled();
 fireEvent.change(screen.getByRole('combobox',{name:'Subsidiary'}),{target:{value:'ECL'}});
 await waitFor(()=>expect(fetchMock.mock.calls.some(([url])=>String(url).includes('entity=ECL'))).toBe(true));
 expect(screen.getByRole('combobox',{name:'Report'})).not.toBeDisabled();
 fireEvent.change(screen.getByRole('combobox',{name:'Report'}),{target:{value:'production_offtake'}});
 await waitFor(()=>expect(fetchMock.mock.calls.some(([url])=>String(url).includes('entity=ECL')&&String(url).includes('report=production_offtake'))).toBe(true));
 expect(screen.getByRole('combobox',{name:'Sort by'})).toHaveTextContent('Newest first');
 expect(screen.getByRole('option',{name:'Oldest first'})).toBeInTheDocument();
});

test('subsidiary sees only report filters for its own scoped vault',async()=>{
 mockVault();
 render(<VaultWorkspace token="token" entityCode="ECL" canFilterSubsidiary={false}/>);
 await screen.findByText('ECL');
 fireEvent.click(screen.getByRole('button',{name:/Filter/}));
 expect(screen.queryByRole('combobox',{name:'Subsidiary'})).not.toBeInTheDocument();
 expect(screen.getByRole('combobox',{name:'Report'})).not.toBeDisabled();
 expect(screen.getByRole('option',{name:'Production and off-take report'})).toBeInTheDocument();
});

test('an older folder response cannot crash the Vault page',async()=>{
 const {filter_options:_,...legacyListing}=listing;
 mockVault(legacyListing);
 render(<VaultWorkspace token="token" entityCode="CIL" canFilterSubsidiary/>);
 expect(await screen.findByText('ECL')).toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:/Filter/}));
 expect(screen.getByRole('combobox',{name:'Subsidiary'})).toBeInTheDocument();
 expect(screen.getByRole('combobox',{name:'Report'})).toBeDisabled();
});
