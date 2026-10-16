import {test,expect,vi} from 'vitest';
import {render,screen,fireEvent} from '@testing-library/react';
import {App} from '@/App';
import {chatApi} from '@/lib/api';
import {newerSnapshot} from '@/lib/factory-api';
import type {FactoryState} from '@/types/factory';
vi.mock('@/components/llm/llm-settings',()=>({LlmSettings:()=> <div>LLM</div>}));
vi.mock('@/components/factory/factory-workspace',()=>({FactoryWorkspace:()=> <h1>Factory Simulation</h1>}));
test('factory navigation preserves the original chat draft, composer and independent Chats collapse',async()=>{
 vi.spyOn(chatApi,'list').mockResolvedValue([]);render(<App/>);
 fireEvent.change(screen.getByLabelText('Message'),{target:{value:'Analyze current gearbox condition'}});
 fireEvent.click(screen.getByRole('button',{name:'Factory Simulation'}));expect(screen.getByRole('heading',{name:'Factory Simulation'})).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'← Back to chat'}));expect((screen.getByLabelText('Message') as HTMLTextAreaElement).value).toBe('Analyze current gearbox condition');expect(screen.getByRole('button',{name:'Add files'})).toBeTruthy();
 fireEvent.click(screen.getByRole('button',{name:'FACTORY'}));expect(screen.getByRole('button',{name:'Chats'}).getAttribute('aria-expanded')).toBe('true');
});
test('WebSocket full snapshots ignore duplicates/out-of-order versions and accept refreshed epochs',()=>{
 const s={version:12,epoch:'first'} as FactoryState;expect(newerSnapshot(s,{version:11} as FactoryState)).toBe(s);expect(newerSnapshot(s,s)).toBe(s);expect(newerSnapshot(s,{version:13,epoch:'second'} as FactoryState).epoch).toBe('second');
});
