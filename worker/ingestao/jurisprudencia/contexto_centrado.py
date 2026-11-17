"""Contexto centrado no acerto do recuperador, sem consultar evidências de gabarito."""
from bisect import bisect_left,bisect_right
from functools import lru_cache
from . import chunking,chunking_avancado as adv

WINDOW_SIZES=(256,500,512,1000,1024,2500,5000)

class Packer:
    def __init__(self,documents,tokenizer):
        self.documents=documents;self.tokenizer=tokenizer;self.positions={};self.indices={};self.units={};self.windows={}
    def offsets(self,ident):
        if ident not in self.positions:
            self.positions[ident]=chunking.offsets(self.documents[ident]['texto'],self.tokenizer)
            self.indices[ident]=([p[0] for p in self.positions[ident]],[p[1] for p in self.positions[ident]])
        return self.positions[ident]
    def window(self,row,cap,section=False):
        ident=row['registro_id'];text=self.documents[ident]['texto'];p=self.offsets(ident)
        scope=(row['contexto_inicio'],row['contexto_fim']) if section else (0,len(text))
        key=(ident,row['inicio'],row['fim'],scope,cap)
        if key in self.windows:return self.windows[key]
        starts,ends=self.indices[ident]
        lo=bisect_left(starts,scope[0]);hi=bisect_right(ends,scope[1])
        ca=bisect_left(starts,row['inicio']);cb=bisect_right(ends,row['fim'])
        center=(ca+cb)//2;length=min(cap,hi-lo)
        a=max(lo,min(center-length//2,hi-length));b=a+length
        if b<=a:return scope[0],scope[0]
        begin=scope[0] if a==lo else p[a][0];end=scope[1] if b==hi else p[b-1][1]
        # Um marcador de anonimização é atômico, mesmo se seus tokens cruzarem a borda.
        scan_start=max(0,begin-100)
        for marker in chunking.MARKER.finditer(text[scan_start:min(len(text),end+100)]):
            m0=scan_start+marker.start();m1=scan_start+marker.end()
            if m0<begin<m1:begin=m1
            if m0<end<m1:end=m0
        self.windows[key]=(begin,max(begin,end));return self.windows[key]
    def pack(self,ranking,budget,window_tokens=None,section=False):
        if budget<=0:raise ValueError('Orçamento deve ser positivo.')
        selected=[];texts=[];seen={};cuts=0;examined=0
        for row in ranking:
            examined+=1;ident=row['registro_id'];text=self.documents[ident]['texto']
            old=seen.get(ident,[])
            expanded=window_tokens is not None or section
            def pieces(size):
                if expanded:
                    a,b=self.window(row,size,section)
                else:
                    key=row['texto_sha256']
                    if key not in self.units:self.units[key]=chunking.offsets(row['texto'],self.tokenizer)
                    offsets=self.units[key]
                    a=row['inicio'];b=row['fim'] if size>=len(offsets) else a+offsets[size-1][1]
                return [(u,v) for u,v in adv.uncovered(a,b,old) if text[u:v].strip()]
            maximum=(window_tokens or budget) if expanded else row['tokens']
            maximum=max(1,maximum)
            def used(parts):return chunking.token_count('\n\n'.join(texts+[text[a:b] for a,b in parts]),self.tokenizer)
            parts=pieces(maximum)
            if not parts:continue
            if used(parts)>budget:
                lo=0;hi=maximum
                while lo<hi:
                    mid=(lo+hi+1)//2
                    if used(pieces(mid))<=budget:lo=mid
                    else:hi=mid-1
                if not lo:continue
                parts=pieces(lo);cuts+=1
            if not parts:continue
            assert used(parts)<=budget
            for a,b in parts:
                selected.append(dict(row,inicio=a,fim=b,texto=text[a:b],
                    unidade_indexada_inicio=row['inicio'],unidade_indexada_fim=row['fim']))
                texts.append(text[a:b]);seen.setdefault(ident,[]).append((a,b))
            if chunking.token_count('\n\n'.join(texts),self.tokenizer)>=budget:break
        consumed=chunking.token_count('\n\n'.join(texts),self.tokenizer)
        assert consumed<=budget
        return selected,consumed,cuts,examined
