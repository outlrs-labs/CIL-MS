import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,vi} from 'vitest';
import {AnalyticsWorkspace} from './AnalyticsWorkspace';

afterEach(()=>{vi.unstubAllGlobals();sessionStorage.clear();vi.useRealTimers();});

beforeAll(()=>{
 HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
 HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');};
});

test('does not start the Vault request while another workspace is open',async()=>{
 const fetchMock=vi.fn().mockImplementation(async(input:RequestInfo|URL)=>{
  const url=String(input),body=url.includes('/catalog')?{files:[],folders:[],entities:['ECL'],root_label:'Data/cil'}:url.includes('/status')?{online:false,models:[]}:[];
  return {ok:true,json:async()=>body};
 });
 vi.stubGlobal('fetch',fetchMock);
 render(<AnalyticsWorkspace token="token" entityCode="ECL" technical={false} view="analysis"/>);
 await waitFor(()=>expect(fetchMock).toHaveBeenCalledTimes(4));
 expect(fetchMock.mock.calls.every(([url])=>!String(url).includes('/vault'))).toBe(true);
});

test('opens a ready analytics shell and waits for a new data selection',async()=>{
 const analysis={id:'analysis-1',title:'September workspace',status:'ready',period:'',scope_entities:['ECL'],missing_entities:[],sources:[],target_entity:'ECL',target_family:'production_offtake',tables:[]};
 const fetchMock=vi.fn().mockImplementation(async(input:RequestInfo|URL)=>{
  const url=String(input);
  if(url.includes('/catalog'))return {ok:true,json:async()=>({files:[],folders:[],entities:['ECL'],root_label:'Data/cil'})};
  if(url.includes('/status'))return {ok:true,json:async()=>({online:true,models:[]})};
  if(url.endsWith('/analyses'))return {ok:true,json:async()=>[analysis]};
  if(url.endsWith('/analyses/analysis-1/workbench-session'))return {ok:true,json:async()=>({url:'/cmpdi/workbench/analysis-1/'})};
  return {ok:true,json:async()=>[]};
 });
 vi.stubGlobal('fetch',fetchMock);
 render(<AnalyticsWorkspace token="token" entityCode="ECL" technical={false} view="analysis"/>);
 expect(screen.getByRole('button',{name:'Choose Data'})).toBeInTheDocument();
 expect(screen.queryByText('Version report')).not.toBeInTheDocument();
 expect(screen.queryByText('Recent analyses')).not.toBeInTheDocument();
 expect(screen.queryByText('Generate report')).not.toBeInTheDocument();
 await waitFor(()=>expect(screen.getByText('Analytics ready')).toBeInTheDocument());
 expect(screen.getByText('Select data to start working with analytics')).toBeInTheDocument();
 expect(screen.queryByTitle('CIL analytics workbench')).not.toBeInTheDocument();
 expect(fetchMock.mock.calls.some(([url])=>String(url).endsWith('/analyses/analysis-1/workbench-session'))).toBe(false);
});

test('creates the workbench session after data is selected',async()=>{
 const source={id:'ecl-file',entity:'ECL',family:'production_offtake',name:'production.csv',relative_path:'ECL/production_offtake/data/production.csv',bytes:1024,supported:true,period:'2026-09',cadence:'monthly',version:1,is_latest:true};
 const analysis={id:'analysis-2',title:'ECL report analysis',status:'ready',period:'',scope_entities:['ECL'],missing_entities:[],sources:[source],target_entity:'ECL',target_family:'production_offtake',tables:[]};
 const report={id:'report-1',title:'ECL report analysis',created:1,series:'report-1',version:1,previous_id:null,entity:'ECL',family:'production_offtake',can_submit:true,audit_status:null};
 const fetchMock=vi.fn().mockImplementation(async(input:RequestInfo|URL,init?:RequestInit)=>{
  const url=String(input);
  if(url.includes('/catalog'))return {ok:true,json:async()=>({files:[source],folders:[{entity:'ECL',family:'production_offtake',name:'Production and off-take report',cadences:['monthly']}],entities:['ECL'],root_label:'Data/cil'})};
  if(url.includes('/status'))return {ok:true,json:async()=>({online:true,models:[]})};
  if(url.endsWith('/analyses')&&init?.method==='POST')return {ok:true,json:async()=>analysis};
  if(url.endsWith('/reports/generate')&&init?.method==='POST')return {ok:true,json:async()=>report};
  if(url.endsWith('/analyses/analysis-2/workbench-session'))return {ok:true,json:async()=>({url:'/cmpdi/workbench/analysis-2/'})};
  if(url.endsWith('/analyses'))return {ok:true,json:async()=>[]};
  return {ok:true,json:async()=>[]};
 });
 vi.stubGlobal('fetch',fetchMock);
 const {rerender}=render(<AnalyticsWorkspace token="token" entityCode="ECL" technical={false} view="analysis"/>);
 await waitFor(()=>expect(screen.getByText('Analytics ready')).toBeInTheDocument());
 fireEvent.click(screen.getByRole('button',{name:'Choose Data'}));
 fireEvent.click(await screen.findByRole('checkbox',{name:/production.csv/}));
 fireEvent.click(screen.getByRole('button',{name:/open selected data/i}));
 await waitFor(()=>expect(screen.getByTitle('CIL analytics workbench')).toHaveAttribute('src','/cmpdi/workbench/analysis-2/'));
 const workbench=screen.getByTitle('CIL analytics workbench') as HTMLIFrameElement;
 await act(async()=>{
  window.dispatchEvent(new MessageEvent('message',{origin:window.location.origin,source:workbench.contentWindow,data:{type:'cil-generate-report'}}));
 });
 await waitFor(()=>expect(screen.getByText('Report ready')).toBeInTheDocument());
 expect(fetchMock.mock.calls.some(([url,init])=>String(url).endsWith('/reports/generate')&&(init as RequestInit|undefined)?.method==='POST')).toBe(true);
 const sessionCalls=()=>fetchMock.mock.calls.filter(([url])=>String(url).endsWith('/analyses/analysis-2/workbench-session')).length;
 expect(sessionCalls()).toBe(1);
 rerender(<AnalyticsWorkspace token="token" entityCode="ECL" technical={false} view="vault"/>);
 expect(screen.getByTitle('CIL analytics workbench').closest('section')).toHaveAttribute('hidden');
 rerender(<AnalyticsWorkspace token="token" entityCode="ECL" technical={false} view="analysis"/>);
 expect(screen.getByTitle('CIL analytics workbench').closest('section')).not.toHaveAttribute('hidden');
 expect(sessionCalls()).toBe(1);
});

test('restores only the exact active analysis after a portal refresh',async()=>{
 const analysis={id:'analysis-saved',title:'Saved workspace',status:'ready',period:'',scope_entities:['ECL'],missing_entities:[],sources:[],target_entity:'ECL',target_family:'production_offtake',tables:[]};
 sessionStorage.setItem('cil.analytics.active.ECL',analysis.id);
 const fetchMock=vi.fn().mockImplementation(async(input:RequestInfo|URL)=>{
  const url=String(input);
  if(url.includes('/catalog'))return {ok:true,json:async()=>({files:[],folders:[],entities:['ECL'],root_label:'Data/cil'})};
  if(url.includes('/status'))return {ok:true,json:async()=>({online:true,models:[]})};
  if(url.endsWith('/analyses/analysis-saved/workbench-session'))return {ok:true,json:async()=>({url:'/cmpdi/workbench/analysis-saved/'})};
  if(url.endsWith('/analyses'))return {ok:true,json:async()=>[analysis]};
  return {ok:true,json:async()=>[]};
 });
 vi.stubGlobal('fetch',fetchMock);
 render(<AnalyticsWorkspace token="token" entityCode="ECL" technical={false} view="analysis"/>);
 await waitFor(()=>expect(screen.getByTitle('CIL analytics workbench')).toHaveAttribute('src','/cmpdi/workbench/analysis-saved/'));
});
