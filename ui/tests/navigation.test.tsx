import {test,expect,vi} from 'vitest';
import {render,screen,fireEvent} from '@testing-library/react';
import {RagNavigation} from '@/components/rag/rag-navigation';
test('RAG is independently collapsible and navigates to main-area destinations',()=>{
 const navigate=vi.fn(); render(<RagNavigation page="Devices" onNavigate={navigate}/>);
 expect(screen.getByRole('button',{name:'Devices'}).getAttribute('aria-current')).toBe('page');
 fireEvent.click(screen.getByRole('button',{name:'Connection'}));expect(navigate).toHaveBeenCalledWith('Connection');
 fireEvent.click(screen.getByRole('button',{name:'RAG'}));expect(screen.queryByRole('button',{name:'Devices'})).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'RAG'}));expect(screen.getByRole('button',{name:'Documents'})).toBeTruthy();
});
