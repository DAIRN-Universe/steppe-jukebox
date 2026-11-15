/* Geographic rendering only. The existing player owns the sole audio clock. */
window.LiveGridMap = class {
  constructor(){this.nodes=new Map();this.signature=null;}
  draw(config,slice,geometry,index,ended){
    this.restorePickFocus=document.activeElement?.dataset.pickKey;
    const root=document.getElementById('map-content'),NS='http://www.w3.org/2000/svg';
    const make=(tag,attrs={})=>{const n=document.createElementNS(NS,tag);for(const [k,v]of Object.entries(attrs))n.setAttribute(k,v);return n;};
    const {projectX:x,projectY:y}=geometry;
    const box=cell=>{const [w,s,e,n]=cell.bounds,width=x(e)-x(w),height=y(s)-y(n);return{x:x(w)+width*.1,y:y(n)+height*.1,width:width*.8,height:height*.8,rx:Math.min(width,height)*.14};};
    root.replaceChildren();this.nodes.clear();
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
      target.addEventListener('focus',()=>{const node=this.nodes.get(key);node?.classList.add('focused');node?.removeAttribute('hidden');});
      target.addEventListener('blur',()=>{this.nodes.get(key)?.classList.remove('focused');this.signature=null;this.highlight(this.currentIndex,this.ended);});
      target.addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();this.onSelect?.(i);}});root.append(target);
    }
    this.config=config;this.signature=null;this.highlight(index,ended);
  }
  edit({editing,draft,names,text,onSelect}){
    const root=document.getElementById('map-content'),NS='http://www.w3.org/2000/svg';
    document.getElementById('route-map').setAttribute('role','group');
    const make=(tag,attrs={})=>{const n=document.createElementNS(NS,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);return n;};
    const cells=this.config.cells,byPosition=new Map(cells.map(c=>[`${c.row}/${c.col}`,c]));
    const previous=document.activeElement?.dataset.pickKey||this.restorePickFocus;
    this.restorePickFocus=null;
    root.querySelector('#route-edit-layer')?.remove();
    const layer=make('g',{id:'route-edit-layer','aria-label':text('route_coordinates')}),labels=[];
    for(const cell of cells){
      const rect=root.querySelector(`mask [data-grid-key="${cell.key}"]`),attrs={};
      for(const attr of ['x','y','width','height','rx'])attrs[attr]=rect.getAttribute(attr);
      if(editing){
        const target=make('rect',{...attrs,class:'route-pick','data-pick-key':cell.key,
          tabindex:cell.key===(previous||this.focusKey||cells[0]?.key)?0:-1,role:'button',
          'aria-label':`${text('route_cell')} ${cell.key}`});
        target.addEventListener('click',()=>onSelect(cell.key));
        target.addEventListener('focus',()=>{this.focusKey=cell.key;if(!this.restoringFocus)this.onFocusCell?.(cell);});
        target.addEventListener('keydown',e=>{
          if(['Enter',' '].includes(e.key)){e.preventDefault();onSelect(cell.key);return;}
          const direction={ArrowLeft:[0,-1],ArrowRight:[0,1],ArrowUp:[-1,0],ArrowDown:[1,0]}[e.key];
          if(direction){e.preventDefault();const next=byPosition.get(`${cell.row+direction[0]}/${cell.col+direction[1]}`);
            if(next){target.setAttribute('tabindex',-1);const node=layer.querySelector(`[data-pick-key="${next.key}"]`);node.setAttribute('tabindex',0);node.focus();}}
        });
        layer.append(target);
      }
      const indices=draft.flatMap((key,i)=>key===cell.key?[i+1]:[]);
      if(indices.length){
        const marker=make('g',{class:'route-waypoint','data-waypoint-key':cell.key,'pointer-events':'none'});
        const name=names?.get(cell.key);
        marker.setAttribute('aria-label',`${indices.join(', ')}${name?' · '+name:''}`);
        marker.setAttribute('role','img');
        const title=make('title');title.textContent=marker.getAttribute('aria-label');marker.append(title);
        const x=Number(attrs.x)+Number(attrs.width)/2,y=Number(attrs.y)+Number(attrs.height)/2;
        const radius=Math.max(8,indices.join(',').length*3);
        const offsets=[[0,-18],[18,0],[0,18],[-18,0],[18,-18],[-18,18],[0,-36],[36,0]];
        const [dx,dy]=offsets.find(([dx,dy])=>labels.every(p=>Math.hypot(x+dx-p.x,y+dy-p.y)>radius+p.radius+2))||[0,36];
        const cx=x+dx,cy=y+dy;labels.push({x:cx,y:cy,radius});
        marker.append(make('path',{d:`M ${x} ${y} L ${cx} ${cy}`}),make('circle',{cx:x,cy:y,r:2}),make('circle',{cx,cy,r:radius}));
        const label=make('text',{x:cx,y:cy+3});label.textContent=indices.join(',');
        marker.append(label);layer.append(marker);
      }
    }
    root.append(layer);
    this.restoringFocus=true;
    if(previous)layer.querySelector(`[data-pick-key="${previous}"]`)?.focus({preventScroll:true});
    this.restoringFocus=false;
  }
  highlight(index,ended){
    this.currentIndex=index;this.ended=ended;
    if(!this.config)return;
    const current=index>=0?this.config.point_keys[index]:null,reached=ended?Infinity:index;
    const signature=`${current}:${reached}`;if(signature===this.signature)return;
    for(const entry of this.config.route_cells){const node=this.nodes.get(entry.key),active=entry.key===current;
      const passed=reached>=0&&entry.first_step<=reached&&!active;
      node.toggleAttribute('hidden',!active&&!passed&&!node.classList.contains('focused'));
      node.classList.toggle('active',active);node.classList.toggle('passed',passed);
      if(active)node.setAttribute('aria-current','step');else node.removeAttribute('aria-current');
    }
    this.signature=signature;
  }
};
