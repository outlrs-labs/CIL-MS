import {fireEvent,render,screen} from '@testing-library/react';
import {afterEach,vi} from 'vitest';
import {VaultWorkspace} from './VaultWorkspace';

const structure={
 entities:['ECL','BCCL'],timezone:'Asia/Kolkata',
 families:{
  ECL:{production_offtake:{name:'Production and off-take report',cycles:{daily:{current_period:'2026-09-05',status:'submitted',latest_version:2,last_update:'2026-09-05T10:30:00+05:30'},monthly:{current_period:'2026-09',status:'awaiting_submission',latest_version:null,last_update:null}}},financial:{name:'Financial report',cycles:{quarterly:{current_period:'2026-Q3',status:'awaiting_submission',latest_version:null,last_update:null}}}},
  BCCL:{production_offtake:{name:'Production and off-take report',cycles:{daily:{current_period:'2026-09-05',status:'awaiting_submission',latest_version:null,last_update:null}}}},
 },
 submissions:[
  {id:'version-2-hash',entity:'ECL',family:'production_offtake',cadence:'daily',period:'2026-09-05',version:2,previous_id:'version-1-hash',uploaded_at:'2026-09-05T10:30:00+05:30',data_prefix:'ECL/production_offtake/data/versions/daily/2026-09-05/version-2-hash',pending_extraction:0,files:[{name:'CIL_FOLDER/production.csv',bytes:2048,status:'ready_for_analysis'}]},
  {id:'version-1-hash',entity:'ECL',family:'production_offtake',cadence:'daily',period:'2026-09-05',version:1,previous_id:null,uploaded_at:'2026-09-05T09:00:00+05:30',data_prefix:'ECL/production_offtake/data/versions/daily/2026-09-05/version-1-hash',pending_extraction:0,files:[{name:'production.csv',bytes:1800,status:'ready_for_analysis'}]},
 ],
};

function mockVault(value:unknown=structure){const fetchMock=vi.fn().mockResolvedValue({ok:true,json:async()=>value});vi.stubGlobal('fetch',fetchMock);return fetchMock}
afterEach(()=>vi.unstubAllGlobals());

test('administrator drills from subsidiary to report category without storage folders',async()=>{
 mockVault();render(<VaultWorkspace token="token" entityCode="CIL" canFilterSubsidiary/>);
 fireEvent.click(await screen.findByRole('button',{name:/ECL 2 report categories/}));
 expect(screen.queryByRole('heading',{name:'ECL reports'})).not.toBeInTheDocument();
 expect(screen.queryByRole('navigation',{name:'Vault location'})).not.toBeInTheDocument();
 expect(screen.getByRole('textbox',{name:'Search folders'})).toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Reload Vault'})).toBeInTheDocument();
 expect(screen.queryByText('data')).not.toBeInTheDocument();
 expect(screen.queryByText('report_generated')).not.toBeInTheDocument();
 fireEvent.click(screen.getByRole('button',{name:/Production and off-take report/}));
 expect(screen.getByRole('button',{name:/5 September 2026 2 versions/})).toBeInTheDocument();
 expect(screen.queryByText('version-2-hash')).not.toBeInTheDocument();
});

test('subsidiary lands directly in its own report directory',async()=>{
 mockVault();render(<VaultWorkspace token="token" entityCode="ECL" canFilterSubsidiary={false}/>);
 expect(await screen.findByRole('button',{name:/Financial report/})).toBeInTheDocument();
 expect(screen.queryByRole('heading',{name:'ECL reports'})).not.toBeInTheDocument();
 expect(screen.queryByRole('navigation',{name:'Vault location'})).not.toBeInTheDocument();
 expect(screen.queryByRole('button',{name:/BCCL/})).not.toBeInTheDocument();
});

test('version control expands files and filters by reporting cycle',async()=>{
 mockVault();render(<VaultWorkspace token="token" entityCode="ECL" canFilterSubsidiary={false}/>);
 fireEvent.click(await screen.findByRole('button',{name:/Production and off-take report/}));
 fireEvent.click(screen.getByRole('button',{name:/5 September 2026 2 versions/}));
 expect(screen.getAllByText(/Version [12]/)).toHaveLength(2);
 fireEvent.click(screen.getByRole('button',{name:/Version 2/}));
 expect(screen.getByText('production.csv')).toBeInTheDocument();
 expect(screen.queryByText('CIL_FOLDER/production.csv')).not.toBeInTheDocument();
 expect(screen.queryByText(/ready for analysis/)).not.toBeInTheDocument();
 fireEvent.click(screen.getByText('Filter'));
 fireEvent.click(screen.getByRole('button',{name:'Monthly'}));
 expect(screen.getByText('No matching dates')).toBeInTheDocument();
});
