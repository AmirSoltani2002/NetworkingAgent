import Phaser from 'phaser';
import type {FactoryState} from '@/types/factory';
// Original procedural artwork inspired by both user-supplied side-view references.
// Rendering never writes machine state or generates observations.
const C={ink:0x102b36,wall:0x215462,panel:0x2b6370,metal:0xc9dadb,light:0xecf2e9,teal:0x55b4b6,orange:0xf2b25c,floor:0x173d4c,green:0x67edb5,red:0xf57279};
export class FactoryScene extends Phaser.Scene{
 state:FactoryState|null=null;private moving!:Phaser.GameObjects.Graphics;private labels:Phaser.GameObjects.Text[]=[];private technicianX=1100;private received=0;
 constructor(private readonly select:(id:string)=>void){super('factory');}
 setFactoryState(s:FactoryState){if(!this.state||this.state.epoch!==s.epoch)this.technicianX=s.technician.x;this.state=s;this.received=performance.now();}
 create(){
  const g=this.add.graphics();
  g.fillStyle(C.wall);g.fillRect(0,0,1280,640);
  for(let y=0;y<500;y+=100)for(let x=0;x<1280;x+=160){g.fillStyle((x/160+y/100)%2?0x245967:0x225563);g.fillRect(x+2,y+2,156,96);g.lineStyle(1,0x337080,.6);g.strokeRect(x+1,y+1,158,98);}
  g.fillStyle(C.floor);g.fillRect(0,470,1280,170);g.fillStyle(0x122f3e);g.fillRect(0,610,1280,30);
  for(let y=490;y<620;y+=42){g.lineStyle(1,0x31606b,.5);g.lineBetween(0,y,1280,y);}
  for(let x=0;x<1280;x+=160){g.lineStyle(1,0x31606b,.5);g.lineBetween(x,470,x-150,640);}
  // Ceiling lighting and utility runs, visually distinct from process flow.
  for(const x of [140,515,900]){this.box(g,x,35,230,13,0x133542);this.box(g,x+9,38,212,5,0x89c5c4);g.fillStyle(0x83d7cc,.035);g.fillTriangle(x,50,x+230,50,x+350,465);}
  for(const y of [95,120]){g.lineStyle(9,C.ink);g.strokePoints([{x:0,y},{x:70,y},{x:70,y:y+65},{x:340,y:y+65},{x:340,y:40}],false);g.lineStyle(4,0x689e9e);g.strokePoints([{x:0,y},{x:70,y},{x:70,y:y+65},{x:340,y:y+65},{x:340,y:40}],false);}
  g.lineStyle(8,C.ink);g.strokePoints([{x:1200,y:0},{x:1200,y:180},{x:1040,y:180},{x:1040,y:235}],false);g.lineStyle(3,0xefa956);g.strokePoints([{x:1200,y:0},{x:1200,y:180},{x:1040,y:180},{x:1040,y:235}],false);
  // Storage, chiller and isolated electrical enclosure in the background.
  this.box(g,30,300,80,166,0x739f9d);for(let y=320;y<455;y+=35)this.box(g,40,y,60,25,0x375f67);
  this.box(g,910,175,100,158,0x91bfbb);this.box(g,922,189,76,42,0x376574);for(let x=930;x<990;x+=12)this.box(g,x,245,6,45,0x486976);
  this.text('COOLING UNIT',960,159,12,0xb1d9d5).setOrigin(.5);
  // Raised base, feet and striped inspection boundary.
  g.fillStyle(0x071f2b,.45);g.fillEllipse(646,488,1110,75);
  this.box(g,140,425,738,28,0x416d77);for(const x of [160,305,480,665,835]){this.box(g,x,453,20,25,0x254956);this.box(g,x-6,475,32,7,0x90a5a0);}
  g.lineStyle(3,0xdba956,.7);g.strokeRoundedRect(125,481,1070,85,12);g.fillStyle(0xdba956,.7);for(let x=145;x<1200;x+=33)g.fillRect(x,483,13,3);
  // Motor cooling fins and driven shaft.
  this.box(g,136,317,119,96,C.teal);this.box(g,128,328,20,72,0x417c87);for(let x=156;x<240;x+=13)this.box(g,x,327,5,69,0x326c78);
  this.box(g,252,346,28,24,C.orange);this.box(g,270,335,92,68,0xa1b9ba);this.box(g,282,321,68,15,C.metal);
  this.box(g,363,345,60,24,C.orange);
  // Feed hopper above barrel entry.
  g.lineStyle(4,C.ink);g.fillStyle(C.light);g.fillPoints([{x:380,y:170},{x:500,y:170},{x:466,y:258},{x:414,y:258}],true);g.strokePoints([{x:380,y:170},{x:500,y:170},{x:466,y:258},{x:414,y:258}],true);
  this.box(g,375,159,130,17,C.teal);this.box(g,422,257,36,55,0xb1c6c6);this.box(g,410,294,60,25,C.orange);this.box(g,400,318,86,28,C.metal);
  // Barrel blocks, insulated zones, heating bands, fasteners.
  for(let i=0;i<6;i++){const x=430+i*61;this.box(g,x,330,59,68,i%2?0xcedbd5:0xe3e8db);this.box(g,x+4,320,50,10,C.orange);this.box(g,x+4,393,50,11,0x70a7ab);this.box(g,x+18,341,20,20,0x8badae);for(const y of [336,390]){g.fillStyle(C.ink);g.fillCircle(x+7,y,2);g.fillCircle(x+51,y,2);}}
  // Twin screws are a schematic cutaway, not a manufacturer's drawing.
  this.box(g,442,367,340,18,0x284e5c);
  this.box(g,801,335,28,59,0xdda552);this.box(g,826,352,31,25,0x9ab8b8);this.box(g,851,358,19,13,C.orange);
  // Conveyor assembly.
  this.box(g,882,400,299,24,0x7d9da2);this.box(g,886,392,291,10,0x1c454f);for(const x of [900,1145]){this.box(g,x,425,13,57,C.metal);this.box(g,x-8,478,29,8,0x788e90);}
  for(let x=901;x<1170;x+=23){g.lineStyle(2,C.ink);g.strokeCircle(x,411,6);}
  // HMI and signal tower.
  this.box(g,1066,235,116,130,0xbacdcc);this.box(g,1077,247,93,69,0x0c303e);this.box(g,1108,365,25,112,0x749aa2);this.box(g,1080,476,81,9,0x96b4b5);
  this.box(g,1121,182,14,51,0x466b74);for(let i=0;i<3;i++)this.box(g,1116,178+i*16,24,13,0x548276);
  this.text('ZSK  •  CO-ROTATING TWIN-SCREW',36,208,19,0xcde9e4);
  this.text('SYNTHETIC PROCESS / SIMULATION ONLY',36,234,11,0x84b7ba);
  for(const [name,x,y] of [['MAIN DRIVE',195,294],['GEARBOX',318,296],['METERED FEED',441,132],['HEATING / COOLING ZONES',646,285],['DIE',829,305],['OUTPUT CONVEYOR',1027,455]] as [string,number,number][]){this.text(name,x,y,11,0xb6dcda).setOrigin(.5);}
  const positions=[['motor',136,317,120,96],['gearbox',270,320,95,87],['hopper',375,157,130,100],['feeder',402,257,85,89],['barrel',428,320,372,87],['cooling',510,275,220,44],['die',800,331,72,65],['conveyor',880,390,300,44],['control',1066,235,116,130]] as [string,number,number,number,number][];
  for(const [id,x,y,w,h] of positions){const hit=this.add.zone(x+w/2,y+h/2,w,h).setInteractive({useHandCursor:true});hit.on('pointerdown',()=>this.select(id));}
  this.moving=this.add.graphics();
  this.labels=[this.text('Awaiting authoritative state…',36,65,13,0xc4ede6),this.text('',1087,259,13,0x64e0b2),this.text('',1087,284,11,0x9fccc8),this.text('TECHNICIAN',1100,551,10,0xaed4d0).setOrigin(.5)];
 }
 private text(text:string,x:number,y:number,size:number,color:number){return this.add.text(x,y,text,{fontFamily:'Ubuntu, Arial, sans-serif',fontSize:size,color:'#'+color.toString(16).padStart(6,'0'),fontStyle:size>=18?'bold':'normal'});}
 private box(g:Phaser.GameObjects.Graphics,x:number,y:number,w:number,h:number,color:number){g.fillStyle(C.ink);g.fillRoundedRect(x-2,y-2,w+4,h+4,5);g.fillStyle(color);g.fillRoundedRect(x,y,w,h,3);g.fillStyle(0xffffff,.15);g.fillRect(x+3,y+2,w-6,3);g.fillStyle(0x071e2b,.15);g.fillRect(x+2,y+h-6,w-4,4);}
 update(_time:number,delta:number){
  if(!this.moving||!this.state)return;const s=this.state,g=this.moving;g.clear();
  const fresh=Math.min((performance.now()-this.received)/1000,1);const elapsed=s.clock.elapsed_seconds+(s.clock.paused?0:fresh*s.clock.speed);const running=['RUNNING','STOPPING'].includes(s.mode)&&!s.clock.paused;const phase=elapsed;
  const alarmColor=s.condition==='FAULT'?C.red:s.condition==='WARNING'?C.orange:C.green;
  this.labels[0].setText(`${s.machine_id}    /    ${s.mode}    /    ${s.clock.paused?'CLOCK PAUSED':s.clock.speed+'× SIMULATION TIME'}`);
  this.labels[1].setText(s.mode);this.labels[2].setText(`${s.condition}\n${s.latest_measurement?Number(s.latest_measurement.screw_torque_pct).toFixed(1):'—'}% TORQUE`);
  g.fillStyle(alarmColor,.12);g.fillCircle(1128,188,19);g.fillStyle(alarmColor);g.fillRoundedRect(1118,181,20,10,3);
  if(s.condition!=='NORMAL'&&Math.sin(phase*2)>0){const target=s.components.find(c=>c.id===(s.alarms[0]?.component??'gearbox'));if(target){g.lineStyle(3,alarmColor,.8);g.strokeRoundedRect(target.x-51,target.y-47,102,91,9);}}
  // Animated gear teeth, paired screw helixes, pellets and conveyor parcels.
  for(let i=0;i<12;i++){const angle=i*Math.PI/6+(running?phase*.8:0);g.lineStyle(5,0x4f8186);g.lineBetween(316+Math.cos(angle)*15,368+Math.sin(angle)*15,316+Math.cos(angle)*25,368+Math.sin(angle)*25);}
  g.fillStyle(0x416973);g.fillCircle(316,368,19);g.lineStyle(3,C.ink);g.strokeCircle(316,368,19);g.fillStyle(C.orange);g.fillCircle(316,368,7);
  for(let x=451;x<779;x+=16){const shift=running?Math.sin(phase*2+x)*4:0;g.lineStyle(2,0x8ec6c5);g.lineBetween(x+shift,369,x+7+shift,381);}
  for(let i=0;i<10;i++){const q=running?(phase*.035+i*.1)%1:i*.1;g.fillStyle(C.orange);g.fillCircle(404+(i%4)*22,179+q*61,3);}
  for(let i=0;i<7;i++){const q=running?(phase*.022+i/7)%1:i/7;g.fillStyle(0xffce7c);g.fillRoundedRect(894+q*266,378,15,12,3);g.lineStyle(2,0x14424e);g.lineBetween(891+q*268,395,899+q*268,401);}
  if(running){g.lineStyle(4,0xe5b36b);g.lineBetween(868,364,900,387);g.fillStyle(C.green);g.fillCircle(152,408,4);}
  // Technician position is interpolated toward backend-confirmed coordinates.
  this.technicianX=Phaser.Math.Linear(this.technicianX,s.technician.x,Math.min(1,delta/150));const x=this.technicianX,y=s.technician.y;const walking=s.technician.mode==='WALKING';const stride=walking&&!s.clock.paused?Math.sin(phase*3)*5:0;
  g.fillStyle(0x071f2b,.4);g.fillEllipse(x,y+50,52,14);
  this.box(g,x-11,y+24,9,23+stride,0x284951);this.box(g,x+3,y+24,9,23-stride,0x284951);this.box(g,x-13,y+45+stride,14,6,0x122e3d);this.box(g,x+3,y+45-stride,14,6,0x122e3d);
  this.box(g,x-14,y-8,29,35,0xdd9e52);this.box(g,x-11,y+10,23,8,0xf4d791);g.fillStyle(0xdcc4a0);g.fillCircle(x,y-19,12);this.box(g,x-15,y-31,30,10,C.orange);this.box(g,x-18,y-23,36,5,C.orange);
  const working=['INSPECTING','MAINTENANCE'].includes(s.technician.mode);g.lineStyle(7,0xdd9e52);g.lineBetween(x-13,y,x-20,y+16);g.lineBetween(x+15,y,x+25,y+(working?Math.sin(phase*2)*6:-2));g.lineStyle(3,C.metal);g.lineBetween(x+24,y-4,x+35,y-11);
  if(working){g.fillStyle(C.teal,.2);g.fillCircle(x+35,y-14,17);g.lineStyle(2,C.teal);g.strokeCircle(x+35,y-14,10);}
  this.labels[3].setPosition(x,y+69).setText(s.technician.mode==='IDLE'?'TECHNICIAN':s.technician.mode);
 }
}
