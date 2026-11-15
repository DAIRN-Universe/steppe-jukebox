/* Geographic zoom/pan changes only the projection, never route keys or audio. */
window.MapViewport = class {
  constructor(hooks){
    this.hooks=hooks;this.zoom=1;this.lon=0;this.lat=0;this.pointers=new Map();this.pending=null;
    const $=id=>document.getElementById(id);this.map=$('route-map');
    $('map-zoom-in').addEventListener('click',()=>this.zoomAt(2));
    $('map-zoom-out').addEventListener('click',()=>this.zoomAt(.5));
    $('map-fit').addEventListener('click',()=>this.reset());
    this.map.addEventListener('wheel',e=>{
      if(!this.hooks.enabled()||!this.inside(this.point(e)))return;
      e.preventDefault();this.zoomAt(e.deltaY<0?1.25:.8,this.point(e));
    },{passive:false});
    this.map.addEventListener('pointerdown',e=>this.down(e));
    this.map.addEventListener('pointermove',e=>this.move(e));
    for(const kind of ['pointerup','pointercancel','lostpointercapture'])this.map.addEventListener(kind,e=>this.up(e));
    this.map.addEventListener('click',e=>{
      if(performance.now()<this.suppressUntil){e.preventDefault();e.stopImmediatePropagation();}
    },true);
  }
  point(e){const box=this.map.getBoundingClientRect(),view=this.map.viewBox.baseVal;
    return {x:(e.clientX-box.left)*view.width/box.width,y:(e.clientY-box.top)*view.height/box.height};}
  inside(p){const g=this.hooks.geometry();return g&&p.x>=g.left&&p.x<=g.right&&p.y>=g.top&&p.y<=g.bottom;}
  schedule(){if(this.pending===null)this.pending=requestAnimationFrame(()=>{this.pending=null;this.hooks.redraw();});}
  reset(redraw=true){this.zoom=1;this.lon=0;this.lat=0;this.drag=null;this.pinch=null;this.pointers.clear();
    if(redraw)this.hooks.redraw();}
  refresh(){
    document.getElementById('map-tools').hidden=!this.hooks.enabled();
    document.getElementById('map-zoom-level').value=Math.round(this.zoom*100)+'%';
    document.getElementById('map-zoom-in').disabled=this.zoom>=8;
    document.getElementById('map-zoom-out').disabled=this.zoom<=1;
    this.map.dataset.zoom=String(this.zoom);
  }
  zoomAt(factor,p){
    const g=this.hooks.geometry();if(!g||!this.hooks.enabled())return;
    const next=Math.max(1,Math.min(8,this.zoom*factor));
    p=p||{x:g.centerX,y:g.centerY};const ratio=next/this.zoom;
    this.lon+=(p.x-g.centerX)/(g.cosLat*g.scale)*(1-1/ratio);
    this.lat-=(p.y-g.centerY)/g.scale*(1-1/ratio);this.zoom=next;
    if(next===1){this.lon=0;this.lat=0;}
    this.hooks.redraw();
  }
  down(e){
    if(!this.hooks.enabled()||e.button!==0||!this.inside(this.point(e)))return;
    this.suppressUntil=0;this.pointers.set(e.pointerId,this.point(e));
    const g=this.hooks.geometry();
    if(this.pointers.size===1)this.drag={id:e.pointerId,p:this.point(e),lon:this.lon,lat:this.lat,g,moved:false};
    if(this.pointers.size===2){
      const [a,b]=[...this.pointers.values()];
      this.pinch={distance:Math.hypot(a.x-b.x,a.y-b.y),mid:{x:(a.x+b.x)/2,y:(a.y+b.y)/2},zoom:this.zoom,lon:this.lon,lat:this.lat,g};
      for(const id of this.pointers.keys())this.map.setPointerCapture(id);
      this.drag=null;
    }
  }
  move(e){
    if(!this.pointers.has(e.pointerId))return;
    const p=this.point(e);this.pointers.set(e.pointerId,p);
    if(this.pinch&&this.pointers.size===2){
      const [a,b]=[...this.pointers.values()],v=this.pinch,g=v.g;
      this.zoom=Math.max(1,Math.min(8,v.zoom*Math.hypot(a.x-b.x,a.y-b.y)/Math.max(1,v.distance)));
      const ratio=this.zoom/v.zoom,mid={x:(a.x+b.x)/2,y:(a.y+b.y)/2};
      this.lon=v.lon+(v.mid.x-g.centerX)/(g.cosLat*g.scale)-(mid.x-g.centerX)/(g.cosLat*g.scale*ratio);
      this.lat=v.lat-(v.mid.y-g.centerY)/g.scale+(mid.y-g.centerY)/(g.scale*ratio);
      if(this.zoom===1){this.lon=0;this.lat=0;}
      this.suppressUntil=performance.now()+400;this.schedule();return;
    }
    const v=this.drag;if(!v||v.id!==e.pointerId||this.zoom<=1)return;
    const dx=p.x-v.p.x,dy=p.y-v.p.y;
    if(!v.moved&&Math.hypot(dx,dy)<5)return;
    v.moved=true;this.map.setPointerCapture(e.pointerId);this.map.classList.add('is-panning');
    this.lon=v.lon-dx/(v.g.cosLat*v.g.scale);this.lat=v.lat+dy/v.g.scale;
    this.suppressUntil=performance.now()+400;this.schedule();
  }
  up(e){
    if(this.drag?.moved||this.pinch)this.suppressUntil=performance.now()+400;
    this.pointers.delete(e.pointerId);this.drag=null;this.pinch=null;this.map.classList.remove('is-panning');
  }
  reveal(cell){
    const g=this.hooks.geometry();if(!g||this.zoom<=1||this.drag?.moved||this.pinch)return;
    const [w,s,e,n]=cell.bounds,x=g.projectX((w+e)/2),y=g.projectY((s+n)/2);
    const dx=x-Math.max(g.left+12,Math.min(g.right-12,x)),dy=y-Math.max(g.top+12,Math.min(g.bottom-12,y));
    if(dx||dy){this.lon+=dx/(g.cosLat*g.scale);this.lat-=dy/g.scale;this.schedule();}
  }
};
