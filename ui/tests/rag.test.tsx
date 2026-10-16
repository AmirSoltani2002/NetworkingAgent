import {afterEach,test,expect,vi} from 'vitest';
import {render,screen,fireEvent,waitFor,within} from '@testing-library/react';
import {Connection} from '@/components/rag/connection';
import {Management,KnowledgeSearch} from '@/components/rag/management';
import {ragApi} from '@/lib/rag-api';
import type {Device,Issue,DocumentRecord,RagConnection} from '@/types/rag';
const device:Device={id:'device',name:'Device A',model:'X100',manufacturer:'Siemens',description:'Industrial device',metadata:{}};
const issue:Issue={id:'issue',device_id:'device',title:'Clicking during startup',category:'Sound',symptoms:'Clicking',possible_cause:'Relay',description:''};
const doc:DocumentRecord={id:'doc',title:'Maintenance Manual',document_type:'manual',version:'1',status:'ready',created_at:new Date().toISOString(),device_ids:['device'],metadata:{}};
const chunk={chunk_id:'chunk',document_id:'doc',document_title:doc.title,section_heading:'Troubleshooting',section_path:null,page_number:15,content:'Inspect the relay.'};
const row:RagConnection={id:'profile',name:'RAG',url:'http://rag-api:8090/mcp',restUrl:'http://rag-api:8090/',authEnvVar:'TOKEN',hasCredential:true,tools:[{name:'search_knowledge',description:'Search evidence',readOnly:true,inputSchema:{}}],allowedTools:[],status:'connected',restStatus:'connected',lastError:null,restError:null,serverName:'RAG',disconnected:false,agentEnabled:false};
function catalog(){vi.spyOn(ragApi,'catalog').mockImplementation(async(_id,path)=>path==='api/devices'?[device]:path==='api/issues'?[issue]:path.includes('/chunks')?[chunk]:[doc]);}
afterEach(()=>vi.useRealTimers());
test('connection form tests independent statuses and clears write-only token input',async()=>{
 const save=vi.spyOn(ragApi,'save');vi.spyOn(ragApi,'test').mockResolvedValue({mcpStatus:'connected',restStatus:'failed',mcpError:null,restError:'RAG authentication failed.',tools:row.tools,serverName:'RAG',retrievalAvailable:true});vi.spyOn(ragApi,'list').mockResolvedValue([row]);
 render(<Connection connection={row} onSaved={vi.fn()}/>);
 const token=screen.getByLabelText('Replace saved token (optional)');expect((token as HTMLInputElement).value).toBe('');fireEvent.change(token,{target:{value:'secret-never-shown'}});
 fireEvent.click(screen.getByRole('button',{name:'Test Connection'}));await screen.findByText('RAG authentication failed.');expect((token as HTMLInputElement).value).toBe('');expect(screen.getByText('search_knowledge')).toBeTruthy();expect(ragApi.test).toHaveBeenCalledWith(expect.objectContaining({token:'secret-never-shown'}),'profile');expect(save).not.toHaveBeenCalled();
});
test('connection save and permissions reuse the existing profile without revealing credentials',async()=>{
 vi.spyOn(ragApi,'save').mockResolvedValue(row);vi.spyOn(ragApi,'permissions').mockResolvedValue({...row,allowedTools:['search_knowledge'],agentEnabled:true});const saved=vi.fn();render(<Connection connection={row} onSaved={saved}/>);
 fireEvent.click(screen.getByRole('checkbox',{name:/search_knowledge/}));fireEvent.click(screen.getByRole('checkbox',{name:'Make allowed retrieval tools available to chat'}));fireEvent.click(screen.getByRole('button',{name:'Save tool permissions'}));await waitFor(()=>expect(ragApi.permissions).toHaveBeenCalledWith('profile',['search_knowledge'],true));
 fireEvent.click(screen.getByRole('button',{name:'Save Connection'}));await waitFor(()=>expect(ragApi.save).toHaveBeenCalled());expect(saved).toHaveBeenCalledWith(row);
});
test('device CRUD, filtering, counts and confirmed deletion use external operations',async()=>{
 catalog();vi.spyOn(ragApi,'operation').mockResolvedValue({deleted:true});render(<Management page="Devices" id="profile"/>);await screen.findByRole('cell',{name:'Device A'});expect(screen.getAllByRole('cell',{name:'1'})).toHaveLength(2);
 fireEvent.click(screen.getByRole('button',{name:'Add Device'}));const modal=screen.getByRole('dialog');for(const[label,value]of [['Name *','Device C'],['Model *','C100'],['Manufacturer *','Acme']])fireEvent.change(within(modal).getByLabelText(label),{target:{value}});fireEvent.click(within(modal).getByRole('button',{name:'Save'}));await waitFor(()=>expect(ragApi.operation).toHaveBeenCalledWith('profile','api/devices','POST',expect.objectContaining({name:'Device C'})));
 await waitFor(()=>expect(screen.queryByRole('dialog')).toBeNull());fireEvent.click(screen.getByRole('button',{name:'Delete'}));expect(ragApi.operation).not.toHaveBeenCalledWith('profile','api/devices/device','DELETE');fireEvent.click(screen.getByRole('button',{name:'Delete permanently'}));await waitFor(()=>expect(ragApi.operation).toHaveBeenCalledWith('profile','api/devices/device','DELETE'));
});
test('issue editing and explicit evidence search/linking use source passages',async()=>{
 catalog();vi.spyOn(ragApi,'operation').mockImplementation(async(_id,path,method)=>path.endsWith('/evidence')&&method==='GET'?{items:[]}:path==='api/retrieval/search'?{device_id:'device',matched_issues:[issue],results:[chunk]}:{});
 render(<Management page="Known Issues" id="profile"/>);await screen.findByRole('cell',{name:issue.title});fireEvent.click(screen.getByRole('button',{name:'Edit'}));fireEvent.change(screen.getByLabelText('Possible cause (unconfirmed)'),{target:{value:'Possible relay defect'}});fireEvent.click(screen.getByRole('button',{name:'Save'}));await waitFor(()=>expect(ragApi.operation).toHaveBeenCalledWith('profile','api/issues/issue','PUT',expect.objectContaining({possible_cause:'Possible relay defect'})));
 await waitFor(()=>expect(screen.queryByRole('dialog')).toBeNull());fireEvent.click(screen.getByRole('button',{name:'Evidence'}));fireEvent.click(await screen.findByRole('button',{name:'Add Evidence'}));fireEvent.change(screen.getByLabelText('Search query *'),{target:{value:'Clicking startup'}});fireEvent.click(screen.getByRole('button',{name:'Search Knowledge'}));fireEvent.click(await screen.findByRole('button',{name:'Select passage'}));fireEvent.click(screen.getByRole('button',{name:'Save Evidence Link'}));await waitFor(()=>expect(ragApi.operation).toHaveBeenCalledWith('profile','api/issues/issue/evidence','POST',{chunk_id:'chunk',evidence_type:'supporting_observation'}));
});
test('document uploads preserve associations and never perform indexing in the UI',async()=>{
 catalog();vi.spyOn(ragApi,'upload').mockResolvedValue({...doc,status:'uploaded'});render(<Management page="Documents" id="profile"/>);await screen.findByRole('cell',{name:doc.title});fireEvent.click(screen.getByRole('button',{name:'Upload Document'}));fireEvent.change(screen.getByLabelText('Document title *'),{target:{value:'Repair report'}});fireEvent.change(screen.getByLabelText('Document file *'),{target:{files:[new File(['# Manual'],'manual.md',{type:'text/markdown'})]}});fireEvent.click(screen.getByRole('checkbox',{name:'Device A X100'}));fireEvent.click(within(screen.getByRole('dialog')).getByRole('button',{name:'Upload Document'}));await waitFor(()=>expect(ragApi.upload).toHaveBeenCalled());const body=vi.mocked(ragApi.upload).mock.calls[0][1];expect(body.get('device_ids')).toBe('["device"]');expect((body.get('file') as File).name).toBe('manual.md');
});
test('knowledge search shows sources and empty results; timeout errors are actionable',async()=>{
 vi.spyOn(ragApi,'operation').mockResolvedValue({device_id:'device',matched_issues:[issue],results:[chunk]});render(<KnowledgeSearch id="profile" devices={[device]}/>);fireEvent.change(screen.getByLabelText('Search query *'),{target:{value:'Clicking'}});fireEvent.click(screen.getByRole('button',{name:'Search Knowledge'}));expect(await screen.findByText('Inspect the relay.')).toBeTruthy();expect(screen.getByText('Page 15')).toBeTruthy();expect(screen.getByText(/not diagnostic confidence probabilities/)).toBeTruthy();
 vi.mocked(ragApi.operation).mockResolvedValueOnce({device_id:null,matched_issues:[],results:[]});fireEvent.click(screen.getByRole('button',{name:'Search Knowledge'}));await screen.findByText(/No relevant passages found/);
 vi.mocked(ragApi.operation).mockRejectedValueOnce(new Error('RAG REST API timed out. Check the server connection.'));fireEvent.click(screen.getByRole('button',{name:'Search Knowledge'}));expect(await screen.findByRole('alert')).toBeTruthy();
});
test('document status polling stops when processing completes',async()=>{
 catalog();vi.mocked(ragApi.catalog).mockImplementation(async(_id,path)=>path==='api/devices'?[device]:path==='api/issues'?[issue]:[{...doc,status:'processing'}]);vi.spyOn(ragApi,'operation').mockResolvedValue({id:'doc',status:'ready'});
 render(<Management page="Documents" id="profile"/>);await screen.findByRole('cell',{name:'processing'});await waitFor(()=>expect(screen.getByRole('cell',{name:'ready'})).toBeTruthy(),{timeout:4500});expect(ragApi.operation).toHaveBeenCalledTimes(1);
});
test('edited endpoint drafts cannot change saved-profile agent permissions',()=>{
 vi.spyOn(ragApi,'permissions');render(<Connection connection={row} onSaved={vi.fn()}/>);fireEvent.change(screen.getByLabelText('MCP server URL *'),{target:{value:'http://other-server:8090/mcp'}});const button=screen.getByRole('button',{name:'Save tool permissions'}) as HTMLButtonElement;expect(button.disabled).toBe(true);fireEvent.click(button);expect(ragApi.permissions).not.toHaveBeenCalled();
});
