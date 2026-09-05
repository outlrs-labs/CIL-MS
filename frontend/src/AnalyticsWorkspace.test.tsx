import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,vi} from 'vitest';
import {AnalyticsWorkspace} from './AnalyticsWorkspace';

afterEach(()=>vi.unstubAllGlobals());

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

test('requires a category before sending a saved report to subsidiary audit',async()=>{
 const report={id:'report-1',title:'September summary',created:1,series:'series-1',version:2,previous_id:null,entity:'ECL',family:'production_offtake',can_submit:true,audit_status:null};
 const fetchMock=vi.fn().mockImplementation(async(input:RequestInfo|URL,init?:RequestInit)=>{
  const url=String(input);
  if(url.includes('/catalog'))return {ok:true,json:async()=>({files:[],folders:[],entities:['ECL'],root_label:'Data/cil'})};
  if(url.includes('/status'))return {ok:true,json:async()=>({online:false,models:[]})};
  if(url.endsWith('/reports')&&(!init?.method||init.method==='GET'))return {ok:true,json:async()=>[report]};
  if(url.endsWith('/reports/report-1/audit'))return {ok:true,json:async()=>({status:'pending_review'})};
  return {ok:true,json:async()=>[]};
 });
 vi.stubGlobal('fetch',fetchMock);
 if(!HTMLDialogElement.prototype.showModal)Object.defineProperty(HTMLDialogElement.prototype,'showModal',{configurable:true,value:function(this:HTMLDialogElement){this.open=true}});
 if(!HTMLDialogElement.prototype.close)Object.defineProperty(HTMLDialogElement.prototype,'close',{configurable:true,value:function(this:HTMLDialogElement){this.open=false}});
 render(<AnalyticsWorkspace token="token" entityCode="ECL" technical={false} view="analysis"/>);
 await waitFor(()=>expect(fetchMock).toHaveBeenCalledTimes(4));
 fireEvent.click(screen.getByRole('button',{name:'Send report for audit'}));
 fireEvent.click(await screen.findByRole('button',{name:'Choose category'}));
 fireEvent.change(screen.getByRole('combobox',{name:/^Report category/}),{target:{value:'financial'}});
 fireEvent.click(screen.getByRole('button',{name:'Send to subsidiary audit'}));
 await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith('/api/analytics/reports/report-1/audit',expect.objectContaining({method:'POST',body:JSON.stringify({category:'financial'})})));
});
