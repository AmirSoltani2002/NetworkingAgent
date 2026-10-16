import {useEffect,useRef} from 'react';
import Phaser from 'phaser';
import {FactoryScene} from './factory-scene';
import type {FactoryState} from '@/types/factory';
export default function FactoryCanvas({state,onSelect}:{state:FactoryState;onSelect:(id:string)=>void}){
 const host=useRef<HTMLDivElement>(null),scene=useRef<FactoryScene|null>(null),select=useRef(onSelect);useEffect(()=>{select.current=onSelect;},[onSelect]);
 useEffect(()=>{if(!host.current)return;const view=new FactoryScene(id=>select.current(id));scene.current=view;const game=new Phaser.Game({type:Phaser.AUTO,parent:host.current,width:1280,height:640,backgroundColor:'#215462',scene:view,scale:{mode:Phaser.Scale.FIT,autoCenter:Phaser.Scale.CENTER_BOTH},render:{antialias:true},audio:{noAudio:true}});return()=>{scene.current=null;game.destroy(true);};},[]);
 useEffect(()=>{scene.current?.setFactoryState(state);},[state]);
 return <div ref={host} className="factory-canvas" role="img" aria-label={`Animated ZSK extrusion line, ${state.mode}. Click a component to inspect its details.`}/>;
}
