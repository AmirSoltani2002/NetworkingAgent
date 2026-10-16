import {Body,Controller,Get,Headers,Param,Post,Query,BadRequestException} from '@nestjs/common';
import {requireLocalOrigin} from '../config/local-origin';
import {object,text,uuid} from '../tasks/task-contract';
import {FactoryService} from './factory.service';
@Controller('factory')
export class FactoryController{
 constructor(private readonly factory:FactoryService){}
 @Get('state')state(@Headers('origin') origin?:string){requireLocalOrigin(origin);return this.factory.request('state');}
 @Get('measurements')measurements(@Query() query:Record<string,unknown>,@Headers('origin') origin?:string){requireLocalOrigin(origin);const params=new URLSearchParams();for(const [k,v] of Object.entries(query)){if(!['start_time','end_time','limit'].includes(k)||typeof v!=='string'||v.length>100)throw new BadRequestException('Invalid measurement filter');params.set(k,v);}return this.factory.request('measurements?'+params);}
 @Get('actions/:id')status(@Param('id') id:string,@Headers('origin') origin?:string){requireLocalOrigin(origin);uuid(id);return this.factory.request('actions/'+id);}
 @Post('actions')action(@Body() raw:unknown,@Headers('origin') origin?:string){
  requireLocalOrigin(origin);const b=object(raw);if(Object.keys(b).some(k=>!['kind','arguments','idempotency_key'].includes(k)))throw new BadRequestException('Unknown factory field');
  text(b.idempotency_key,160);const kind=text(b.kind,40),args=object(b.arguments);
  const fields:Record<string,string[]>={clock:['paused','speed','automatic_faults'],fault:['fault_id','mode','duration_minutes'],stop:['machine_id'],start:['machine_id'],reset:[],inspect:['component_id'],maintenance:['machine_id','component_id','maintenance_action'],acknowledge:['alarm_id']};
  if(!fields[kind]||Object.keys(args).some(k=>!fields[kind].includes(k))||JSON.stringify(args).length>2000)throw new BadRequestException('Unknown simulation action/arguments');
  return this.factory.request('actions','POST',b);
 }
}
