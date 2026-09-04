import {render,waitFor} from '@testing-library/react';
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
