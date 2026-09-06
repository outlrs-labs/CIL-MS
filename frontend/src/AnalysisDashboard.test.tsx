import {fireEvent,render,screen} from '@testing-library/react';
import {vi} from 'vitest';
import {AnalysisDashboard,type AnalysisCatalog} from './AnalysisDashboard';

const catalog:AnalysisCatalog={
 root_label:'Data/cil',
 entities:['ECL','BCCL'],
 folders:[
  {entity:'ECL',family:'production_offtake',name:'Production & offtake',cadences:['monthly']},
  {entity:'BCCL',family:'safety_incidents',name:'Safety incidents',cadences:['monthly']},
 ],
 files:[
  {id:'ecl-file',entity:'ECL',family:'production_offtake',name:'ecl-production-2026.csv',relative_path:'ECL/production_offtake/submissions/ecl-production-2026.csv',bytes:2048,supported:true,period:'2026-08',cadence:'monthly',version:2,is_latest:true},
  {id:'bccl-file',entity:'BCCL',family:'safety_incidents',name:'bccl-safety-2026.xlsx',relative_path:'BCCL/safety_incidents/submissions/bccl-safety-2026.xlsx',bytes:4096,supported:true,period:'2026-08',cadence:'monthly',version:1,is_latest:true},
  {id:'ecl-pdf',entity:'ECL',family:'production_offtake',name:'signed-report.pdf',relative_path:'ECL/production_offtake/data/versions/monthly/2026-08/v1/signed-report.pdf',bytes:8192,supported:false,extractable:true,format:'pdf',period:'2026-08',cadence:'monthly',version:2,is_latest:true},
 ]};

function renderDashboard(selected:Record<string,string>={}){
 const setSelected=vi.fn(),setEntities=vi.fn();
 render(<AnalysisDashboard catalog={catalog} technical entityCode="CMPDI" selected={selected} setSelected={setSelected} entities={['ECL','BCCL']} setEntities={setEntities} family="all" setFamily={vi.fn()} title="Consolidated analysis" setTitle={vi.fn()} period="" setPeriod={vi.fn()} target="CMPDI" setTarget={vi.fn()} targetFamily="annual" setTargetFamily={vi.fn()} busy={false} online analyses={[]} onCreate={vi.fn()} onOpen={vi.fn()} onRefresh={vi.fn().mockResolvedValue(undefined)} token="test-token"/>);
 return {setSelected,setEntities};
}

beforeAll(()=>{
 HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
 HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');};
});

test('browses and searches the root-wise CIL data hierarchy',async()=>{
 renderDashboard();
 fireEvent.click(screen.getByRole('button',{name:/choose data/i}));
 expect(await screen.findByRole('navigation',{name:'Data hierarchy'})).toBeInTheDocument();
 expect(screen.getAllByText('Data/cil')).toHaveLength(2);
 expect(screen.getByText('ecl-production-2026.csv')).toBeInTheDocument();
 expect(screen.getByText('bccl-safety-2026.xlsx')).toBeInTheDocument();
 expect(screen.getByText('signed-report.pdf')).toBeInTheDocument();

 fireEvent.click(screen.getByRole('button',{name:'Expand ECL'}));
 fireEvent.click(screen.getByRole('button',{name:/Production & offtake/}));
 expect(screen.getByText('ecl-production-2026.csv')).toBeInTheDocument();
 expect(screen.getByText('OCR on open')).toBeInTheDocument();
 expect(screen.queryByText('bccl-safety-2026.xlsx')).not.toBeInTheDocument();

 fireEvent.change(screen.getByRole('textbox',{name:'Search data hierarchy'}),{target:{value:'BCCL safety'}});
 expect(screen.getByText('bccl-safety-2026.xlsx')).toBeInTheDocument();
 expect(screen.queryByText('ecl-production-2026.csv')).not.toBeInTheDocument();
});

test('keeps selected files and backend entity scope aligned',async()=>{
 const {setSelected,setEntities}=renderDashboard();
 fireEvent.click(screen.getByRole('button',{name:/choose data/i}));
 fireEvent.click(await screen.findByRole('checkbox',{name:/ecl-production-2026.csv/}));
 expect(setSelected).toHaveBeenCalledWith({'ecl-file':''});
 expect(setEntities).toHaveBeenCalledWith(['ECL']);
});

test('changes the picker action label after a source is selected',()=>{
 renderDashboard({'ecl-file':''});
 expect(screen.getByRole('button',{name:/change files/i})).toBeInTheDocument();
 expect(screen.queryByRole('button',{name:/choose data/i})).not.toBeInTheDocument();
});
