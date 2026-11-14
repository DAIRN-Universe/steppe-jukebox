/* Geographic rendering only. The existing player owns the sole audio clock. */
window.LiveGridMap = class {
  constructor(){this.nodes=new Map();this.landmarks=new Map();this.signature=null;}
  draw(config,slice,geometry,index,ended,landmarks=[]){
    const root=document.getElementById('map-content'),NS='http://www.w3.org/2000/svg';
    const make=(tag,attrs={})=>{const n=document.createElementNS(NS,tag);for(const [k,v]of Object.entries(attrs))n.setAttribute(k,v);return n;};
    const {projectX:x,projectY:y}=geometry;
    const box=cell=>{const [w,s,e,n]=cell.bounds,width=x(e)-x(w),height=y(s)-y(n);return{x:x(w)+width*.1,y:y(n)+height*.1,width:width*.8,height:height*.8,rx:Math.min(width,height)*.14};};
    root.replaceChildren();this.nodes.clear();this.landmarks.clear();
    const defs=make('defs'),mask=make('mask',{id:'live-grid-mask',maskUnits:'userSpaceOnUse',x:0,y:0,width:10000,height:10000});
    // The retained cell list already excludes every boundary crossing and hole.
    for(const cell of config.cells)mask.append(make('rect',{...box(cell),fill:'white','data-grid-key':cell.key}));
    defs.append(mask);root.append(defs);
    const layer=make('g',{mask:'url(#live-grid-mask)',id:'live-map-images'});
    layer.append(make('rect',{x:0,y:0,width:10000,height:10000,fill:'#62796c'}));
    for(const tile of slice?.tiles||[]){
      if(!['ndvi','EIC'].includes(tile.layer)||['ok','waiting'].includes(tile.status))continue;
      const color=tile.status==='date_mismatch'?'#c88838':'#9f3651';
      if(tile.bounds){const[w,s,e,n]=tile.bounds;layer.append(make('rect',{x:x(w),y:y(n),width:x(e)-x(w),height:y(s)-y(n),fill:color}));}
      else layer.append(make('rect',{x:0,y:0,width:10000,height:10000,fill:color}));
    }
    for(const image of slice?.images||[]){const[w,s,e,n]=image.bounds;layer.append(make('image',{href:image.src,x:x(w),y:y(n),width:x(e)-x(w),height:y(s)-y(n),preserveAspectRatio:'none',class:'tile-image','data-image-key':image.key}));}
    root.append(layer);
    const cells=new Map(config.cells.map(c=>[c.key,c]));
    for(const entry of config.route_cells){
      const cell=cells.get(entry.key),node=make('rect',{...box(cell),class:'route-tile','data-grid-key':entry.key,hidden:''});
      node.addEventListener('click',()=>{const i=this.currentIndex>=0&&config.point_keys[this.currentIndex]===entry.key?this.currentIndex:config.point_keys.indexOf(entry.key);if(i>=0)this.onSelect?.(i);});
      root.append(node);this.nodes.set(entry.key,node);
    }
    for(const [i,key] of config.point_keys.entries()){
      if(!cells.has(key))continue;
      const target=make('rect',{...box(cells.get(key)),class:'route-point-target',tabindex:0,role:'button','aria-label':config.point_ids[i],'data-point-id':config.point_ids[i]});
      target.addEventListener('focus',()=>this.nodes.get(key)?.classList.add('focused'));
      target.addEventListener('blur',()=>this.nodes.get(key)?.classList.remove('focused'));
      target.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();this.onSelect?.(i);}});root.append(target);
    }
    for(const point of landmarks){
      const marker=make('g',{class:'route-landmark',transform:`translate(${x(point.lon)},${y(point.lat)})`,
        tabindex:0,role:'button','data-landmark-id':point.cell_id});
      marker.append(make('title'),make('rect',{x:-12,y:-12,width:24,height:24,fill:'transparent'}));
      for(const kind of ['halo','symbol'])marker.append(make('path',{d:'M -6 0 H 6 M 0 -6 V 6',class:'route-landmark-'+kind}));
      marker.addEventListener('click',()=>this.onSelect?.(point.index));
      marker.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();this.onSelect?.(point.index);}});
      root.append(marker);this.landmarks.set(point.cell_id,marker);
    }
    this.labelLandmarks(landmarks);
    this.config=config;this.signature=null;this.highlight(index,ended);
  }
  labelLandmarks(points){
    for(const point of points){const marker=this.landmarks.get(point.cell_id);if(!marker)continue;
      marker.setAttribute('aria-label',point.label);marker.querySelector('title').textContent=point.label;
    }
  }
  highlight(index,ended){
    this.currentIndex=index;
    if(!this.config)return;
    const current=index>=0?this.config.point_keys[index]:null,reached=ended?Infinity:index;
    const signature=`${current}:${reached}`;if(signature===this.signature)return;
    for(const entry of this.config.route_cells){const node=this.nodes.get(entry.key),active=entry.key===current;
      const passed=reached>=0&&entry.first_step<=reached&&!active;
      node.toggleAttribute('hidden',!active&&!passed);
      node.classList.toggle('active',active);node.classList.toggle('passed',passed);
      if(active)node.setAttribute('aria-current','step');else node.removeAttribute('aria-current');
    }
    this.signature=signature;
  }
};
