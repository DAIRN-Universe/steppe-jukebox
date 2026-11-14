/* Loading and metadata bridge for the existing one-clock route player. */
window.LivePlayerSession = class {
  constructor(hooks){
    this.hooks=hooks;this.ready=false;this.loading=false;this.maps=new Map();this.active=null;
    this.inFlight=null;this.queue=[];this.timer=null;this.dates=[];this.request=null;
    this.map=new window.LiveGridMap();
    this.inspected=null;this.map.onSelect=index=>this.inspect(index);
    const $=id=>document.getElementById(id);this.$=$;
    $('provider').addEventListener('change',()=>this.selection());
    $('observation-date').addEventListener('change',()=>this.selection());
    $('eic-date').addEventListener('change',()=>{$('observation-date').value=$('eic-date').value;this.selection();});
    $('load-data').addEventListener('click',()=>this.load());
    $('clear-live-cache').addEventListener('click',()=>{this.invalidate();this.active=this.command('clear',{source:this.provider()});if(this.provider()==='eic')this.dates=[];this.refresh();});
    $('refresh-eic-dates').addEventListener('click',()=>this.command('refresh_catalog'));
    for(const id of ['live-snow','live-water','live-temperature'])$(id).addEventListener('change',()=>this.selection());
  }
  command(type,fields={}){
    const id=crypto.randomUUID();this.queue.push({id,type,...fields});this.dispatch();return id;
  }
  dispatch(){if(this.inFlight!==null||!this.queue.length)return;const command=this.queue.shift();this.inFlight=command.id;
    parent.postMessage({isStreamlitMessage:true,type:'streamlit:setComponentValue',dataType:'json',value:command},'*');}
  day(){return this.$('observation-date').value;}
  provider(){return this.$('provider').value;}
  placeholder(data,mode){
    const base=mode==='journey'?data.journey:data.seasons[0];
    return {...base,date:this.day(),audio_src:null,intervals:base.intervals.map(slot=>({...slot,date:mode==='journey'?slot.date:this.day()})),
      source_url:this.provider()==='gibs'?'https://gibs.earthdata.nasa.gov/layer-metadata/v1.0/VIIRS_NOAA20_NDVI_8Day.json':'https://svs.gsfc.nasa.gov/5544/'};
  }
  invalidate(){
    this.inspected=null;this.$('live-inspector').hidden=true;
    clearTimeout(this.timer);this.ready=false;this.loading=false;this.maps.clear();this.request=null;
    this.active=this.command('invalidate');this.hooks.reset();this.hooks.prepare();this.refresh();
  }
  selection(){this.hooks.selection();}
  load(){
    if(!this.day())return;this.invalidate();this.loading=true;
    this.active=this.command('load',{source:this.provider(),region:this.hooks.region(),mode:this.hooks.mode(),date:this.day(),
      snow:this.$('live-snow').checked,water:this.$('live-water').checked,temperature:this.$('live-temperature').checked});
    this.refresh();
  }
  accept(payload){
    if(payload.ack===this.inFlight){this.inFlight=null;this.dispatch();}
    const request=payload.request;
    if(request&&request.id===this.active){
      this.request=request;this.loading=request.state==='loading';
      if(request.available_dates?.length)this.dates=request.available_dates;
      for(const slice of request.maps||[])this.maps.set(slice.date,slice);
      if(request.track&&!this.ready){this.ready=true;this.hooks.track(request.track);}
      else this.hooks.redraw();
      clearTimeout(this.timer);
      if(this.loading&&this.inFlight===null&&!this.queue.length){
        const id=this.active;this.timer=setTimeout(()=>{if(id===this.active)this.command('poll',{known:Object.fromEntries([...this.maps].map(([day,m])=>[day,m.version]))});},300);
      }
    }
    if(Array.isArray(payload.catalog_dates))this.dates=payload.catalog_dates;
    this.$('catalog-error').hidden=!payload.catalog_error;
    this.refresh();
  }
  slice(day){return this.maps.get(day);}
  inspect(index){
    this.inspected=index;const t=this.hooks.text,frame=this.slice(this.hooks.currentDate()),point=frame?.points[index];
    this.$('live-inspector').hidden=false;
    if(!point){this.$('live-pixel').textContent=t('live_choose');return;}
    const coordinate=value=>Number(value).toLocaleString(document.documentElement.lang,{maximumFractionDigits:5});
    const tile=frame.tiles.find(tile=>frame.source==='eic'||(tile.row===point.row&&tile.col===point.col));
    const note=point.ndvi_class?t('class_note',{value:point.ndvi_class,note:['C4','D4','E4','G4','A4'][point.ndvi_class-1]}):
      ['transparent','no_data'].includes(point.status)?t('missing_rest'):t('live_status_'+point.status);
    this.$('live-pixel').textContent=`${point.cell_id} · ${coordinate(point.lat)}°, ${coordinate(point.lon)}° · ${note} · ${frame.source.toUpperCase()} · ${t('live_actual')}: ${tile?.metadata.actual_date||'—'}`;
  }
  refresh(){
    if(!this.hooks.text)return;const t=this.hooks.text,$=this.$;
    $('live-controls').hidden=false;$('season-field').hidden=true;$('date-field').hidden=this.hooks.mode()==='journey';
    $('load-data').disabled=this.loading;$('toggle').disabled=!this.ready;$('restart').disabled=!this.ready;
    $('timing-details').hidden=!this.ready;
    const eic=this.provider()==='eic',select=$('eic-date');
    $('observation-date').hidden=eic&&this.dates.length>0;select.hidden=!eic||!this.dates.length;
    $('date-field').querySelector('label').htmlFor=eic&&this.dates.length?'eic-date':'observation-date';
    const signature=(eic?'eic':'gibs')+this.day()+this.dates.join(',');
    if(eic&&this.dates.length&&signature!==this.dateSignature){const day=this.day();select.replaceChildren();
      if(!this.dates.includes(day)){const o=document.createElement('option');o.value=day;o.textContent=day+' · '+t('live_unavailable');select.append(o);}
      for(const value of this.dates){const o=document.createElement('option');o.value=value;o.textContent=value;select.append(o);}select.value=day;this.dateSignature=signature;}
    $('live-layers').hidden=eic;
    $('refresh-eic-dates').hidden=!eic;
    $('provider-method').textContent=t(eic?'live_eic_method':'live_gibs_method');
    $('scale-details').querySelector('a').href=eic?'https://svs.gsfc.nasa.gov/vis/a000000/a005500/a005544/NDVI_colorbar.png':'https://gibs.earthdata.nasa.gov/colormaps/v1.3/MODIS_NDVI.xml';
    const request=this.request;
    let message=t(this.loading?'live_loading':this.ready?'live_ready':'live_choose');
    if(request?.error)message=t('live_'+request.error)+(request.missing_dates?.length?' '+request.missing_dates.slice(0,3).join(', ')+(request.missing_dates.length>3?' …':''):'');
    else if(request?.tile_errors)message=t('live_partial');
    if(this.loading&&request)message+=' '+request.completed_dates+'/'+request.total_dates;
    $('load-state').textContent=message;$('load-state').dataset.error=String(Boolean(request?.error||request?.tile_errors));
    if(!this.ready)$('status').textContent=message;
    $('live-counts').textContent=request?t('live_counts',{network:request.network_requests,completed:request.completed_dates,total:request.total_dates}):'';
    $('missing-frame-dates').textContent=request?.missing_dates?.join(', ')||'';
    $('live-point-errors').textContent=(request?.route_errors||[]).map(point=>`${point.cell_id} · ${point.date} · ${t('live_status_'+point.status)}`).join('; ');
    $('live-cache-path').textContent=this.provider()==='gibs'?this.cache?.gibs||'':this.cache?.eic||'';
    const frame=this.hooks.currentDate?this.slice(this.hooks.currentDate()):null;
    const tbody=$('live-requests').querySelector('tbody');tbody.replaceChildren();
    for(const tile of frame?.tiles||[]){const row=document.createElement('tr');
      for(const value of [tile.layer,tile.date,tile.metadata.actual_date||'—',t('live_status_'+tile.status),t(tile.from_cache?'live_cache':'live_network')]){const td=document.createElement('td');td.textContent=value;row.append(td);}tbody.append(row);}
    if(this.inspected!==null)this.inspect(this.inspected);
  }
};
