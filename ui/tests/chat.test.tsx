import {test,vi,expect} from 'vitest';
import {render,screen,fireEvent,waitFor} from '@testing-library/react';
import {App} from '@/App';
import {chatApi} from '@/lib/api';
import {ragApi} from '@/lib/rag-api';
vi.mock('@/components/llm/llm-settings',()=>({LlmSettings:()=> <div>LLM</div>}));
test('existing chat draft and file controls survive management navigation; compact MCP section is available',async()=>{
 vi.spyOn(chatApi,'list').mockResolvedValue([]);vi.spyOn(ragApi,'list').mockResolvedValue([]);render(<App/>);fireEvent.change(screen.getByLabelText('Message'),{target:{value:'Unsent chat draft'}});fireEvent.click(screen.getByRole('button',{name:'Connection'}));await screen.findByRole('heading',{name:'Connection'});expect(screen.getByRole('button',{name:'MCP'})).toBeTruthy();expect(screen.queryByRole('button',{name:'Send message'})).toBeNull();fireEvent.click(screen.getByRole('button',{name:'← Back to chat'}));expect((screen.getByLabelText('Message')as HTMLTextAreaElement).value).toBe('Unsent chat draft');expect(screen.getByRole('button',{name:'Add files'})).toBeTruthy();
});
test('plain chat still saves user text, auto title and assistant reply',async()=>{
 const chat={id:'chat',title:'Hello',createdAt:'',updatedAt:''};vi.spyOn(chatApi,'list').mockResolvedValue([]);vi.spyOn(chatApi,'create').mockResolvedValue(chat);vi.spyOn(chatApi,'send').mockResolvedValue({chat,message:{id:'user',role:'user',replyToMessageId:null,text:'Hello',attachments:[]}});vi.spyOn(chatApi,'respond').mockResolvedValue({chat,message:{id:'reply',role:'assistant',replyToMessageId:'user',text:'Hi there',attachments:[]}});render(<App/>);fireEvent.change(screen.getByLabelText('Message'),{target:{value:'Hello'}});fireEvent.click(screen.getByRole('button',{name:'Send message'}));await screen.findByText('Hi there');await waitFor(()=>expect((screen.getByLabelText('Message')as HTMLTextAreaElement).value).toBe(''));expect(chatApi.respond).toHaveBeenCalledWith('chat','user');
});
test('chat automatically requests the next prompt after each budget checkpoint and saves only the final visible reply',async()=>{
 const chat={id:'chat',title:'Continue',createdAt:'',updatedAt:''};
 vi.spyOn(chatApi,'list').mockResolvedValue([]);vi.spyOn(chatApi,'create').mockResolvedValue(chat);
 vi.spyOn(chatApi,'send').mockResolvedValue({chat,message:{id:'user',role:'user',replyToMessageId:null,text:'Continue',attachments:[]}});
 vi.spyOn(chatApi,'respond').mockResolvedValueOnce({chat,continuation:{reason:'model_turns'}}).mockResolvedValueOnce({chat,continuation:{reason:'tool_calls'}}).mockResolvedValueOnce({chat,continuation:{reason:'deadline'}}).mockResolvedValueOnce({chat,message:{id:'reply',role:'assistant',replyToMessageId:'user',text:'Work finished',attachments:[]}});
 render(<App/>);fireEvent.change(screen.getByLabelText('Message'),{target:{value:'Continue'}});fireEvent.click(screen.getByRole('button',{name:'Send message'}));
 await screen.findByText('Work finished');expect(chatApi.respond).toHaveBeenCalledTimes(4);expect(chatApi.send).toHaveBeenCalledTimes(1);
});
test('automatic continuation stops at state-changing tool confirmation without calling the confirmation endpoint',async()=>{
 const chat={id:'chat',title:'Train',createdAt:'',updatedAt:''};
 vi.spyOn(chatApi,'list').mockResolvedValue([]);vi.spyOn(chatApi,'create').mockResolvedValue(chat);
 vi.spyOn(chatApi,'send').mockResolvedValue({chat,message:{id:'user',role:'user',replyToMessageId:null,text:'Train',attachments:[]}});
 vi.spyOn(chatApi,'respond').mockResolvedValueOnce({chat,continuation:{reason:'tool_calls'}}).mockResolvedValueOnce({chat,pendingConfirmation:{id:'permission',serverId:'server',serverName:'Model',tool:'train',arguments:{},expiresAt:'2099-01-01T00:00:00Z'}});
 vi.spyOn(chatApi,'confirm');render(<App/>);fireEvent.change(screen.getByLabelText('Message'),{target:{value:'Train'}});fireEvent.click(screen.getByRole('button',{name:'Send message'}));
 await screen.findByRole('button',{name:'Confirm and run'});expect(chatApi.respond).toHaveBeenCalledTimes(2);expect(chatApi.confirm).not.toHaveBeenCalled();
});
test('a consumed confirmation is cleared after checkpoint so later connection failure permits response retry',async()=>{
 const chat={id:'chat',title:'Train',createdAt:'',updatedAt:''};
 vi.spyOn(chatApi,'list').mockResolvedValue([]);vi.spyOn(chatApi,'create').mockResolvedValue(chat);
 vi.spyOn(chatApi,'send').mockResolvedValue({chat,message:{id:'user',role:'user',replyToMessageId:null,text:'Train',attachments:[]}});
 vi.spyOn(chatApi,'respond').mockResolvedValueOnce({chat,pendingConfirmation:{id:'permission',serverId:'server',serverName:'Model',tool:'train',arguments:{},expiresAt:'2099-01-01T00:00:00Z'}}).mockRejectedValueOnce(new Error('Connection failed'));
 vi.spyOn(chatApi,'confirm').mockResolvedValueOnce({chat,continuation:{reason:'deadline'}});
 render(<App/>);fireEvent.change(screen.getByLabelText('Message'),{target:{value:'Train'}});fireEvent.click(screen.getByRole('button',{name:'Send message'}));
 fireEvent.click(await screen.findByRole('button',{name:'Confirm and run'}));
 await screen.findByText(/Connection failed/);expect(screen.queryByRole('button',{name:'Confirm and run'})).toBeNull();expect(screen.getByRole('button',{name:'Retry response'})).toBeTruthy();expect(chatApi.confirm).toHaveBeenCalledTimes(1);
});
